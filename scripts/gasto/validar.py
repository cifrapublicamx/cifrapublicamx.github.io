"""
Paso 2: revisa la tabla extraída. Falla (código de salida 1) si:
  - a algún año le faltan claves o tiene duplicadas,
  - un subtotal no es la suma de sus renglones (tolerancia: un peso) en aprobado o devengado,
  - el total devengado funcional no coincide con el de objeto del gasto.
Inconsistencias de origen conocidas (se reportan, no fallan): ver CONOCIDAS.

Uso: python -I scripts/gasto/validar.py
"""
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[2]
df = pd.read_csv(BASE / "data" / "processed" / "gasto" / "egresos_leon.csv")
COLS = ["aprobado", "modificado", "devengado", "pagado"]
# (año, clasificación, clave padre, columna): en el archivo de 2016 la finalidad 3 no suma
# los 487,934.19 de «Combustibles y Energía» en el modificado. No afecta el devengado.
CONOCIDAS = {(2016, "funcional", 3, "modificado"), (2016, "funcional", 3, "ampliaciones")}
errores = []

for clas, g in df.groupby("clasificacion"):
    base = set(g[g.anio == g.anio.min()].clave)
    for y, gy in g.groupby("anio"):
        if len(gy) != gy.clave.nunique() or set(gy.clave) != base:
            errores.append(f"claves {clas} {y}")


def parent(clas, code):
    if code == 0:
        return None
    if clas == "funcional":
        return 0 if code < 10 else code // 10
    return 0 if code % 1000 == 0 else code // 1000 * 1000


df["padre"] = [parent(c, k) for c, k in zip(df.clasificacion, df.clave)]
for (y, clas), g in df.groupby(["anio", "clasificacion"]):
    idx = g.set_index("clave")
    for p, row in g.dropna(subset=["padre"]).groupby("padre")[COLS].sum().iterrows():
        for c in COLS:
            if abs(row[c] - idx.at[p, c]) > 1:
                (print if (y, clas, int(p), c) in CONOCIDAS else errores.append)(
                    f"suma {y} {clas} padre={int(p)} {c}: difiere {row[c] - idx.at[p, c]:,.2f}")

tot = df[df.clave == 0].pivot_table(index="anio", columns="clasificacion", values="devengado")
for y, r in tot.iterrows():
    if abs(r.funcional - r.objeto) > 1:
        errores.append(f"total {y}: funcional {r.funcional:,.2f} vs objeto {r.objeto:,.2f}")

print((tot / 1e6).round(1).to_string())
if errores:
    raise SystemExit("ERRORES:\n" + "\n".join(errores))
print("OK: claves completas, sumas y totales cuadran.")
