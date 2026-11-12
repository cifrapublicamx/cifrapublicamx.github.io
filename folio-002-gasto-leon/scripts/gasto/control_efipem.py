"""
Paso 4 (control): compara la cuenta pública (devengado por capítulo) contra la Estadística de
Finanzas Públicas Estatales y Municipales (EFIPEM) del INEGI.

La EFIPEM cuenta como egreso la «disponibilidad final» (lo que queda en caja al cierre); la
cuenta pública no. Sin ella, los dos totales deben coincidir.

Uso:    python -I scripts/gasto/control_efipem.py
Salida: data/processed/gasto/control_efipem.csv
"""
import unicodedata
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[2]
PROC = BASE / "data" / "processed" / "gasto"
EFIPEM = BASE / "data" / "fuentes" / "gasto" / "efipem_ciudades_2016_2025.csv"
CAP = {1000: "servicios personales", 2000: "materiales y suministros", 3000: "servicios generales",
       4000: "transferencias, asignaciones, subsidios y otras ayudas",
       5000: "bienes muebles, inmuebles e intangibles", 6000: "inversion publica",
       7000: "otros egresos", 8000: "participaciones y aportaciones", 9000: "deuda publica"}


def norm(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


cp = pd.read_csv(PROC / "egresos_leon.csv")
cp = cp[(cp.clasificacion == "objeto") & (cp.nivel == "capitulo")]
cp = cp.assign(cap=cp.clave.map(CAP)).pivot_table(index="cap", columns="anio", values="devengado", aggfunc="sum")
ef = pd.read_csv(EFIPEM, dtype={"CVEGEO": str})
ef = ef[(ef.CVEGEO == "11020") & (ef.TEMA == "Egresos") & ef.CATEGORIA.isin(["Capítulo", "Tema"])]
ef = ef.assign(cap=ef.DESCRIPCION_CATEGORIA.map(norm)).pivot_table(index="cap", columns="ANIO", values="VALOR", aggfunc="sum")

rows = []
for y in cp.columns:
    g = lambda c: 0 if pd.isna(ef[y].get(c, 0)) else ef[y].get(c, 0)
    disp, tot_ef, tot_cp = g("disponibilidad final"), g("total de egresos"), cp[y].sum()
    difs = {c: g(c) - (cp.at[c, y] if c in cp.index else 0) for c in CAP.values()}
    rows.append({"anio": y, "cuenta_publica_devengado": round(tot_cp), "efipem_total_egresos": round(tot_ef),
                 "efipem_disponibilidad_final": round(disp), "diferencia_sin_disponibilidad": round(tot_ef - disp - tot_cp),
                 "capitulos_que_difieren": "; ".join(f"{c}: {v / 1e6:+,.1f} mdp" for c, v in difs.items() if abs(v) >= 1000),
                 "estatus_efipem": "preliminar" if y == 2025 else "definitivo"})
res = pd.DataFrame(rows)
res.to_csv(PROC / "control_efipem.csv", index=False)
print(res.drop(columns="capitulos_que_difieren").to_string(index=False))
bad = res[res.diferencia_sin_disponibilidad.abs() > 1000]
if len(bad):
    raise SystemExit(f"No cuadran sin disponibilidad final: {list(bad.anio)}")
print("OK: sin disponibilidad final, la EFIPEM coincide con la cuenta pública todos los años.")
