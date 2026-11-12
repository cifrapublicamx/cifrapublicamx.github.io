"""
Cifra Pública | Folio 003 | Empleo formal (IMSS)

Módulo común: encuentra los archivos mensuales de asegurados en el portal de datos
abiertos del IMSS, los descarga y los lee.

Lo que sabemos del portal (revisado el 12 de noviembre de 2026):
- Un conjunto por año («ASG 2026», etc.) con un CSV por mes: asg-AAAA-MM-DD.csv.
- La dirección del conjunto cambia según el espejo: dataset/asg-2026 y dataset/asg2026.
  Por eso el enlace se busca (API de DKAN y, si falla, la página), no se arma.
- El portal no sirve por https («SSL is not supported»): todo va por http.
- Cada archivo mensual pesa ~400 MB.

Para pruebas locales: IMSS_BASES="http://127.0.0.1:8765" apunta a un portal simulado.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, asdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = Path(__file__).resolve().parents[2]          # raíz del repo
CRUDO = BASE / "data" / "raw" / "empleo"            # data/raw/ está en .gitignore
FUENTES = BASE / "data" / "fuentes" / "empleo"
PROCESADO = BASE / "data" / "processed" / "empleo"
MENSUAL = PROCESADO / "mensual"

BASES = [b.rstrip("/") for b in os.environ.get(
    "IMSS_BASES", "http://datos.imss.gob.mx,http://www2.imss.gob.mx").split(",") if b.strip()]

USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) CifraPublica/1.0 "
              "(+https://cifrapublicamx.github.io; datos abiertos IMSS)")

PATRON_ARCHIVO = re.compile(r"asg-(\d{4})-(\d{2})-(\d{2})(?:\.csv)?", re.I)

# Columnas que esperamos (diccionario del IMSS, a confirmar con el sondeo).
DIMENSIONES = ["cve_delegacion", "cve_subdelegacion", "cve_entidad", "cve_municipio",
               "sector_economico_1", "sector_economico_2", "sector_economico_4",
               "tamano_patron", "sexo", "rango_edad", "rango_salarial", "rango_uma"]
MEDIDAS = ["asegurados", "no_trabajadores", "ta", "teu", "tec", "tpu", "tpc",
           "ta_sal", "teu_sal", "tec_sal", "tpu_sal", "tpc_sal",
           "masa_sal_ta", "masa_sal_teu", "masa_sal_tec", "masa_sal_tpu", "masa_sal_tpc"]
# Lo mínimo para extraer; si falta algo de aquí, la extracción se detiene.
REQUERIDAS = ["cve_entidad", "cve_municipio", "sector_economico_1", "sector_economico_2",
              "sector_economico_4", "tamano_patron", "sexo", "rango_edad", "rango_uma",
              "ta", "teu", "tec", "tpu", "tpc", "ta_sal", "masa_sal_ta"]


# ---------------------------------------------------------------- red

def sesion() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "es-MX,es;q=0.9"})
    reintentos = Retry(total=5, connect=5, read=5, backoff_factor=3,
                       status_forcelist=(429, 500, 502, 503, 504),
                       allowed_methods=("GET", "HEAD"), raise_on_status=False)
    s.mount("http://", HTTPAdapter(max_retries=reintentos))
    s.mount("https://", HTTPAdapter(max_retries=reintentos))
    return s


def a_http(url: str) -> str:
    """El portal no acepta https: cualquier enlace del IMSS se baja por http."""
    p = urlsplit(url)
    if p.scheme == "https" and p.hostname and p.hostname.endswith("imss.gob.mx"):
        p = p._replace(scheme="http")
    return urlunsplit(p)


class RespuestaRara(RuntimeError):
    """El portal respondió algo que no es lo que pedimos (p. ej. una página de bloqueo)."""


def _get(s: requests.Session, url: str, **kw) -> requests.Response:
    r = s.get(a_http(url), timeout=(30, 120), **kw)
    r.raise_for_status()
    return r


# ---------------------------------------------------------------- descubrimiento

@dataclass
class Recurso:
    mes: str            # AAAA-MM
    fecha_corte: str    # AAAA-MM-DD
    url: str
    nombre: str
    origen: str         # api | html
    tamano: int | None = None


class _Enlaces(HTMLParser):
    def __init__(self):
        super().__init__()
        self.enlaces: list[tuple[str, str]] = []
        self._href = None
        self._texto: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._texto = []

    def handle_data(self, data):
        if self._href is not None:
            self._texto.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.enlaces.append((self._href, " ".join("".join(self._texto).split())))
            self._href = None


def enlaces(html: str, base: str) -> list[tuple[str, str]]:
    p = _Enlaces()
    p.feed(html)
    return [(urljoin(base, h), t) for h, t in p.enlaces if h]


def _recurso_de(url: str, nombre: str, origen: str, tamano=None) -> Recurso | None:
    m = PATRON_ARCHIVO.search(url) or PATRON_ARCHIVO.search(nombre or "")
    if not m:
        return None
    a, mm, d = m.groups()
    try:
        tamano = int(tamano) if tamano not in (None, "") else None
    except (TypeError, ValueError):
        tamano = None
    return Recurso(f"{a}-{mm}", f"{a}-{mm}-{d}", a_http(url), nombre or "", origen, tamano)


def _paquete_api(s, base: str, pid: str) -> dict | None:
    try:
        r = _get(s, f"{base}/api/3/action/package_show", params={"id": pid})
        datos = r.json()
    except (requests.RequestException, ValueError):
        return None
    res = datos.get("result") if isinstance(datos, dict) else None
    if isinstance(res, list):                       # DKAN devuelve una lista
        res = res[0] if res else None
    return res if isinstance(res, dict) else None


def recursos_api(s, base: str, pid: str) -> list[Recurso]:
    paquete = _paquete_api(s, base, pid)
    if not paquete:
        return []
    out = []
    for rec in paquete.get("resources") or []:
        url = rec.get("url") or rec.get("download_url") or ""
        r = _recurso_de(url, rec.get("name") or rec.get("title") or "", "api",
                        rec.get("size") or rec.get("filesize"))
        if r and url.lower().split("?")[0].endswith(".csv"):
            out.append(r)
    return out


def recursos_html(s, base: str, pid: str) -> list[Recurso]:
    try:
        pagina = _get(s, f"{base}/dataset/{pid}")
    except requests.RequestException:
        return []
    out, vistos = [], set()
    candidatos = enlaces(pagina.text, pagina.url)
    for url, texto in candidatos:
        if url.lower().split("?")[0].endswith(".csv"):
            r = _recurso_de(url, texto, "html")
            if r and r.url not in vistos:
                vistos.add(r.url); out.append(r)
    # Si la página solo enlaza a páginas de recurso, entra a cada una por su CSV.
    for url, texto in candidatos:
        if "/resource/" in url and PATRON_ARCHIVO.search(url + " " + texto):
            try:
                sub = _get(s, url)
            except requests.RequestException:
                continue
            for u2, t2 in enlaces(sub.text, sub.url):
                if u2.lower().split("?")[0].endswith(".csv"):
                    r = _recurso_de(u2, t2 or texto, "html")
                    if r and r.url not in vistos:
                        vistos.add(r.url); out.append(r)
    return out


def diagnostico(s, url: str) -> str:
    """Una línea con lo que contesta el portal: estado, tipo, redirección y el inicio del cuerpo."""
    try:
        r = s.get(a_http(url), timeout=(20, 60), allow_redirects=True)
    except requests.RequestException as e:
        return f"sin respuesta: {type(e).__name__}: {' '.join(str(e).split())[:200]}"
    cuerpo = " ".join(r.text[:400].split())
    bloqueo = any(p in r.text[:5000].lower() for p in ("incapsula", "imperva", "request blocked", "captcha"))
    salto = f" | redirigió a {r.url}" if r.url != a_http(url) else ""
    return (f"HTTP {r.status_code} | {r.headers.get('Content-Type', '')}{salto}"
            f"{' | PARECE BLOQUEO' if bloqueo else ''} | {cuerpo[:200]}")


def ids_anio(anio: int) -> list[str]:
    return [f"asg-{anio}", f"asg{anio}"]


def vivo(base: str) -> tuple[bool, str]:
    """Prueba rápida, sin reintentos: si el servidor ni contesta, no tiene caso buscar ahí."""
    try:
        r = requests.get(base + "/", timeout=(15, 30), headers={"User-Agent": USER_AGENT})
        return True, f"HTTP {r.status_code}"
    except requests.RequestException as e:
        return False, f"{type(e).__name__}: {' '.join(str(e).split())[:200]}"


_VIVAS: list[str] | None = None


def bases_vivas(bitacora: list | None = None) -> list[str]:
    global _VIVAS
    if _VIVAS is None:
        _VIVAS = []
        for base in BASES:
            ok, detalle = vivo(base)
            if bitacora is not None:
                bitacora.append(f"{base}: {'contesta' if ok else 'NO CONTESTA'} ({detalle})")
            if ok:
                _VIVAS.append(base)
    return _VIVAS


def descubrir(anios, s=None, bitacora: list | None = None) -> dict[str, Recurso]:
    """Devuelve {AAAA-MM: Recurso} para los años pedidos. Prueba API y página en cada espejo."""
    s = s or sesion()
    hallados: dict[str, Recurso] = {}
    bases = bases_vivas(bitacora)
    for anio in anios:
        for base in bases:
            encontrados = []
            for pid in ids_anio(anio):
                for metodo in (recursos_api, recursos_html):
                    try:
                        rs = metodo(s, base, pid)
                    except Exception as e:                   # noqa: BLE001
                        rs = []
                        if bitacora is not None:
                            bitacora.append(f"{anio} | {base} | {pid} | {metodo.__name__}: error {e!r}")
                    if bitacora is not None:
                        bitacora.append(f"{anio} | {base} | {pid} | {metodo.__name__}: {len(rs)} archivos")
                    encontrados += [r for r in rs if r.mes.startswith(str(anio))]
                    if rs:
                        break
            for r in encontrados:
                hallados.setdefault(r.mes, r)
            if any(m.startswith(str(anio)) for m in hallados):
                break                                       # ya no hace falta el otro espejo
            if bitacora is not None:                        # ¿qué respondió el portal? (bloqueo, 404, https…)
                bitacora.append(f"{anio} | {base} | diagnóstico: {diagnostico(s, base + '/dataset/' + ids_anio(anio)[0])}")
    return dict(sorted(hallados.items()))


# ---------------------------------------------------------------- descarga

def descargar(rec: Recurso, s=None, destino: Path = CRUDO, forzar=False) -> Path:
    s = s or sesion()
    destino.mkdir(parents=True, exist_ok=True)
    archivo = destino / f"asg-{rec.fecha_corte}.csv"
    if archivo.exists() and not forzar and archivo.stat().st_size > 0:
        if rec.tamano is None or archivo.stat().st_size == rec.tamano:
            return archivo
    parcial = archivo.with_suffix(".csv.part")
    ultimo_error = None
    for intento in range(1, 4):
        try:
            with s.get(rec.url, stream=True, timeout=(30, 300)) as r:
                r.raise_for_status()
                tipo = r.headers.get("Content-Type", "")
                esperado = int(r.headers["Content-Length"]) if r.headers.get("Content-Length") else None
                bajado = 0
                with open(parcial, "wb") as f:
                    for i, bloque in enumerate(r.iter_content(chunk_size=1 << 20)):
                        inicio = bloque[:2000].lower()
                        if i == 0 and (b"<html" in inicio or b"<!doctype" in inicio):
                            muestra = bloque[:1500].decode("utf-8", "replace")
                            raise RespuestaRara(
                                f"El portal respondió HTML en lugar del CSV ({rec.url}, "
                                f"Content-Type: {tipo or 'sin dato'}). Posible bloqueo o página "
                                f"de error. Inicio:\n{muestra}")
                        f.write(bloque)
                        bajado += len(bloque)
                if esperado is not None and bajado != esperado:
                    raise IOError(f"Descarga incompleta: {bajado} de {esperado} bytes")
            parcial.replace(archivo)
            return archivo
        except RespuestaRara:
            parcial.unlink(missing_ok=True)
            raise
        except (requests.RequestException, IOError) as e:
            ultimo_error = e
            parcial.unlink(missing_ok=True)
            time.sleep(20 * intento)
    raise RuntimeError(f"No se pudo descargar {rec.url}: {ultimo_error!r}")


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


# ---------------------------------------------------------------- lectura

def normaliza_columna(nombre: str) -> str:
    s = nombre.replace("﻿", "").strip().strip('"').lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9_]+", "_", s).strip("_")
    if s.startswith("tama") and s.endswith("patron"):    # tamaño / tamaÃ±o / tamano
        s = "tamano_patron"
    return s


@dataclass
class Formato:
    codificacion: str
    separador: str
    columnas_crudas: list
    columnas: list          # normalizadas


def detecta_formato(ruta: Path) -> Formato:
    with open(ruta, "rb") as f:
        cabeza = f.read(1 << 20)
    # La codificación se decide con el archivo entero leído por pedazos: un acento en la
    # fila 3 millones también cuenta. Si algo no es UTF-8 válido, es latin-1.
    cod = "utf-8-sig"
    try:
        with open(ruta, "r", encoding="utf-8-sig", newline="") as f:
            for _ in iter(lambda: f.read(1 << 22), ""):
                pass
    except UnicodeDecodeError:
        cod = "latin-1"
    primera = cabeza.split(b"\n", 1)[0].rstrip(b"\r").decode(cod, "replace")
    conteos = {sep: primera.count(sep) for sep in ("|", ",", ";", "\t")}
    sep = max(conteos, key=conteos.get)
    crudas = next(csv.reader(io.StringIO(primera), delimiter=sep))
    return Formato(cod, sep, crudas, [normaliza_columna(c) for c in crudas])


def lee_por_partes(ruta: Path, fmt: Formato, usar: list[str], tam=750_000):
    """Itera el CSV en pedazos con columnas normalizadas: dimensiones como texto, medidas como número."""
    import pandas as pd
    idx = {c: i for i, c in enumerate(fmt.columnas)}
    faltan = [c for c in usar if c not in idx]
    if faltan:
        raise KeyError(f"Faltan columnas en el archivo: {faltan}. Columnas: {fmt.columnas}")
    posiciones = sorted(idx[c] for c in usar)
    nombres = [fmt.columnas[i] for i in posiciones]
    for parte in pd.read_csv(ruta, sep=fmt.separador, encoding=fmt.codificacion, header=0,
                             usecols=posiciones, dtype=str, keep_default_na=False,
                             chunksize=tam, low_memory=False):
        parte.columns = nombres
        for c in nombres:
            if c in MEDIDAS:
                parte[c] = pd.to_numeric(parte[c].str.strip().replace("", "0"),
                                         errors="coerce").fillna(0)
            else:
                parte[c] = parte[c].str.strip()
        yield parte


# ---------------------------------------------------------------- utilidades

def escribe_json(ruta: Path, obj) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def resumen_github(texto: str) -> None:
    """Escribe en el resumen del job de GitHub Actions (se lee desde el celular)."""
    destino = os.environ.get("GITHUB_STEP_SUMMARY")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(texto + "\n")


def meses_procesados() -> set[str]:
    if not MENSUAL.exists():
        return set()
    return {p.name for p in MENSUAL.iterdir() if (p / "meta.json").exists()}


def rango_meses(desde: str, hasta: str) -> list[str]:
    a, m = map(int, desde.split("-"))
    a2, m2 = map(int, hasta.split("-"))
    out = []
    while (a, m) <= (a2, m2):
        out.append(f"{a:04d}-{m:02d}")
        m += 1
        if m == 13:
            a, m = a + 1, 1
    return out


def anio_actual() -> int:
    return time.gmtime().tm_year


def recurso_a_dict(r: Recurso) -> dict:
    return asdict(r)


if __name__ == "__main__":
    # Prueba rápida: python scripts/empleo/imss.py 2026
    anios = [int(a) for a in sys.argv[1:]] or [anio_actual()]
    bit = []
    for mes, r in descubrir(anios, bitacora=bit).items():
        print(mes, r.url, r.origen, r.tamano)
    print("\n".join(bit))
