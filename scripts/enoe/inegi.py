"""
Cifra Pública | Folio 003 | Ocupación e informalidad por ciudad (ENOE, INEGI)

Módulo común: arma la dirección de los microdatos de cada trimestre, los descarga, lee la tabla
sociodemográfica (SDEM) y calcula los indicadores laborales por ciudad con su margen de error.

Lo que sabemos (revisado el 12 de noviembre de 2026 en inegi.org.mx):
- Un zip por trimestre, 28 a 41 MB en CSV. Tres formas de nombre:
    2015–2020 T1:  2019trim4_csv.zip
    2020 T3–2022:  enoe_n_2021_trim4_csv.zip     (ENOE Nueva Edición)
    2023 en adelante: enoe_2026_trim2_csv.zip
  2020 T2 no existe (fue la encuesta telefónica, ETOE).
- La tabla SDEM trae ciudad (CD_A), entidad (ENT; CVE_ENT desde 2025 T3), factor de expansión
  (FAC hasta 2020 T1; FAC_TRI después), resultado de la entrevista (R_DEF, 00 = completa),
  residencia (C_RES, 1 y 3 = residentes), edad (EDA), CLASE1 (1 = PEA), CLASE2 (1 = ocupada,
  2 = desocupada), EMP_PPAL (1 = empleo informal), TUE_PPAL (1 = sector informal).
- Ciudades: 39, con claves CD_A (León 05, Puebla 04, San Luis Potosí 07, Aguascalientes 14,
  Tijuana 21, Querétaro 36); 81–86 son el complemento urbano-rural, no ciudades.

Para pruebas locales: INEGI_BASE="http://127.0.0.1:8770/microdatos/" apunta a un servidor simulado.
"""
from __future__ import annotations

import io
import json
import os
import re
import time
import unicodedata
import zipfile
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = Path(__file__).resolve().parents[2]                     # raíz del repo
CRUDO = BASE / "data" / "raw" / "enoe"                          # fuera del repo (.gitignore)
FUENTES = BASE / "data" / "fuentes" / "enoe"
PROCESADO = BASE / "data" / "processed" / "enoe"

URL_BASE = os.environ.get("INEGI_BASE",
                          "https://www.inegi.org.mx/contenidos/programas/enoe/15ymas/microdatos/")
USER_AGENT = "CifraPublica/1.0 (+https://cifrapublicamx.github.io; microdatos ENOE)"

# Columnas que se leen de la SDEM (nombres en minúsculas, después de normalizar).
COLUMNAS = ["cd_a", "cve_ent", "ent", "cve_mun", "mun", "r_def", "c_res", "eda", "sex",
            "clase1", "clase2", "emp_ppal", "tue_ppal", "pos_ocu", "rama_est2", "ingocup",
            "ing7c", "hrsocup", "fac", "fac_tri", "upm", "est_d_tri", "est_d", "est"]
REQUERIDAS = ["cd_a", "r_def", "c_res", "eda", "clase1", "clase2", "emp_ppal", "tue_ppal"]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S', time.gmtime())}] {msg}", flush=True)


# ---------------------------------------------------------------- trimestres y direcciones

def archivo_trimestre(anio: int, trim: int) -> str | None:
    if (anio, trim) == (2020, 2):
        return None                                   # ETOE: no hay microdatos de ENOE
    if (anio, trim) >= (2023, 1):
        return f"enoe_{anio}_trim{trim}_csv.zip"
    if (anio, trim) >= (2020, 3):
        return f"enoe_n_{anio}_trim{trim}_csv.zip"
    return f"{anio}trim{trim}_csv.zip"


def url_trimestre(anio: int, trim: int) -> str | None:
    nombre = archivo_trimestre(anio, trim)
    return URL_BASE + nombre if nombre else None


def trimestres(desde=(2019, 1), hasta=None) -> list[tuple[int, int]]:
    if hasta is None:
        g = time.gmtime()
        hasta = (g.tm_year, (g.tm_mon - 1) // 3 + 1)
    out, (a, t) = [], desde
    while (a, t) <= hasta:
        if archivo_trimestre(a, t):
            out.append((a, t))
        a, t = (a + 1, 1) if t == 4 else (a, t + 1)
    return out


def etiqueta(anio: int, trim: int) -> str:
    return f"{anio}-T{trim}"


# ---------------------------------------------------------------- red

def sesion() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    r = Retry(total=3, backoff_factor=5, status_forcelist=(429, 500, 502, 503, 504),
              allowed_methods=("GET", "HEAD"), raise_on_status=False)
    s.mount("https://", HTTPAdapter(max_retries=r))
    s.mount("http://", HTTPAdapter(max_retries=r))
    return s


def consulta(s, url: str) -> dict:
    """HEAD: ¿existe y cuánto pesa? (sin bajar el archivo)."""
    try:
        r = s.head(url, timeout=(15, 45), allow_redirects=True)
        return {"estado": r.status_code, "bytes": int(r.headers.get("Content-Length") or 0),
                "tipo": r.headers.get("Content-Type", ""), "url_final": r.url}
    except requests.RequestException as e:
        return {"estado": None, "error": f"{type(e).__name__}: {' '.join(str(e).split())[:200]}"}


def ultimo_disponible(s, hasta=None, atras=6) -> tuple[int, int] | None:
    """El trimestre más reciente que ya está publicado (prueba hacia atrás desde hoy)."""
    for a, t in reversed(trimestres((2019, 1), hasta)[-atras:]):
        c = consulta(s, url_trimestre(a, t))
        log(f"¿{etiqueta(a, t)}? HTTP {c.get('estado')} {c.get('bytes', 0):,} bytes")
        if c.get("estado") == 200 and c.get("bytes", 1) > 1_000_000:
            return a, t
    return None


class RespuestaRara(RuntimeError):
    pass


def descargar(s, anio: int, trim: int, destino: Path = CRUDO) -> Path:
    url = url_trimestre(anio, trim)
    destino.mkdir(parents=True, exist_ok=True)
    archivo = destino / archivo_trimestre(anio, trim)
    if archivo.exists() and zipfile.is_zipfile(archivo):
        return archivo
    parcial = archivo.with_suffix(".part")
    with s.get(url, stream=True, timeout=(30, 300)) as r:
        r.raise_for_status()
        with open(parcial, "wb") as f:
            for i, b in enumerate(r.iter_content(1 << 20)):
                if i == 0 and (b"<html" in b[:2000].lower() or b"<!doctype" in b[:2000].lower()):
                    raise RespuestaRara(f"{url} respondió HTML, no un zip: "
                                        f"{' '.join(b[:400].decode('utf-8', 'replace').split())}")
                f.write(b)
    if not zipfile.is_zipfile(parcial):
        parcial.unlink(missing_ok=True)
        raise RespuestaRara(f"{url}: lo descargado no es un zip válido")
    parcial.replace(archivo)
    return archivo


# ---------------------------------------------------------------- lectura

def normaliza(nombre: str) -> str:
    s = nombre.replace("﻿", "").strip().strip('"').lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9_]+", "_", s).strip("_")


def tabla_sdem(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path) as z:
        candidatos = [n for n in z.namelist() if "sdem" in n.lower() and n.lower().endswith(".csv")]
    if not candidatos:
        raise FileNotFoundError(f"{zip_path.name}: no hay tabla SDEM en CSV. Contenido: {contenido(zip_path)}")
    return sorted(candidatos, key=len)[0]


def contenido(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as z:
        return [f"{i.filename} ({i.file_size / 1e6:.1f} MB)" for i in z.infolist()]


def lee_sdem(zip_path: Path):
    """DataFrame con las columnas útiles, en minúsculas y numéricas. Devuelve (df, info)."""
    import pandas as pd
    nombre = tabla_sdem(zip_path)
    with zipfile.ZipFile(zip_path) as z:
        crudo = z.read(nombre)
    for cod in ("utf-8-sig", "latin-1"):
        try:
            texto = crudo.decode(cod)
            break
        except UnicodeDecodeError:
            continue
    primera = texto.split("\n", 1)[0]
    sep = max((",", ";", "|", "\t"), key=primera.count)
    cab = [normaliza(c) for c in primera.split(sep)]
    usar = [i for i, c in enumerate(cab) if c in COLUMNAS]
    df = pd.read_csv(io.StringIO(texto), sep=sep, usecols=usar, dtype=str, keep_default_na=False,
                     low_memory=False)
    df.columns = [cab[i] for i in usar]
    df = df.loc[:, ~df.columns.duplicated()]
    for c in df.columns:
        df[c] = pd.to_numeric(df[c].str.strip(), errors="coerce")
    if "cve_ent" not in df.columns and "ent" in df.columns:
        df = df.rename(columns={"ent": "cve_ent"})
    if "cve_mun" not in df.columns and "mun" in df.columns:
        df = df.rename(columns={"mun": "cve_mun"})
    peso = "fac_tri" if "fac_tri" in df.columns else ("fac" if "fac" in df.columns else None)
    estrato = next((c for c in ("est_d_tri", "est_d", "est") if c in df.columns), None)
    info = {"tabla": nombre, "codificacion": cod, "separador": sep, "filas": len(df),
            "columnas_archivo": cab, "peso": peso, "estrato": estrato,
            "upm": "upm" if "upm" in df.columns else None,
            "faltan": [c for c in REQUERIDAS if c not in df.columns] + ([] if peso else ["fac/fac_tri"])}
    return df, info


def poblacion_15(df):
    """Criterio del INEGI para indicadores: entrevista completa, residentes, 15 a 98 años."""
    return df[(df["r_def"] == 0) & (df["c_res"].isin([1, 3])) & (df["eda"].between(15, 98))].copy()


# ---------------------------------------------------------------- indicadores

def _var_razon(df, y, x, w, estrato, upm, dominio):
    """Varianza de R = sum(w*y*d)/sum(w*x*d) por linealización, con UPM dentro de estrato
    (aproximación con reemplazo, como en los diseños bietápicos del INEGI)."""
    import numpy as np
    d = dominio.astype(float)
    Y = (df[w] * df[y] * d).sum()
    X = (df[w] * df[x] * d).sum()
    if X == 0:
        return float("nan"), float("nan")
    R = Y / X
    z = df[w] * d * (df[y] - R * df[x]) / X
    tot = z.groupby([df[estrato], df[upm]]).sum()
    g = tot.groupby(level=0)
    n_h = g.size()
    centrado = tot - g.transform("mean")
    v_h = (centrado ** 2).groupby(level=0).sum() * n_h / (n_h - 1).replace(0, np.nan)
    return R, float(np.sqrt(v_h.fillna(0).sum()))


def indicadores(df, info, ciudades=None):
    """Tasas por ciudad (cd_a) más el agregado de las 39 ciudades."""
    import pandas as pd
    w, est, upm = info["peso"], info["estrato"], info["upm"]
    p = poblacion_15(df)
    p["pea"] = (p["clase1"] == 1).astype(int)
    p["ocup"] = (p["clase2"] == 1).astype(int)
    p["desoc"] = (p["clase2"] == 2).astype(int)
    p["inf"] = ((p["clase2"] == 1) & (p["emp_ppal"] == 1)).astype(int)
    p["si"] = ((p["clase2"] == 1) & (p["tue_ppal"] == 1)).astype(int)
    p["uno"] = 1
    codigos = sorted(c for c in p["cd_a"].dropna().unique() if 1 <= c <= 52)
    filas = []
    for nombre, dom in [("39 ciudades", p["cd_a"].between(1, 52))] + \
                       [(int(c), p["cd_a"] == c) for c in codigos if ciudades is None or int(c) in ciudades]:
        fila = {"cd_a": nombre, "muestra": int(dom.sum()),
                "pob15": float((p[w] * dom).sum()), "ocupados": float((p[w] * p["ocup"] * dom).sum())}
        for clave, (y, x) in {"participacion": ("pea", "uno"), "desocupacion": ("desoc", "pea"),
                              "informalidad": ("inf", "ocup"), "sector_informal": ("si", "ocup")}.items():
            if est and upm:
                r, se = _var_razon(p, y, x, w, est, upm, dom)
            else:
                r, se = (p[w] * p[y] * dom).sum() / max((p[w] * p[x] * dom).sum(), 1e-9), float("nan")
            fila[clave] = round(100 * r, 2)
            fila[clave + "_ic90"] = round(100 * 1.645 * se, 2) if se == se else None
        filas.append(fila)
    return pd.DataFrame(filas)


def escribe_json(ruta: Path, obj) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def resumen_github(texto: str) -> None:
    destino = os.environ.get("GITHUB_STEP_SUMMARY")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(texto + "\n")
