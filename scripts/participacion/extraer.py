"""Análisis 006 | Participación por sección electoral.

Lee las bases de cómputos distritales del INE (2018 presidencia, 2021 diputaciones,
2024 presidencia), descarta casillas especiales, voto anticipado, voto desde el
extranjero y prisión preventiva, y suma votos y lista nominal por sección.

Uso: python extraer.py <carpeta_ine> <salida.csv>
"""
import json
import sys
from pathlib import Path

import pandas as pd

ARCHIVOS = {
    2018: ("Presidente2018.csv", "ID_ESTADO", "LISTA_NOMINAL_CASILLA"),
    2021: ("Diputados2021.csv", "ID_ESTADO", "LISTA_NOMINAL_CASILLA"),
    2024: ("PRES_2024.csv", "ID_ENTIDAD", "LISTA_NOMINAL"),
}
# B básica, C contigua, E extraordinaria: las únicas con lista nominal de la sección
TIPOS_SECCION = {"B", "C", "E"}


def limpia(s):
    return pd.to_numeric(
        s.astype(str).str.replace('="', "", regex=False).str.replace('"', "", regex=False)
        .str.replace("'", "", regex=False).str.replace(",", "", regex=False).str.strip(),
        errors="coerce",
    )


def lee(carpeta: Path, anio: int) -> pd.DataFrame:
    nombre, col_ent, col_ln = ARCHIVOS[anio]
    ruta = carpeta / nombre
    with open(ruta, encoding="latin1") as f:
        for i, linea in enumerate(f):
            if linea.startswith("CLAVE_CASILLA"):
                break
    df = pd.read_csv(ruta, sep="|", skiprows=i, encoding="latin1", dtype=str,
                     index_col=False, low_memory=False)
    df = df[df["TIPO_CASILLA"].str.strip().isin(TIPOS_SECCION)].copy()
    out = pd.DataFrame({
        "entidad": limpia(df[col_ent]).astype("Int64"),
        "seccion": limpia(df["SECCION"]).astype("Int64"),
        "votos": limpia(df["TOTAL_VOTOS_CALCULADOS"]),
        "lista": limpia(df[col_ln]),
        "urbana": (df["CASILLA"].str.strip() == "Urbana").astype(int),
        "obs": df["OBSERVACIONES"].fillna(""),
    })
    # actas sin datos (paquete no recibido, casilla no instalada) no cuentan
    sin_acta = out["obs"].str.contains("no recibido|no instalada", case=False)
    out = out[~sin_acta & out["lista"].gt(0) & out["votos"].notna()]
    g = out.groupby(["entidad", "seccion"]).agg(
        votos=("votos", "sum"), lista=("lista", "sum"),
        casillas=("votos", "size"), urbana=("urbana", "mean"),
    ).reset_index()
    g["anio"] = anio
    tot = g[["votos", "lista"]].sum()
    print(f"{anio}: {len(g):,} secciones | {tot.votos:,.0f} votos / {tot.lista:,.0f} lista "
          f"= {100 * tot.votos / tot.lista:.2f}% (sin especiales ni extranjero)")
    return g


def oficial(carpeta: Path, anio: int) -> dict:
    """Totales del encabezado del INE (todas las actas, con especiales y extranjero)."""
    with open(carpeta / ARCHIVOS[anio][0], encoding="latin1") as f:
        lineas = [next(f) for _ in range(8)]
    i = next(k for k, l in enumerate(lineas) if l.startswith("ACTAS_ESPERADAS"))
    v = lineas[i + 1].strip().split("|")
    return {"lista": int(v[3].replace(",", "")), "votos": int(v[4].replace(",", "")),
            "participacion": float(v[5])}


def main():
    carpeta, salida = Path(sys.argv[1]), Path(sys.argv[2])
    todo = pd.concat([lee(carpeta, a) for a in ARCHIVOS])
    todo.to_csv(salida, index=False)
    of = {a: oficial(carpeta, a) for a in ARCHIVOS}
    (salida.parent / "oficiales_ine.json").write_text(json.dumps(of, indent=1))
    print("Totales oficiales del INE:", {a: v["participacion"] for a, v in of.items()})


if __name__ == "__main__":
    main()
