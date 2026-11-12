"""
Cifra Pública — Gasto del Municipio de León.

Paso 1: extrae los estados analíticos del ejercicio del presupuesto de egresos de la
cuenta pública anual (Tesorería de León, 2016-2025) en dos clasificaciones:
  - funcional (finalidad y función, CFG)
  - por objeto del gasto (capítulo y concepto, COG)

Los archivos de 2016 y 2017 traen la clave CONAC; desde 2018 solo el nombre. El catálogo
de claves se arma con los de 2016 y los demás años se emparejan por nombre normalizado.
2021, capítulo y concepto: el anual no se puede descargar del sitio; se usa el del
4o trimestre (acumulado al cierre), que cuadra al peso con el funcional anual.

Uso:    python -I scripts/gasto/extraer.py
Salida: data/processed/gasto/egresos_leon.csv
"""
import csv
import re
import unicodedata
from pathlib import Path

import openpyxl

BASE = Path(__file__).resolve().parents[2]
RAW = BASE / "data" / "fuentes" / "gasto" / "cuenta_publica"
OUT = BASE / "data" / "processed" / "gasto"

FILES = {
    **{(y, "funcional"): f"leon_cuenta_publica_{y}_finalidad_funcion.xlsx" for y in range(2016, 2026)},
    **{(y, "objeto"): f"leon_cuenta_publica_{y}_capitulo_concepto.xlsx" for y in range(2016, 2026) if y != 2021},
    (2021, "objeto"): "leon_trimestre4_2021_objeto_del_gasto.xlsx",
}
COLS = ["aprobado", "ampliaciones", "modificado", "devengado", "pagado", "subejercicio"]
HEADER_KEYS = {"aprobado", "ampliaciones", "modificado", "devengado", "pagado"}
TOTAL_NAMES = {"presupuesto de egresos", "total del gasto", "total del egreso"}


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def read_rows(path: Path):
    """[(clave | None, nombre, {columna: valor})] en el orden del archivo."""
    ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    hdr = next(i for i, r in enumerate(rows)
               if any(isinstance(v, str) and v.strip().lower() == "aprobado" for v in r))
    pos = {}
    for j, v in enumerate(rows[hdr]):
        if isinstance(v, str):
            key = v.strip().lower().split()[0].split("/")[0]
            if key in HEADER_KEYS:
                pos[key] = j
    pos["subejercicio"] = pos["pagado"] + 1
    assert set(pos) == set(COLS), (path.name, pos)
    out = []
    for r in rows[hdr + 1:]:
        vals = {c: (r[j] if j < len(r) else None) for c, j in pos.items()}
        if sum(isinstance(v, (int, float)) for v in vals.values()) < 4:
            continue
        texts = [v for k, v in enumerate(r) if isinstance(v, str) and k < min(pos.values())]
        if not texts or texts[0].strip().startswith("3 = ("):  # fila de numeración de columnas
            continue
        code = r[0] if isinstance(r[0], (int, float)) and not isinstance(r[0], bool) else None
        clean = {c: float(vals[c]) if isinstance(vals[c], (int, float)) else 0.0 for c in COLS}
        out.append((int(code) if code is not None else None, texts[0].strip(), clean))
    return out


def catalog(clas: str) -> dict:
    return {norm(n): (c, n) for c, n, _ in read_rows(RAW / FILES[(2016, clas)]) if c != 900001}


def level(clas: str, code: int) -> str:
    if code == 0:
        return "total"
    if clas == "funcional":
        return "finalidad" if code < 10 else "funcion"
    return "capitulo" if code % 1000 == 0 else "concepto"


def main() -> None:
    cats = {c: catalog(c) for c in ("funcional", "objeto")}
    records, problems = [], []
    for (year, clas), fname in sorted(FILES.items()):
        cat = cats[clas]
        for code, name, vals in read_rows(RAW / fname):
            n = norm(name)
            if code == 900001 or n in TOTAL_NAMES:
                code, canon = 0, "Total"
            elif code is not None:
                canon = next((c[1] for c in cat.values() if c[0] == code), name)
            elif n in cat:
                code, canon = cat[n]
            else:
                problems.append((year, clas, name))
                continue
            records.append({"anio": year, "clasificacion": clas, "nivel": level(clas, code), "clave": code,
                            "nombre": canon, "nombre_original": name, **vals, "archivo": fname})
    if problems:
        raise SystemExit(f"Renglones sin emparejar con el catálogo: {problems}")
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "egresos_leon.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(records[0]))
        w.writeheader()
        w.writerows(records)
    print(f"{len(records)} filas -> {OUT / 'egresos_leon.csv'}")


if __name__ == "__main__":
    main()
