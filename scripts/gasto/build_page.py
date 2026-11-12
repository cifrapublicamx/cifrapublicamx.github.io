"""
Paso 5: arma la página del gasto de León desde las salidas de los pasos 1 a 4.

Uso:
    python -I scripts/gasto/build_page.py --autor "Rodrigo Méndez Hernández" \
        --correo cifrapublicamx@gmail.com --fecha "9 de noviembre de 2026"
Salida:
    gasto-leon/index.html (usa assets/ para fuentes, logotipo y favicon)
"""
import argparse
import csv
import json
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[2]
PROC = BASE / "data" / "processed" / "gasto"
SRC = BASE / "data" / "fuentes" / "gasto"
PLANTILLA = BASE / "site_src" / "gasto-leon.html"
SALIDA = BASE / "gasto-leon" / "index.html"

# Clasificación funcional (CONAC): nombre corto para la página, nombre oficial y, en las
# funciones grandes, qué incluye según el clasificador.
FUNCIONES = {
    11: ("Ayuntamiento (cabildo)", "Legislación", ""),
    12: ("Justicia", "Justicia", ""),
    13: ("Coordinación de gobierno", "Coordinación de la Política de Gobierno", "presidencia, gobierno y función pública"),
    14: ("Relaciones exteriores", "Relaciones Exteriores", ""),
    15: ("Hacienda", "Asuntos Financieros y Hacendarios", "cobro de impuestos y administración del dinero público"),
    16: ("Seguridad nacional", "Seguridad Nacional", ""),
    17: ("Seguridad pública", "Asuntos de Orden Público y de Seguridad Interior", "policía, protección civil y otros asuntos de seguridad"),
    18: ("Otros servicios de gobierno", "Otros Servicios Generales", ""),
    21: ("Protección ambiental", "Protección Ambiental", "residuos, drenaje, contaminación y áreas naturales"),
    22: ("Servicios a la comunidad", "Vivienda y Servicios a la Comunidad", "urbanización, alumbrado, agua, vivienda y servicios comunales"),
    23: ("Salud", "Salud", ""),
    24: ("Deporte, cultura y recreación", "Recreación, Cultura y Otras Manifestaciones Sociales", ""),
    25: ("Educación", "Educación", ""),
    26: ("Protección social", "Protección Social", "apoyos a grupos vulnerables"),
    27: ("Otros asuntos sociales", "Otros Asuntos Sociales", ""),
    31: ("Empleo y promoción económica", "Asuntos Económicos, Comerciales y Laborales en General", ""),
    32: ("Campo", "Agropecuaria, Silvicultura, Pesca y Caza", ""),
    33: ("Energía", "Combustibles y Energía", ""),
    34: ("Construcción", "Minería, Manufacturas y Construcción", "obra que el clasificador cuenta como construcción"),
    35: ("Transporte", "Transporte", ""),
    36: ("Comunicaciones", "Comunicaciones", ""),
    37: ("Turismo", "Turismo", ""),
    38: ("Ciencia y tecnología", "Ciencia, Tecnología e Innovación", ""),
    39: ("Otras actividades económicas", "Otras Industrias y Otros Asuntos Económicos", ""),
    41: ("Deuda", "Transacciones de la Deuda Pública / Costo Financiero de la Deuda", "intereses y comisiones"),
    42: ("Transferencias a otros gobiernos", "Transferencias, Participaciones y Aportaciones entre Diferentes Niveles y Órdenes de Gobierno", ""),
    43: ("Saneamiento financiero", "Saneamiento del Sistema Financiero", ""),
    44: ("Adeudos de años anteriores", "Adeudos de Ejercicios Fiscales Anteriores", ""),
}
SERIES = {"total": 0, "seguridad": 17, "gobierno": 1, "social": 2, "economico": 3}
ADMINS = [  # periodos de gobierno; cambian el 10 de octubre
    {"nombre": "Héctor López Santillana", "periodo": "2015–2021", "desde": 2015 + 283 / 365, "hasta": 2021 + 283 / 365},
    {"nombre": "Alejandra Gutiérrez Campos", "periodo": "2021–2027", "desde": 2021 + 283 / 365, "hasta": 2027 + 283 / 365},
]
# Tipos de gasto (clasificación por objeto del gasto) para «lo que creció y lo que bajó».
GRUPOS = [
    ("Nómina", [1000], "sueldos, prestaciones y seguridad social del personal"),
    ("Ayudas sociales", [4400], "becas y apoyos a personas e instituciones"),
    ("Transferencias a organismos públicos", [4100, 4200], "dinero que pasa a organismos con cuentas propias"),
    ("Subsidios", [4300], ""),
    ("Mantenimiento y conservación", [3500], "de edificios, vehículos, equipo y áreas verdes"),
    ("Servicios profesionales", [3300], "consultorías, estudios y otros servicios contratados"),
    ("Servicios básicos", [3100], "luz, agua, teléfono e internet"),
    ("Materiales y suministros", [2000], "combustibles, papelería, herramientas y otros"),
    ("Vehículos, equipo e inmuebles", [5000], "compras de bienes muebles e inmuebles"),
    ("Obra pública", [6000], ""),
    ("Deuda", [9000], "intereses y pago del capital"),
]
CURIOSIDADES = {"publicidad": [3600], "arrendamientos": [3200], "oficiales": [3800], "papeleria": [2100]}
DEPENDENCIA = {"pct": 30, "anio": 2025, "fuente": "Presupuesto ciudadano 2025, Tesorería de León",
               "url": "https://leon.gob.mx/modulos/img/documentos/tesoreria/Egresos%20Presupuesto/"
                      "Presupuesto%20Inicial%20Certificado/2025/Presupuesto%20ciudadano%202025.pdf"}


def main(args) -> None:
    df = pd.read_csv(PROC / "egresos_leon_real.csv")
    f = df[df.clasificacion == "funcional"]
    anios = sorted(int(y) for y in df.anio.unique())
    ult = anios[-1]
    serie = lambda clave, col: [float(f[(f.anio == y) & (f.clave == clave)][col].iloc[0]) for y in anios]

    tot = f[f.clave == 0].set_index("anio")
    funciones = []
    for _, r in f[(f.anio == ult) & (f.nivel == "funcion") & (f.devengado > 0)].iterrows():
        corto, oficial, desc = FUNCIONES[int(r.clave)]
        funciones.append({"clave": int(r.clave), "corto": corto, "oficial": oficial, "desc": desc,
                          "pct": round(100 * r.devengado / tot.at[ult, "devengado"], 1),
                          "mdp": round(r.devengado / 1e6, 3), "pc": round(r.devengado_real_pc)})
    funciones.sort(key=lambda x: -x["pct"])

    aprobado = [{"anio": y, "aprobado": round(tot.at[y, "aprobado"] / 1e6, 3),
                 "modificado": round(tot.at[y, "modificado"] / 1e6, 3),
                 "devengado": round(tot.at[y, "devengado"] / 1e6, 3),
                 "pct": round(100 * (tot.at[y, "devengado"] / tot.at[y, "aprobado"] - 1), 1),
                 "de_modificado": round(100 * tot.at[y, "devengado"] / tot.at[y, "modificado"], 1)} for y in anios]

    o = df[(df.clasificacion == "objeto") & (df.clave == 6000)].set_index("anio")
    obra_pct = {int(y): round(100 * o.at[y, "devengado"] / tot.at[y, "devengado"], 1) for y in anios}
    seg = f[(f.anio == ult) & (f.clave == 17)].iloc[0]
    with open(SRC / "cifras_seguridad_publicadas.csv", encoding="utf-8") as fh:
        publicadas = [dict(r, cifra_pct=float(r["cifra_pct"])) for r in csv.DictReader(fh)]
    ctl = pd.read_csv(PROC / "control_efipem.csv")
    pob = pd.read_csv(PROC / "deflactor_poblacion.csv").set_index("anio")

    obj = df[df.clasificacion == "objeto"]
    suma = lambda claves, col: [float(obj[(obj.anio == y) & obj.clave.isin(claves)][col].sum()) for y in anios]
    pobs = [float(pob.at[y, "poblacion"]) for y in anios]
    grupos = []
    for nombre, claves, desc in GRUPOS:
        pc = [v / p for v, p in zip(suma(claves, "devengado_real"), pobs)]
        i0 = anios.index(2017)
        grupos.append({"nombre": nombre, "desc": desc, "pc": [round(v) for v in pc],
                       "cambio": round(100 * (pc[-1] / pc[i0] - 1), 1),
                       "pct_ult": round(100 * suma(claves, "devengado")[-1] / tot.at[ult, "devengado"], 1)})
    grupos.sort(key=lambda g: -g["cambio"])
    curiosidades = {k: [round(v / 1e6, 3) for v in suma(c, "devengado_real")] for k, c in CURIOSIDADES.items()}
    ing = pd.read_csv(PROC / "ingresos_leon.csv")
    ciudades = pd.read_csv(PROC / "comparativo_ciudades.csv", dtype={"cvegeo": str})

    meta = {
        "anios": anios, "ultimo": ult, "admins": ADMINS,
        "grupos": grupos, "curiosidades": curiosidades,
        "organismos_ult_mdp": round(suma([4100, 4200], "devengado")[-1] / 1e6, 3),
        "ingresos": ing.round(3).to_dict("records"),
        "ciudades": ciudades.round(3).to_dict("records"),
        "pc": {k: [round(v) for v in serie(c, "devengado_real_pc")] for k, c in SERIES.items()},
        "mdp_real": {k: [round(v / 1e6, 3) for v in serie(c, "devengado_real")] for k, c in SERIES.items()},
        "pc_funciones": {int(c): [round(v) for v in serie(int(c), "devengado_real_pc")]
                         for c in sorted(f[f.nivel == "funcion"].clave.unique())},
        "inv_financieras_mdp": round(float(df[(df.clasificacion == "objeto") & (df.clave == 7000) & (df.anio == anios[0])]
                                           .devengado.iloc[0]) / 1e6),
        "funciones": funciones, "aprobado": aprobado, "obra_pct": obra_pct,
        "seguridad": {"aprobado_pct": round(100 * seg.aprobado / tot.at[ult, "aprobado"], 1),
                      "devengado_pct": round(100 * seg.devengado / tot.at[ult, "devengado"], 1),
                      "devengado_mdp": round(seg.devengado / 1e6, 3), "pc": round(seg.devengado_real_pc),
                      "dependencia": DEPENDENCIA, "publicadas": publicadas},
        "poblacion": {int(y): int(p) for y, p in pob.poblacion.items()},
        "anclas": pd.read_csv(SRC / "poblacion_anclas.csv")[["fuente", "poblacion"]].to_dict("records"),
        "control": {"cuadra": bool((ctl.diferencia_sin_disponibilidad.abs() < 1000).all()),
                    "disponibilidad": {int(r.anio): round(r.efipem_disponibilidad_final / 1e6, 3)
                                       for r in ctl.itertuples() if r.efipem_disponibilidad_final > 0}},
        "autor": args.autor, "fecha": args.fecha,
    }
    # Los títulos de dos secciones afirman estos hechos; si los datos cambian, hay que reescribirlos.
    assert [g["nombre"] for g in grupos[:2]] == ["Ayudas sociales", "Mantenimiento y conservación"], grupos[:2]
    assert next(g for g in grupos if g["nombre"] == "Obra pública")["cambio"] < 0
    assert ciudades.sort_values("patrimonio_pc").ciudad.iloc[-1] == "Querétaro"
    dump = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = (PLANTILLA.read_text(encoding="utf-8").replace("__META__", dump)
            .replace("__EMAIL__", args.correo).replace("__AUTOR__", args.autor).replace("__FECHA__", args.fecha))
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(html, encoding="utf-8")
    print(f"{SALIDA} ({SALIDA.stat().st_size / 1024:.0f} KB)")
    print("por habitante:", dict(zip(anios, meta["pc"]["total"])))
    print("seguridad:", {k: v for k, v in meta["seguridad"].items() if k not in ("dependencia", "publicadas")})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--autor", default="Rodrigo Méndez Hernández")
    ap.add_argument("--correo", default="cifrapublicamx@gmail.com")
    ap.add_argument("--fecha", required=True)
    main(ap.parse_args())
