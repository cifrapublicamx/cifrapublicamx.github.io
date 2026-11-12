"""
Cifra Pública | Folio 003 | Consolida los meses extraídos en series y escribe el control.

Lee data/processed/empleo/mensual/*/ y escribe en data/processed/empleo/:
- nacional_mensual.csv         total del país por mes, con la cifra del boletín al lado
- municipios_mensual.csv.gz    todos los municipios, total por mes
- detalle_*.csv.gz             municipios elegidos, todos los meses
- sectores_municipios.csv.gz   sectores seguidos en todo el país (si hay)
- control.md                   cobertura, cuadre contra boletines, saltos y resumen del último mes

control.md es también el texto del PR mensual.

Uso:
    python scripts/empleo/consolidar.py
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import imss  # noqa: E402
from extraer import CORTES, GZ, lee_claves, norm  # noqa: E402

import pandas as pd  # noqa: E402

# Rupturas conocidas de la serie (ver el alcance del Folio 003).
RUPTURAS = {
    **{m: "reforma de subcontratación" for m in ("2021-07", "2021-08", "2021-09")},
    **{m: "plataformas digitales (inicio del piloto)" for m in ("2025-07", "2025-08")},
    **{m: "plataformas digitales (ajuste del registro)" for m in ("2026-01", "2026-02", "2026-03")},
    "2026-05": "cancelación de un registro patronal fraudulento",
}
UMBRAL_SALTO = 4.0      # % de cambio contra el mes anterior que se marca para revisar


def pct(a, b):
    return (a / b - 1) * 100 if b else float("nan")


def f0(x):
    return "—" if pd.isna(x) else f"{x:,.0f}"


def f1(x):
    return "—" if pd.isna(x) else f"{x:+.1f}%"


def mes_menos(mes: str, n: int) -> str:
    a, m = map(int, mes.split("-"))
    total = a * 12 + (m - 1) - n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def main() -> int:
    meses = sorted(imss.meses_procesados())
    if not meses:
        print("No hay meses extraídos todavía.")
        return 0
    modo = lee_claves()
    metas = {m: json.loads((imss.MENSUAL / m / "meta.json").read_text(encoding="utf-8")) for m in meses}

    # --- municipios (todo el país)
    partes = []
    for m in meses:
        df = pd.read_csv(imss.MENSUAL / m / "municipios.csv.gz", dtype={"cve_entidad": str, "cve_municipio": str},
                         keep_default_na=False)
        df.insert(0, "mes", m)
        partes.append(df)
    mun = pd.concat(partes, ignore_index=True)
    mun["permanentes"] = mun["tpu"] + mun["tpc"]
    mun["eventuales"] = mun["teu"] + mun["tec"]
    if modo == "inegi":
        def clave(e, m_):
            return f"{int(e):02d}{int(m_):03d}" if e.isdigit() and m_.isdigit() else ""
        mun["clave_inegi"] = [clave(e, m_) for e, m_ in zip(mun["cve_entidad"], mun["cve_municipio"])]
    columnas = ["mes", "cve_entidad", "cve_municipio"] + (["clave_inegi"] if modo == "inegi" else []) + \
               ["ta", "permanentes", "eventuales", "ta_sal", "masa_sal_ta"]
    mun[columnas].to_csv(imss.PROCESADO / "municipios_mensual.csv.gz", index=False, compression=GZ)

    # --- nacional
    nac = mun.groupby("mes")[["ta", "permanentes", "eventuales", "ta_sal", "masa_sal_ta"]].sum()
    nac["salario_diario"] = (nac["masa_sal_ta"] / nac["ta_sal"]).round(2)
    nac["municipios_con_puestos"] = mun[mun["ta"] > 0].groupby("mes").size()
    boletines = {}
    archivo_b = imss.FUENTES / "boletines.csv"
    if archivo_b.exists():
        for f in csv.DictReader(archivo_b.open(encoding="utf-8")):
            boletines[f["fecha_corte"][:7]] = (float(f["puestos"]), f["fuente"])
    nac["boletin"] = [boletines.get(m, (float("nan"), ""))[0] for m in nac.index]
    nac["diferencia"] = nac["ta"] - nac["boletin"]
    nac.reset_index().to_csv(imss.PROCESADO / "nacional_mensual.csv", index=False)

    # --- detalle y sectores
    for nombre in [*CORTES, "sectores_municipios"]:
        partes = []
        for m in meses:
            ruta = imss.MENSUAL / m / f"{nombre}.csv.gz"
            if ruta.exists():
                df = pd.read_csv(ruta, dtype=str, keep_default_na=False)
                if len(df):
                    df.insert(0, "mes", m)
                    partes.append(df)
        if partes:
            pd.concat(partes, ignore_index=True).to_csv(imss.PROCESADO / f"{nombre}.csv.gz", index=False,
                                                        compression=GZ)

    # --- municipios elegidos: series por clave
    elegidos = list(csv.DictReader((imss.FUENTES / "municipios.csv").open(encoding="utf-8")))
    mun["k"] = list(zip(mun["cve_entidad"].map(norm), mun["cve_municipio"].map(norm)))
    series = {}
    for f in elegidos:
        if modo == "imss" and f.get("cve_entidad_imss") and f.get("cve_municipio_imss"):
            k = (norm(f["cve_entidad_imss"]), norm(f["cve_municipio_imss"]))
        elif modo == "inegi":
            k = (norm(f["clave_inegi"][:2]), norm(f["clave_inegi"][2:]))
        else:
            continue
        sub = mun[mun["k"] == k].set_index("mes")
        series[f["clave_inegi"]] = (f, sub)

    # --- control.md
    L = []
    hoy = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    ultimo = meses[-1]
    L += [f"# Empleo formal IMSS | control al {ultimo}", "", f"Generado {hoy}. Claves de municipio: {modo}.", ""]

    L += ["## Último mes", ""]
    L += ["| Municipio | Papel | Puestos | vs. hace un año | vs. mismo mes de 2019 | Permanentes | Salario diario |",
          "|---|---|---|---|---|---|---|"]
    for clave_inegi, (f, sub) in series.items():
        if ultimo not in sub.index:
            L.append(f"| {f['municipio']} | {f['papel']} | sin datos | | | | |")
            continue
        r = sub.loc[ultimo]
        hace_un_anio = sub["ta"].get(mes_menos(ultimo, 12), float("nan"))
        en_2019 = sub["ta"].get(f"2019-{ultimo[5:]}", float("nan"))
        sal = r["masa_sal_ta"] / r["ta_sal"] if r["ta_sal"] else float("nan")
        perm = r["permanentes"] / r["ta"] * 100 if r["ta"] else float("nan")
        L.append(f"| {f['municipio']} | {f['papel']} | {f0(r['ta'])} | {f1(pct(r['ta'], hace_un_anio))} | "
                 f"{f1(pct(r['ta'], en_2019))} | {perm:.0f}% | ${sal:,.2f} |")
    n_ult = nac.loc[ultimo]
    L += ["", f"País: {f0(n_ult['ta'])} puestos; salario diario promedio ${n_ult['salario_diario']:,.2f} (nominal).", ""]

    L += ["## Cuadre contra los boletines del IMSS", ""]
    con_b = nac.dropna(subset=["boletin"])
    if len(con_b):
        L += ["| Mes | Archivo (ta) | Boletín | Diferencia | Fuente |", "|---|---|---|---|---|"]
        for m, r in con_b.iterrows():
            L.append(f"| {m} | {f0(r['ta'])} | {f0(r['boletin'])} | {f0(r['diferencia'])} "
                     f"({pct(r['ta'], r['boletin']):+.2f}%) | {boletines[m][1]} |")
    else:
        L.append("Ningún mes extraído tiene cifra de boletín cargada.")
    L.append("")

    L += ["## Cobertura", ""]
    esperados = imss.rango_meses(meses[0], ultimo)
    faltan = [m for m in esperados if m not in meses]
    L.append(f"- {len(meses)} meses, de {meses[0]} a {ultimo}. Faltan: {', '.join(faltan) if faltan else 'ninguno'}.")
    nuevas = sorted({c for m in meses for c in metas[m].get("columnas_nuevas", [])})
    if nuevas:
        L.append(f"- Columnas que no estaban en el diccionario: {', '.join(nuevas)} "
                 f"(meses: {', '.join(m for m in meses if metas[m].get('columnas_nuevas'))}).")
    sin_datos = {m: metas[m].get("municipios_elegidos_sin_datos") for m in meses if metas[m].get("municipios_elegidos_sin_datos")}
    if sin_datos:
        L.append(f"- Municipios elegidos sin datos en algún mes: {json.dumps(sin_datos, ensure_ascii=False)}.")
    L.append("")

    L += ["## Saltos para revisar (más de 4% contra el mes anterior)", ""]
    saltos = []
    calendario = imss.rango_meses(meses[0], ultimo)

    def contra_mes_anterior(serie: pd.Series) -> pd.Series:
        s_ = serie.reindex(calendario)          # un mes faltante deja hueco: no se compara a saltos
        return (s_ / s_.shift(1) - 1) * 100

    for clave_inegi, (f, sub) in series.items():
        for m, c in contra_mes_anterior(sub["ta"]).items():
            if pd.notna(c) and abs(c) >= UMBRAL_SALTO:
                saltos.append((m, f["municipio"], c, RUPTURAS.get(m, "")))
    for m, c in contra_mes_anterior(nac["ta"]).items():
        if pd.notna(c) and abs(c) >= 1.5:
            saltos.append((m, "País", c, RUPTURAS.get(m, "")))
    if saltos:
        L += ["| Mes | Dónde | Cambio | Ruptura conocida |", "|---|---|---|---|"]
        for m, d, c, rup in sorted(saltos)[-60:]:
            L.append(f"| {m} | {d} | {c:+.1f}% | {rup} |")
    else:
        L.append("Ninguno.")
    L.append("")

    texto = "\n".join(L) + "\n"
    (imss.PROCESADO / "control.md").write_text(texto, encoding="utf-8")
    imss.resumen_github(texto)
    print(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
