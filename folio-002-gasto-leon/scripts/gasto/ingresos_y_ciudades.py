"""
Paso 4b: ingresos de León y comparación con otras ciudades, con la Estadística de Finanzas
Públicas Estatales y Municipales (EFIPEM) del INEGI.

- Ingresos de León por origen, 2016-2025 (2025 son cifras preliminares).
- León, Querétaro, Puebla y Tijuana en el último año con cifras definitivas: gasto por habitante
  sin disponibilidad final ni pago de deuda, ingresos propios, impuestos sobre el patrimonio,
  peso de la nómina y de la obra pública.
- Población de cada ciudad a mitad del año: interpolación log-lineal entre el Censo 2020
  (15 de marzo) y la Encuesta Intercensal 2025 (punto medio del levantamiento, 25 de octubre).

Uso:    python -I scripts/gasto/ingresos_y_ciudades.py
Salida: data/processed/gasto/ingresos_leon.csv, data/processed/gasto/comparativo_ciudades.csv
"""
import math
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[2]
SRC = BASE / "data" / "fuentes" / "gasto"
PROC = BASE / "data" / "processed" / "gasto"
PROPIOS = ["Impuestos", "Derechos", "Productos", "Aprovechamientos", "Contribuciones de Mejoras"]
T0 = 2020 + (pd.Timestamp("2020-03-15").dayofyear - 0.5) / 366
T1 = 2025 + (pd.Timestamp("2025-10-25").dayofyear - 0.5) / 365

ef = pd.read_csv(SRC / "efipem_ciudades_2016_2025.csv", dtype={"CVEGEO": str})
ef = ef[ef.CATEGORIA.isin(["Tema", "Capítulo", "Concepto"])]
pob = pd.read_csv(SRC / "poblacion_ciudades.csv", dtype={"cvegeo": str}).set_index("cvegeo")


def valor(s, tema, desc):
    return float(s[(s.TEMA == tema) & (s.DESCRIPCION_CATEGORIA == desc)].VALOR.sum())


def poblacion(cvegeo, year):
    p0, p1 = pob.at[cvegeo, "censo_2020"], pob.at[cvegeo, "eic_2025"]
    return p0 * math.exp(math.log(p1 / p0) / (T1 - T0) * (year + 0.5 - T0))


# ---------- ingresos de León ----------
real = pd.read_csv(PROC / "deflactor_poblacion.csv").set_index("anio")
rows = []
for y, s in ef[ef.CVEGEO == "11020"].groupby("ANIO"):
    if y not in real.index:
        continue
    fin_emp, fin_def = valor(s, "Ingresos", "Empréstitos"), valor(s, "Ingresos", "Déficit")
    r = {"anio": int(y), "estatus": s.ESTATUS.iloc[0],
         "total": valor(s, "Ingresos", "Total de ingresos"),
         "propios": sum(valor(s, "Ingresos", k) for k in PROPIOS),
         "impuestos": valor(s, "Ingresos", "Impuestos"),
         "patrimonio": valor(s, "Ingresos", "Impuestos sobre el Patrimonio"),
         "participaciones": valor(s, "Ingresos", "Participaciones federales"),
         "aportaciones": valor(s, "Ingresos", "Aportaciones federales y estatales"),
         "financiamiento": valor(s, "Ingresos", "Financiamiento"),
         "emprestitos": fin_emp, "deficit": fin_def}
    f, p = real.at[y, "factor_a_2025"], real.at[y, "poblacion"]
    for k in ["total", "propios", "patrimonio", "participaciones", "aportaciones", "financiamiento"]:
        r[f"{k}_real_pc"] = r[k] * f / p
    rows.append(r)
ing = pd.DataFrame(rows)
ing.to_csv(PROC / "ingresos_leon.csv", index=False)

# ---------- comparativo de ciudades ----------
defin = ef[ef.ESTATUS.str.contains("Definitiv", case=False)]
anio = int(defin.groupby("CVEGEO").ANIO.max().min())  # último año definitivo para las cuatro
rows = []
for c, s in ef[ef.ANIO == anio].groupby("CVEGEO"):
    eg = valor(s, "Egresos", "Total de egresos") - valor(s, "Egresos", "Disponibilidad final")
    deuda, P = valor(s, "Egresos", "Deuda pública"), poblacion(c, anio)
    tot = valor(s, "Ingresos", "Total de ingresos")
    propios = sum(valor(s, "Ingresos", k) for k in PROPIOS)
    rows.append({"anio": anio, "cvegeo": c, "ciudad": pob.at[c, "ciudad"], "poblacion": round(P),
                 "gasto_sin_deuda_pc": (eg - deuda) / P, "deuda_pc": deuda / P, "deuda_mdp": deuda / 1e6,
                 "financiamiento_mdp": valor(s, "Ingresos", "Financiamiento") / 1e6,
                 "propios_pc": propios / P, "patrimonio_pc": valor(s, "Ingresos", "Impuestos sobre el Patrimonio") / P,
                 "propios_pct": 100 * propios / tot,
                 "nomina_pct": 100 * valor(s, "Egresos", "Servicios personales") / eg,
                 "obra_pct": 100 * valor(s, "Egresos", "Inversión pública") / eg})
cmp_ = pd.DataFrame(rows).sort_values("gasto_sin_deuda_pc", ascending=False)
cmp_.to_csv(PROC / "comparativo_ciudades.csv", index=False)

pd.set_option("display.width", 200)
print(ing[["anio", "estatus", "total", "propios", "financiamiento"]].assign(
    propios_pct=lambda d: (100 * d.propios / d.total).round(1)).to_string(index=False))
print(f"\nComparativo {anio}:")
print(cmp_.round(1).drop(columns=["cvegeo"]).to_string(index=False))
