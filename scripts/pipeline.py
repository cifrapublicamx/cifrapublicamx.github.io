"""
Cifra Pública — Negocios de León por zona y giro.

Paso 1: lee una versión del DENUE de Guanajuato (CSV de descarga masiva de INEGI),
filtra el municipio de León, asigna cada establecimiento a un hexágono H3 y a un giro,
y guarda una tabla ligera por versión (un renglón por establecimiento).

Uso:
    python -I pipeline.py <ruta_csv_denue> <version>   # p. ej. 2019-11, 2024-11, 2026-05
"""
import re
import sys
import unicodedata
from pathlib import Path

import h3
import pandas as pd

CVE_ENT, CVE_MUN = "11", "020"          # Guanajuato, León
H3_RES = 8                              # hexágonos de ~0.74 km² (lado ~460 m)
CAJA_LEON = dict(lat=(20.85, 21.35), lon=(-101.95, -101.35))  # descarta coordenadas absurdas

# Giros: código SCIAN de 6 dígitos -> nombre corto. compara.py revisa que existan en ambas versiones.
GIROS = {
    **{c: "Restaurantes" for c in ["722511", "722512", "722513", "722514",
                                   "722516", "722517", "722518", "722519"]},
    "722515": "Cafeterías y neverías",
    "464111": "Farmacias", "464112": "Farmacias",
    "713943": "Gimnasios",
    "812110": "Estéticas y peluquerías",
    # Abarrotes y minisúpers van juntos: INEGI movió ~385 negocios de León entre ambos códigos
    # de 11/2024 a 05/2026, así que por separado la comparación no es confiable.
    "461110": "Abarrotes y minisúpers", "462112": "Abarrotes y minisúpers",
}

COLUMNAS = ["id", "nom_estab", "codigo_act", "nombre_act", "per_ocu", "nomb_asent",
            "cve_ent", "cve_mun", "cve_loc", "localidad", "latitud", "longitud", "fecha_alta"]

BASE = Path(__file__).resolve().parent.parent
SALIDA = BASE / "data" / "processed"


def clave_colonia(nombre: str) -> str:
    """Llave para agrupar variantes del mismo nombre: 'Barrio del Coecillo' = 'El Coecillo' = 'Coecillo'."""
    s = unicodedata.normalize("NFKD", nombre.lower()).encode("ascii", "ignore").decode()
    s = re.sub(r"^(barrio( de| del)?|colonia|col\.?|fraccionamiento|fracc\.?)\s+", "", s.strip())
    s = re.sub(r"^(el|la|los|las)\s+", "", s)
    return re.sub(r"\s+", " ", s).strip()


MINUSCULAS = {"de", "del", "la", "las", "los", "el", "y", "e", "en", "a"}
ROMANOS = re.compile(r"^(i{1,3}|iv|v|vi{0,3}|ix|x{1,3})$", re.I)


def estilo_nombre(nombre: str) -> str:
    """'VALLE DEL REAL II' -> 'Valle del Real II' (title case con conectores en minúscula)."""
    palabras = nombre.split()
    out = []
    for i, w in enumerate(palabras):
        if ROMANOS.match(w):
            out.append(w.upper())
        elif i > 0 and w.lower() in MINUSCULAS:
            out.append(w.lower())
        else:
            out.append(w[:1].upper() + w[1:].lower())
    return " ".join(out)


def leer_leon(ruta: str) -> tuple[pd.DataFrame, dict]:
    df = pd.read_csv(ruta, encoding="latin1", dtype=str, usecols=lambda c: c.lower() in COLUMNAS)
    df.columns = [c.lower() for c in df.columns]
    rep = {"filas_gto": len(df)}
    df = df[(df.cve_ent.str.zfill(2) == CVE_ENT) & (df.cve_mun.str.zfill(3) == CVE_MUN)].copy()
    rep["filas_leon"] = len(df)
    df["lat"] = pd.to_numeric(df.latitud, errors="coerce")
    df["lon"] = pd.to_numeric(df.longitud, errors="coerce")
    ok = df.lat.between(*CAJA_LEON["lat"]) & df.lon.between(*CAJA_LEON["lon"])
    rep["descartadas_coordenadas"] = int((~ok).sum())
    df = df[ok].copy()
    df["codigo_act"] = df.codigo_act.str.strip()
    df["giro"] = df.codigo_act.map(GIROS)
    df["hex"] = [h3.latlng_to_cell(la, lo, H3_RES) for la, lo in zip(df.lat, df.lon)]
    df["colonia"] = df.nomb_asent.fillna("").str.strip().map(estilo_nombre).replace({"Ninguno": ""})
    df["colonia_clave"] = df.colonia.map(clave_colonia)
    rep["filas_finales"] = len(df)
    rep["en_giros"] = int(df.giro.notna().sum())
    return df, rep


def main(ruta: str, version: str) -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    df, rep = leer_leon(ruta)
    cols = ["id", "hex", "giro", "codigo_act", "per_ocu", "colonia", "colonia_clave", "fecha_alta"]
    df[cols].to_csv(SALIDA / f"leon_{version}.csv.gz", index=False)
    (df.groupby(["codigo_act", "nombre_act"]).size().rename("n").reset_index()
       .to_csv(SALIDA / f"codigos_{version}.csv", index=False))
    print(f"[{version}]", rep)
    print(f"[{version}] hexágonos: {df.hex.nunique()} | por giro:",
          df.giro.value_counts().to_dict())


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
