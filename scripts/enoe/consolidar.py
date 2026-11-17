"""
Cifra Pública | Folio 003 | Junta los trimestres de la ENOE y escribe el control.

Lee data/processed/enoe/trimestral/*/ y escribe en data/processed/enoe/:
- ciudades_trimestral.csv   todas las ciudades y agregados, todos los trimestres
- desgloses_trimestral.csv  León y comparables por sexo y sector, todos los trimestres
- control.md                cobertura, cuadre contra lo publicado por el INEGI, último trimestre
                            contra hace un año y contra 2019 (mismo trimestre), y lugar de León
                            entre las 39 ciudades. Es también el texto del PR.

Un cambio «se distingue» si es mayor que su margen de 90%: raíz de la suma de los cuadrados de
los dos márgenes. Trata los dos trimestres como muestras independientes; la ENOE repite una
parte de las viviendas (panel rotatorio), así que el criterio es conservador.

Uso:
    python scripts/enoe/consolidar.py
"""
from __future__ import annotations

import csv
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inegi  # noqa: E402
from extraer import TRIMESTRAL, hechos  # noqa: E402

import pandas as pd  # noqa: E402


def nombres() -> dict[str, dict]:
    archivo = inegi.FUENTES / "ciudades.csv"
    return {str(int(f["cd_a"])): f for f in csv.DictReader(archivo.open(encoding="utf-8"))}


def f1(x):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.1f}"


def compara(a, b, ic_a, ic_b):
    """(diferencia, margen, ¿se distingue?) de a − b."""
    if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in (a, b, ic_a, ic_b)):
        return None, None, None
    d = a - b
    m = math.sqrt(ic_a ** 2 + ic_b ** 2)
    return d, m, abs(d) > m


def texto_cambio(d, m, si):
    if d is None:
        return "—"
    return f"{d:+.1f} (± {m:.1f}) {'**sí**' if si else 'no se distingue'}"


def main() -> int:
    trims = sorted(hechos())
    if not trims:
        print("No hay trimestres extraídos todavía.")
        return 0
    cat = nombres()
    partes_c, partes_d, metas = [], [], {}
    for a, t in trims:
        d = TRIMESTRAL / f"{a}-T{t}"
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        metas[(a, t)] = meta
        c = pd.read_csv(d / "ciudades.csv", dtype={"cd_a": str})
        c.insert(0, "encuesta", meta["encuesta"])
        c.insert(0, "trimestre", f"{a}-T{t}")
        c.insert(0, "trim", t)
        c.insert(0, "anio", a)
        partes_c.append(c)
        if (d / "desgloses.csv").exists() and (d / "desgloses.csv").stat().st_size > 5:
            g = pd.read_csv(d / "desgloses.csv", dtype={"cd_a": str})
            g.insert(0, "trimestre", f"{a}-T{t}")
            g.insert(0, "trim", t)
            g.insert(0, "anio", a)
            partes_d.append(g)
    ciu = pd.concat(partes_c, ignore_index=True)
    ciu.insert(5, "ciudad", ciu["cd_a"].map(lambda x: cat.get(x, {}).get("ciudad", x)))
    ciu.to_csv(inegi.PROCESADO / "ciudades_trimestral.csv", index=False)
    if partes_d:
        des = pd.concat(partes_d, ignore_index=True)
        des.insert(4, "ciudad", des["cd_a"].map(lambda x: cat.get(x, {}).get("ciudad", x)))
        des.to_csv(inegi.PROCESADO / "desgloses_trimestral.csv", index=False)

    def valor(a, t, cd, col):
        r = ciu[(ciu["anio"] == a) & (ciu["trim"] == t) & (ciu["cd_a"] == cd)]
        if r.empty or pd.isna(r[col].iloc[0]):
            return None
        return float(r[col].iloc[0])

    ua, ut = trims[-1]
    L = [f"# ENOE | control al {ua}-T{ut}", "",
         f"Generado {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. "
         f"{len(trims)} trimestres, de {trims[0][0]}-T{trims[0][1]} a {ua}-T{ut}.", ""]

    # Último trimestre
    elegidas = ["5"] + [k for k, f in cat.items() if f.get("papel") == "comparable"]
    L += [f"## {ua}-T{ut}: León y comparables", "",
          "| | Informalidad % | contra hace un año | contra el mismo trimestre de 2019 | Participación % | Desocupación % |",
          "|---|---|---|---|---|---|"]
    for cd in elegidas + ["39 ciudades", "36 ciudades"]:
        inf, ic = valor(ua, ut, cd, "informalidad"), valor(ua, ut, cd, "informalidad_ic90")
        ref19 = "36 ciudades" if cd == "39 ciudades" else cd       # 2019 solo tiene 36
        prev = compara(inf, valor(ua - 1, ut, cd, "informalidad"), ic, valor(ua - 1, ut, cd, "informalidad_ic90"))
        v19 = compara(inf if cd != "39 ciudades" else valor(ua, ut, "36 ciudades", "informalidad"),
                      valor(2019, ut, ref19, "informalidad"),
                      ic if cd != "39 ciudades" else valor(ua, ut, "36 ciudades", "informalidad_ic90"),
                      valor(2019, ut, ref19, "informalidad_ic90"))
        nombre = cat.get(cd, {}).get("ciudad", cd)
        L.append(f"| {'**' + nombre + '**' if cd == '5' else nombre} | {f1(inf)} ± {f1(ic)} | {texto_cambio(*prev)} | "
                 f"{texto_cambio(*v19)}{' (36 ciudades)' if cd == '39 ciudades' else ''} | "
                 f"{f1(valor(ua, ut, cd, 'participacion'))} | {f1(valor(ua, ut, cd, 'desocupacion'))} |")
    L += ["", "«Se distingue» = la diferencia es mayor que su margen de 90%.", ""]

    # Lugar de León entre las 39
    ult = ciu[(ciu["anio"] == ua) & (ciu["trim"] == ut) & ciu["cd_a"].str.fullmatch(r"\d+")]
    L += ["## Lugar de León entre las ciudades (1 = la más alta)", ""]
    for col, nombre in (("informalidad", "Informalidad"), ("participacion", "Participación"),
                        ("desocupacion", "Desocupación")):
        orden = ult.sort_values(col, ascending=False).reset_index(drop=True)
        pos = orden.index[orden["cd_a"] == "5"]
        if len(pos):
            L.append(f"- {nombre}: lugar {pos[0] + 1} de {len(orden)} "
                     f"(más alta: {orden['ciudad'].iloc[0]} {orden[col].iloc[0]:.1f}; "
                     f"más baja: {orden['ciudad'].iloc[-1]} {orden[col].iloc[-1]:.1f}).")
    L.append("")

    # Cuadre contra lo publicado
    L += ["## Cuadre contra lo publicado por el INEGI", ""]
    archivo_p = inegi.FUENTES / "publicados.csv"
    filas = []
    if archivo_p.exists():
        for f in csv.DictReader(archivo_p.open(encoding="utf-8")):
            cd = f["cd_a"] if not f["cd_a"].isdigit() else str(int(f["cd_a"]))
            v = valor(int(f["anio"]), int(f["trim"]), cd, f["indicador"])
            if v is not None:
                filas.append(f"| {f['anio']}-T{f['trim']} | {cat.get(cd, {}).get('ciudad', cd)} | {f['indicador']} | "
                             f"{v:.1f} | {float(f['valor']):.1f} | {v - float(f['valor']):+.1f} |")
    if filas:
        L += ["| Trimestre | Ciudad | Indicador | Calculado | Publicado | Diferencia |", "|---|---|---|---|---|---|"] + filas
    else:
        L.append("No hay cifras publicadas cargadas para los trimestres extraídos.")
    L.append("")

    # Cobertura
    esperados = inegi.trimestres(trims[0], trims[-1])
    faltan = [f"{a}-T{t}" for a, t in esperados if (a, t) not in trims]
    n_ciu = {f"{a}-T{t}": metas[(a, t)].get("ciudades") for a, t in trims}
    L += ["## Cobertura", "",
          f"- Faltan: {', '.join(faltan) if faltan else 'ninguno'} (2020-T2 no existe: fue la ETOE).",
          f"- Ciudades por trimestre: {', '.join(sorted({f'{v}' for v in n_ciu.values()}))} "
          f"(36 en 2019; 39 desde 2020).",
          f"- ENOE Nueva Edición (en parte por teléfono): "
          f"{', '.join(f'{a}-T{t}' for a, t in trims if metas[(a, t)]['encuesta'] == 'ENOE N') or 'ninguno'}.",
          ""]

    texto = "\n".join(L) + "\n"
    (inegi.PROCESADO / "control.md").write_text(texto, encoding="utf-8")
    inegi.resumen_github(texto)
    print(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
