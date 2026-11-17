"""
Cifra Pública | Folio 003 | Ocupación e informalidad en México (ENOE, INEGI)

Módulo común: arma la dirección de los microdatos de cada trimestre, los descarga, lee la tabla
sociodemográfica (SDEM) y calcula los indicadores laborales con su margen de error para el total
nacional, las 32 entidades, los cuatro tamaños de localidad y las 39 ciudades.

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
- Tamaño de localidad: T_LOC en 2019 y T_LOC_TRI desde 2020 T3 (1 = 100 mil y más habitantes,
  2 = 15 mil a 99 999, 3 = 2 500 a 14 999, 4 = menos de 2 500). Revisado en las columnas reales
  de 2019 T4, 2021 T4 y 2026 T2 (data/fuentes/enoe/sondeo/columnas_*.json).

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
            "ing7c", "hrsocup", "fac", "fac_tri", "upm", "est_d_tri", "est_d", "est", "t_loc",
            "t_loc_tri"]
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
    """¿Existe el zip? El INEGI responde 200 también a archivos que no existen (con una página
    HTML) y su HEAD no trae tamaño. Así que se piden los primeros bytes: un zip empieza con «PK».
    Devuelve estado HTTP, si es zip, tamaño (si el servidor lo dice) y tipo."""
    try:
        with s.get(url, headers={"Range": "bytes=0-3"}, stream=True, timeout=(15, 45),
                   allow_redirects=True) as r:
            inicio = next(r.iter_content(4), b"")
            total = None
            rango = r.headers.get("Content-Range", "")           # «bytes 0-3/35123456»
            if "/" in rango and rango.rsplit("/", 1)[1].isdigit():
                total = int(rango.rsplit("/", 1)[1])
            elif r.status_code == 200 and r.headers.get("Content-Length", "").isdigit():
                total = int(r.headers["Content-Length"])
            return {"estado": r.status_code, "zip": inicio[:2] == b"PK", "bytes": total,
                    "tipo": r.headers.get("Content-Type", ""), "url_final": r.url}
    except requests.RequestException as e:
        return {"estado": None, "zip": False,
                "error": f"{type(e).__name__}: {' '.join(str(e).split())[:200]}"}


def disponible(c: dict) -> bool:
    return c.get("estado") in (200, 206) and c.get("zip", False)


def ultimo_disponible(s, hasta=None, atras=6) -> tuple[int, int] | None:
    """El trimestre más reciente que ya está publicado (prueba hacia atrás desde hoy)."""
    for a, t in reversed(trimestres((2019, 1), hasta)[-atras:]):
        c = consulta(s, url_trimestre(a, t))
        log(f"¿{etiqueta(a, t)}? HTTP {c.get('estado')} | zip: {c.get('zip')} | {c.get('bytes')} bytes")
        if disponible(c):
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
    localidad = "t_loc_tri" if "t_loc_tri" in df.columns else ("t_loc" if "t_loc" in df.columns else None)
    if localidad == "t_loc_tri":
        df = df.drop(columns=["t_loc"], errors="ignore").rename(columns={"t_loc_tri": "t_loc"})
    peso = "fac_tri" if "fac_tri" in df.columns else ("fac" if "fac" in df.columns else None)
    estrato = next((c for c in ("est_d_tri", "est_d", "est") if c in df.columns), None)
    info = {"tabla": nombre, "codificacion": cod, "separador": sep, "filas": len(df),
            "columnas_archivo": cab, "peso": peso, "estrato": estrato,
            "upm": "upm" if "upm" in df.columns else None, "localidad": localidad,
            "faltan": [c for c in REQUERIDAS if c not in df.columns] + ([] if peso else ["fac/fac_tri"])}
    return df, info


def poblacion_15(df):
    """Criterio del INEGI para indicadores: entrevista completa, residentes, 15 a 98 años."""
    return df[(df["r_def"] == 0) & (df["c_res"].isin([1, 3])) & (df["eda"].between(15, 98))].copy()


# ---------------------------------------------------------------- indicadores

# Ciudades que entraron a la ENOE en 2020 T1 (Coatzacoalcos, Ciudad del Carmen, Tapachula). Para comparar
# contra 2019 se usa el agregado de las 36 ciudades que están en toda la serie.
NUEVAS_2020 = {30, 42, 52}
CDMX = 1                                   # CD_A de la Ciudad de México (zona metropolitana)
LOCALIDADES = {1: "100 mil y más habitantes", 2: "15 mil a 99 999 habitantes",
               3: "2 500 a 14 999 habitantes", 4: "Menos de 2 500 habitantes"}
TASAS = {  # nombre: (numerador, denominador)
    "participacion": ("pea", "uno"),
    "desocupacion": ("desoc", "pea"),
    "informalidad": ("inf", "ocup"),
    "sector_informal": ("si", "ocup"),
}


def prepara(df, info):
    """Población de 15+ con las variables 0/1 que usan las tasas y la clave de UPM dentro de estrato."""
    import pandas as pd
    p = poblacion_15(df)
    p["pea"] = (p["clase1"] == 1).astype("int8")
    p["ocup"] = (p["clase2"] == 1).astype("int8")
    p["desoc"] = (p["clase2"] == 2).astype("int8")
    p["inf"] = ((p["clase2"] == 1) & (p["emp_ppal"] == 1)).astype("int8")
    p["si"] = ((p["clase2"] == 1) & (p["tue_ppal"] == 1)).astype("int8")
    p["uno"] = 1
    p["_w"] = p[info["peso"]].astype(float)
    if info["estrato"] and info["upm"]:
        est, upm = p[info["estrato"]].fillna(-1), p[info["upm"]].fillna(-1)
        p["_h"] = p.groupby(est, sort=False).ngroup().to_numpy()
        p["_u"] = p.groupby([est, upm], sort=False).ngroup().to_numpy()
    return p.reset_index(drop=True)


def _razon(p, y, x, dom):
    """R = sum(w*y*d)/sum(w*x*d) y su error estándar por linealización (UPM dentro de estrato,
    aproximación con reemplazo, como en los diseños bietápicos del INEGI)."""
    import numpy as np
    d = dom.to_numpy(dtype=float)
    w = p["_w"].to_numpy()
    yv = p[y].to_numpy(dtype=float)
    xv = p[x].to_numpy(dtype=float)
    Y, X = (w * yv * d).sum(), (w * xv * d).sum()
    if X == 0:
        return float("nan"), float("nan")
    R = Y / X
    if "_u" not in p:
        return R, float("nan")
    z = w * d * (yv - R * xv) / X
    zu = np.bincount(p["_u"].to_numpy(), weights=z)                     # total por UPM
    h_de_u = np.zeros(len(zu), dtype=int)
    h_de_u[p["_u"].to_numpy()] = p["_h"].to_numpy()                    # estrato de cada UPM
    n_h = np.bincount(h_de_u)
    media_h = np.bincount(h_de_u, weights=zu) / np.maximum(n_h, 1)
    dev2 = np.bincount(h_de_u, weights=(zu - media_h[h_de_u]) ** 2)
    factor = np.where(n_h > 1, n_h / np.maximum(n_h - 1, 1), 0.0)
    return R, float(np.sqrt((factor * dev2).sum()))


def tasas(p, dom, cuales=TASAS) -> dict:
    """Tasas en % con su intervalo de 90% (± puntos), muestra y totales del dominio."""
    w = p["_w"]
    fila = {"muestra": int(dom.sum()), "pob15": float((w * dom).sum()),
            "pea": float((w * p["pea"] * dom).sum()), "ocupados": float((w * p["ocup"] * dom).sum()),
            "desocupados": float((w * p["desoc"] * dom).sum()),
            "informales": float((w * p["inf"] * dom).sum())}
    for nombre, (y, x) in cuales.items():
        r, se = _razon(p, y, x, dom)
        fila[nombre] = round(100 * r, 2) if r == r else None
        fila[nombre + "_ic90"] = round(100 * 1.645 * se, 2) if se == se else None
    return fila


def dominios_ciudades(p, solo=None):
    """[(etiqueta, máscara)]: agregado de 39 ciudades (solo desde 2020, cuando existen las 39), agregado
    comparable de 36, el de 36 sin la Ciudad de México y cada ciudad."""
    codigos = sorted(int(c) for c in p["cd_a"].dropna().unique() if 1 <= c <= 52)
    en_ciudad = p["cd_a"].between(1, 52)
    c36 = en_ciudad & ~p["cd_a"].isin(NUEVAS_2020)
    out = [("39 ciudades", en_ciudad)] if p["cd_a"].isin(NUEVAS_2020).any() else []
    out += [("36 ciudades", c36), ("36 ciudades sin Ciudad de México", c36 & (p["cd_a"] != CDMX))]
    out += [(c, p["cd_a"] == c) for c in codigos if solo is None or c in solo]
    return out


def dominios_nacionales(p):
    """[(dominio, clave, máscara)]: total nacional, cada entidad (CVE_ENT 1–32) y cada tamaño de localidad."""
    import pandas as pd
    out = [("nacional", "0", pd.Series(True, index=p.index))]
    if "cve_ent" in p.columns:
        out += [("entidad", str(k), p["cve_ent"] == k)
                for k in sorted(int(e) for e in p["cve_ent"].dropna().unique() if 1 <= e <= 32)]
    if "t_loc" in p.columns:
        out += [("localidad", str(k), p["t_loc"] == k)
                for k in sorted(int(e) for e in p["t_loc"].dropna().unique() if k_valida(e))]
    return out


def k_valida(e) -> bool:
    return 1 <= e <= 4 and float(e).is_integer()


def entidades() -> dict[str, dict]:
    """Catálogo de entidades: clave (sin ceros) → {entidad, nombre_corto}."""
    import csv
    archivo = FUENTES / "entidades.csv"
    return {str(int(f["cve_ent"])): f for f in csv.DictReader(archivo.open(encoding="utf-8"))}


def indicadores(df, info, ciudades=None):
    """Tasas por ciudad (cd_a) más los agregados. Lo usa el sondeo."""
    import pandas as pd
    p = prepara(df, info)
    return pd.DataFrame([{"cd_a": et, **tasas(p, dom)} for et, dom in dominios_ciudades(p, ciudades)])


def escribe_json(ruta: Path, obj) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def resumen_github(texto: str) -> None:
    destino = os.environ.get("GITHUB_STEP_SUMMARY")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(texto + "\n")
