"""
Paso 3: pasa el gasto a pesos de 2025 y por habitante.

- Deflactor: promedio anual del INPC (INEGI, base 2a quincena de julio de 2018 = 100),
  en data/fuentes/gasto/inpc_mensual.csv.
- Población a mitad de cada año: interpolación log-lineal entre la Encuesta Intercensal 2015,
  el Censo 2020 y la Encuesta Intercensal 2025 (data/fuentes/gasto/poblacion_anclas.csv),
  cada una en su fecha de referencia.

Uso:    python -I scripts/gasto/reales.py
Salida: data/processed/gasto/egresos_leon_real.csv, data/processed/gasto/deflactor_poblacion.csv
"""
import math
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[2]
SRC = BASE / "data" / "fuentes" / "gasto"
PROC = BASE / "data" / "processed" / "gasto"
ANIO_BASE = 2025
MONEY = ["aprobado", "ampliaciones", "modificado", "devengado", "pagado", "subejercicio"]

inpc = pd.read_csv(SRC / "inpc_mensual.csv").set_index("anio").mean(axis=1)
factor = inpc[ANIO_BASE] / inpc

anc = pd.read_csv(SRC / "poblacion_anclas.csv", parse_dates=["fecha_referencia"])
pts = [(d.year + (d.dayofyear - 0.5) / (366 if d.is_leap_year else 365), p)
       for d, p in zip(anc.fecha_referencia, anc.poblacion)]


def poblacion(year: int) -> float:
    t = year + 0.5
    for i, ((t0, p0), (t1, p1)) in enumerate(zip(pts, pts[1:])):
        if t <= t1 or i == len(pts) - 2:
            return p0 * math.exp(math.log(p1 / p0) / (t1 - t0) * (t - t0))


df = pd.read_csv(PROC / "egresos_leon.csv")
aux = pd.DataFrame({"anio": sorted(df.anio.unique())})
aux["inpc_promedio"] = aux.anio.map(inpc)
aux["factor_a_2025"] = aux.anio.map(factor)
aux["poblacion"] = aux.anio.map(poblacion).round().astype(int)
aux.to_csv(PROC / "deflactor_poblacion.csv", index=False)

df = df.merge(aux, on="anio")
for c in MONEY:
    df[f"{c}_real"] = df[c] * df.factor_a_2025
df["devengado_real_pc"] = df.devengado_real / df.poblacion
df.to_csv(PROC / "egresos_leon_real.csv", index=False)
print(aux.round(4).to_string(index=False))
