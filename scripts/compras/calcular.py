"""
Cifra Pública | Folio 005 | Paso 2. Proporciones del gasto por canal y forma de pago, con su margen de error.

Lee data/processed/compras/hogares_<año>.csv.gz (paso 1) y escribe en data/processed/compras/:

- indicadores.csv  una fila por año, dominio e indicador: proporción, error estándar, intervalo al 90%
                   y número de hogares en muestra
- cambios.csv      diferencia 2020→2024 y 2022→2024 de cada indicador, con su error y si es distinta de cero
- deciles.json     cortes de ingreso de los deciles nacionales de 2024 (trimestrales y mensuales)

Las proporciones son cocientes: gasto en el canal / gasto total con lugar de compra, con los factores de
expansión. El error estándar sale por linealización de Taylor con el diseño de la encuesta (estratos
est_dis, unidades primarias upm), como en los programas de cálculo del INEGI. Los dominios (Guanajuato, cada
decil) se estiman sin recortar la muestra: los hogares fuera del dominio cuentan con cero.
Entre ediciones las muestras son independientes: el error de una diferencia es la raíz de la suma de varianzas.

Uso:
    python scripts/compras/calcular.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[2]
DATOS = BASE / "data/processed/compras"
ANIOS = (2020, 2022, 2024)
Z90 = 1.645

L = {f"L{i:02d}" for i in range(1, 19)}
# Grupos de lugares de compra (claves del catálogo lugar_comp de la ENIGH)
GRUPOS = {
    "tiendita": [4],                    # tiendas de abarrotes
    "cadenas": [6, 7, 9, 10],           # supermercados, departamentales, clubes de precio, conveniencia
    "super": [6],
    "conveniencia": [10],
    "club": [9],
    "departamental": [7],
    "calle": [1, 2, 3],                 # mercado, tianguis, ambulantes
    "mercado": [1],
    "tianguis": [2],
    "ambulantes": [3],
    "especializada": [5],               # tiendas específicas del ramo
    "fuera": [11, 12, 13, 14],          # restaurantes, fondas, cafeterías, bares
    "particular": [17],
    "internet": [18],
    "otros": [8, 15, 16],               # fuera del país, Diconsa, Liconsa
}
PAGOS = {
    "efectivo": [1], "debito": [6], "credito": [5], "tarjeta": [5, 6], "fiado": [2],
    "transferencia": [4, 9],            # transferencia y pago móvil
    "otros_pago": [0, 3, 7, 8, 10],
}


def cols(pref, claves):
    return [f"{pref}{c:02d}" for c in claves]


def leer(anio: int) -> pd.DataFrame:
    d = pd.read_csv(DATOS / f"hogares_{anio}.csv.gz", dtype={"folioviv": str, "ent": str, "upm": str, "est_dis": str})
    d["X"] = d[sorted(L)].sum(axis=1)                       # total con lugar de compra
    d["XF"] = d[cols("F", range(1, 19))].sum(axis=1)        # comida para la casa con lugar de compra
    d["XT"] = d[cols("T", range(0, 11))].sum(axis=1)        # gasto en la tiendita
    d["psu"] = d.est_dis + "_" + d.upm
    return d


def cociente(d: pd.DataFrame, y: np.ndarray, x: np.ndarray, dom: np.ndarray) -> tuple[float, float, int]:
    """Cociente Σw·y / Σw·x en el dominio, con error estándar por linealización (estratos y UPM)."""
    w = d.factor.to_numpy(float) * dom
    X = (w * x).sum()
    if X <= 0:
        return np.nan, np.nan, 0
    R = (w * y).sum() / X
    z = w * (y - R * x) / X
    t = pd.DataFrame({"h": d.est_dis.to_numpy(), "p": d.psu.to_numpy(), "z": z}).groupby(["h", "p"], sort=False).z.sum().reset_index()
    g = t.groupby("h").z
    n = g.transform("size").to_numpy()
    dev = (t.z - g.transform("mean")).to_numpy()
    ok = n > 1  # estratos con una sola UPM no aportan varianza (en la ENIGH no los hay; se revisa abajo)
    var = (n[ok] / (n[ok] - 1) * dev[ok] ** 2).sum()
    return R, float(np.sqrt(var)), int((dom > 0).sum())


def dominios(d: pd.DataFrame) -> dict[str, np.ndarray]:
    out = {"mx": np.ones(len(d)), "gto": (d.ent == "11").to_numpy(float),
           "mx_urb": d.urb.to_numpy(float), "mx_rur": 1 - d.urb.to_numpy(float)}
    for k in range(1, 11):
        out[f"d{k}"] = (d.decil == k).to_numpy(float)
    return out


def main() -> None:
    filas = []
    for anio in ANIOS:
        d = leer(anio)
        unicos = d.groupby("est_dis").psu.nunique()
        if (unicos < 2).any():
            print(f"aviso {anio}: {int((unicos < 2).sum())} estratos con una sola UPM")
        X, XF, XT = d.X.to_numpy(), d.XF.to_numpy(), d.XT.to_numpy()
        for dn, dom in dominios(d).items():
            for g, cl in GRUPOS.items():
                filas.append((anio, dn, "canal", g, *cociente(d, d[cols("L", cl)].sum(axis=1).to_numpy(), X, dom)))
                filas.append((anio, dn, "comida", g, *cociente(d, d[cols("F", cl)].sum(axis=1).to_numpy(), XF, dom)))
            for g, cl in PAGOS.items():
                filas.append((anio, dn, "pago", g, *cociente(d, d[cols("P", cl)].sum(axis=1).to_numpy(), X, dom)))
            filas.append((anio, dn, "tiendita_pago", "efectivo", *cociente(d, d["T01"].to_numpy(), XT, dom)))
            # Gasto trimestral promedio por hogar con lugar de compra (pesos corrientes), solo como contexto
            w = d.factor.to_numpy() * dom
            filas.append((anio, dn, "contexto", "gasto_hogar", (w * X).sum() / w.sum(), np.nan, int((dom > 0).sum())))
        print(f"{anio}: listo")
    ind = pd.DataFrame(filas, columns=["anio", "dominio", "tema", "indicador", "p", "ee", "n"])
    ind["li90"] = ind.p - Z90 * ind.ee
    ind["ls90"] = ind.p + Z90 * ind.ee
    ind.to_csv(DATOS / "indicadores.csv", index=False, float_format="%.6f")

    a = ind.set_index(["dominio", "tema", "indicador", "anio"])[["p", "ee"]].unstack("anio")
    cam = []
    for base in (2020, 2022):
        dif = a[("p", 2024)] - a[("p", base)]
        ee = np.sqrt(a[("ee", 2024)] ** 2 + a[("ee", base)] ** 2)
        cam.append(pd.DataFrame({"desde": base, "dif": dif, "ee": ee, "z": dif / ee}).reset_index())
    cam = pd.concat(cam)
    cam["significativa_90"] = cam.z.abs() > Z90
    cam.to_csv(DATOS / "cambios.csv", index=False, float_format="%.6f")

    # Cortes de deciles de 2024: ingreso corriente trimestral del hogar (pesos de agosto de 2024)
    d = leer(2024).sort_values("ing_cor")
    cortes = [float(d.loc[d.decil == k, "ing_cor"].max()) for k in range(1, 10)]
    inpc = pd.read_csv(BASE / "data/fuentes/gasto/inpc_mensual.csv").set_index("anio")
    f = float(inpc.loc[2025, "dic"] / inpc.loc[2024, "ago"])
    json.dump({"trimestral_ago2024": cortes, "mensual_ago2024": [c / 3 for c in cortes],
               "mensual_dic2025": [c / 3 * f for c in cortes], "factor_inpc_ago2024_dic2025": f},
              open(DATOS / "deciles.json", "w"), indent=1)
    print("indicadores:", len(ind), "| cambios:", len(cam))


if __name__ == "__main__":
    main()
