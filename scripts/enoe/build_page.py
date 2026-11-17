"""
Cifra Pública | Folio 003 | Arma la página «Menos desempleo, casi la misma informalidad».

Lee data/processed/enoe/ (nacional_trimestral.csv, ciudades_trimestral.csv, desgloses_trimestral.csv)
y escribe informalidad/index.html desde site_src/informalidad.html (usa assets/ para fuentes y logotipo).

Corre sin argumentos: así la llama la actualización trimestral después de consolidar. Si los datos
dejan de sostener el título (consolidar.titular), no escribe nada y termina con error, para que el
título se revise antes de publicar.

Uso:
    python scripts/enoe/build_page.py
    python scripts/enoe/build_page.py --fecha "26 de noviembre de 2026"
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inegi  # noqa: E402
from consolidar import BASE, TITULO, cambio, compara, nombres, titular  # noqa: E402

import pandas as pd  # noqa: E402

PLANTILLA = inegi.BASE / "site_src" / "informalidad.html"
SALIDA = inegi.BASE / "informalidad" / "index.html"
FECHA = "17 de noviembre de 2026"                     # fecha de publicación del folio
LEON = "5"

# Mapa de hexágonos: abreviatura y posición (columna, fila). Las filas impares se recorren medio hexágono.
HEX = {
    "2": ("BC", 0, 0), "26": ("Son", 1, 0), "8": ("Chih", 2, 0), "5": ("Coah", 3, 0), "19": ("NL", 4, 0),
    "3": ("BCS", 0, 1), "25": ("Sin", 1, 1), "10": ("Dgo", 2, 1), "32": ("Zac", 3, 1), "24": ("SLP", 4, 1), "28": ("Tamp", 5, 1),
    "18": ("Nay", 1, 2), "1": ("Ags", 2, 2), "11": ("Gto", 3, 2), "22": ("Qro", 4, 2), "13": ("Hgo", 5, 2), "30": ("Ver", 6, 2),
    "31": ("Yuc", 9, 2),
    "14": ("Jal", 1, 3), "16": ("Mich", 2, 3), "15": ("Méx", 3, 3), "9": ("CDMX", 4, 3), "29": ("Tlax", 5, 3), "21": ("Pue", 6, 3),
    "27": ("Tab", 7, 3), "4": ("Camp", 8, 3), "23": ("QRoo", 9, 3),
    "6": ("Col", 2, 4), "12": ("Gro", 3, 4), "17": ("Mor", 4, 4), "20": ("Oax", 5, 4), "7": ("Chis", 6, 4),
}
ORDINAL = {1: "primer", 2: "segundo", 3: "tercer", 4: "cuarto"}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]


def r1(x):
    """Un decimal, redondeando hacia arriba en el medio (como publica el INEGI: 2.65 → 2.7)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return float(Decimal(str(round(float(x), 6))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def camb(filas: pd.DataFrame, ult: list[str]) -> dict:
    out = {}
    for ind in ("informalidad", "desocupacion", "participacion"):
        c = cambio(filas, ult, ind)
        out[ind] = None if c is None else {"antes": r1(c["antes"]), "ahora": r1(c["ahora"]), "dif": r1(c["dif"]),
                                           "margen": r1(c["margen"]), "v": c["veredicto"]}
    return out


def ultimo(filas: pd.DataFrame, trim: str) -> dict | None:
    f = filas[filas["trimestre"] == trim]
    if f.empty:
        return None
    f = f.iloc[0]
    return {k: r1(f[k]) for k in ("informalidad", "informalidad_ic90", "desocupacion", "desocupacion_ic90",
                                   "participacion", "participacion_ic90")}


def serie(filas: pd.DataFrame, trims: list[str], cols=("informalidad",)) -> list:
    """Una fila por trimestre de la serie (None si falta) con las columnas pedidas."""
    f = filas.set_index("trimestre")
    return [[r1(f.at[t, c]) if t in f.index else None for c in cols] for t in trims]


def ventana(ult: list[str]) -> str:
    a0, t0 = map(int, ult[0].split("-T"))
    a1, t1 = map(int, ult[-1].split("-T"))
    return f"de {MESES[3 * t0 - 3]} de {a0} a {MESES[3 * t1 - 1]} de {a1}"


def main(args) -> int:
    nac = pd.read_csv(inegi.PROCESADO / "nacional_trimestral.csv", dtype={"clave": str})
    ciu = pd.read_csv(inegi.PROCESADO / "ciudades_trimestral.csv", dtype={"cd_a": str})
    des = pd.read_csv(inegi.PROCESADO / "desgloses_trimestral.csv", dtype={"cd_a": str})
    trims = sorted(set(nac["trimestre"]), key=lambda t: tuple(map(int, t.split("-T"))))
    ult, U = trims[-4:], trims[-1]
    ua, ut = map(int, U.split("-T"))
    if not all(b in trims for b in BASE):
        sys.exit("Faltan trimestres de 2019: no se puede armar la página.")

    tt = titular(ciu, nac, ult)
    if not tt["se_sostiene"]:
        falla = [r for r, ok in tt["reglas"].items() if not ok]
        print(f"El título «{TITULO}» ya no se sostiene con los datos al {U}:", *falla, sep="\n- ")
        print("No se rearma la página. Revisa el título y build_page.py.")
        return 1

    cat = nombres()
    ents = inegi.entidades()
    tot = nac[nac["dominio"] == "nacional"]

    # Nacional: serie completa con márgenes y comparación del último trimestre contra un año antes.
    s_nac = serie(tot, trims, ("informalidad", "informalidad_ic90", "desocupacion", "desocupacion_ic90",
                               "participacion", "participacion_ic90"))
    enc = tot.set_index("trimestre")["encuesta"].to_dict()
    hace_un_anio = f"{ua - 1}-T{ut}"
    este = {}
    for ind in ("informalidad", "desocupacion", "participacion"):
        a = tot[tot["trimestre"] == U].iloc[0]
        b = tot[tot["trimestre"] == hace_un_anio]
        if len(b):
            b = b.iloc[0]
            d, m, si = compara(a[ind], b[ind], a[ind + "_ic90"], b[ind + "_ic90"])
            este[ind] = {"ahora": r1(a[ind]), "antes": r1(b[ind]), "dif": r1(d), "margen": r1(m), "distingue": bool(si)}

    # Entidades
    entidades = []
    for clave, f in nac[nac["dominio"] == "entidad"].groupby("clave"):
        ab, col, fila = HEX[clave]
        entidades.append({"clave": clave, "nombre": ents[clave]["nombre_corto"], "abrev": ab, "col": col, "fila": fila,
                          "ultimo": ultimo(f, U), "cambio": camb(f, ult), "serie": serie(f, trims, ("informalidad", "desocupacion"))})
    entidades.sort(key=lambda e: e["nombre"])

    # Tamaño de localidad
    localidades = []
    for clave, f in nac[nac["dominio"] == "localidad"].groupby("clave"):
        localidades.append({"clave": int(clave), "nombre": inegi.LOCALIDADES[int(clave)], "ultimo": ultimo(f, U),
                            "cambio": camb(f, ult)})
    localidades.sort(key=lambda x: x["clave"])

    # Ciudades y agregados
    ciudades = []
    for cd, f in ciu[ciu["cd_a"].str.fullmatch(r"\d+")].groupby("cd_a"):
        info = cat.get(cd, {})
        ciudades.append({"cd": cd, "nombre": info.get("ciudad", cd), "entidad": info.get("entidad", ""),
                         "ultimo": ultimo(f, U), "cambio": camb(f, ult), "desde2019": bool(f["trimestre"].isin(BASE).any()),
                         "serie": serie(f, trims, ("informalidad", "desocupacion"))})
    ciudades.sort(key=lambda c: c["nombre"])
    agregados = {et: {"ultimo": ultimo(ciu[ciu["cd_a"] == et], U), "cambio": camb(ciu[ciu["cd_a"] == et], ult),
                      "serie": serie(ciu[ciu["cd_a"] == et], trims, ("informalidad",))}
                 for et in ("36 ciudades", "36 ciudades sin Ciudad de México", "39 ciudades")}
    oc = ciu[ciu["trimestre"].isin(ult)].pivot(index="trimestre", columns="cd_a", values="ocupados")
    peso_cdmx = r1(100 * (oc[str(inegi.CDMX)] / oc["36 ciudades"]).mean())

    # León: lugar en participación entre las ciudades, trimestres seguidos en primer lugar y diferencia con el segundo.
    numericas = ciu[ciu["cd_a"].str.fullmatch(r"\d+")]
    racha, segundo = 0, None
    for t in reversed(trims):
        orden = numericas[numericas["trimestre"] == t].sort_values("participacion", ascending=False)
        if orden["cd_a"].iloc[0] != LEON:
            break
        racha += 1
        if t == U:
            a, b = orden.iloc[0], orden.iloc[1]
            d, m, si = compara(a["participacion"], b["participacion"], a["participacion_ic90"], b["participacion_ic90"])
            segundo = {"nombre": cat.get(b["cd_a"], {}).get("ciudad", b["cd_a"]), "valor": r1(b["participacion"]),
                       "dif": r1(d), "margen": r1(m), "distingue": bool(si)}
    lugar_inf = int(numericas[numericas["trimestre"] == U].sort_values("informalidad", ascending=False)["cd_a"]
                    .reset_index(drop=True).pipe(lambda s: s[s == LEON].index[0])) + 1
    sexo = {}
    for sx in ("Mujeres", "Hombres"):
        f = des[(des["cd_a"] == LEON) & (des["corte"] == "sexo") & (des["valor"] == sx)]
        c = cambio(f, ult, "participacion")
        sexo[sx] = None if c is None else {"antes": r1(c["antes"]), "ahora": r1(c["ahora"]), "dif": r1(c["dif"]),
                                           "margen": r1(c["margen"]), "v": c["veredicto"]}
    leon = {"racha_participacion": racha, "segundo": segundo, "lugar_informalidad": lugar_inf,
            "n_ciudades": int(numericas[numericas["trimestre"] == U]["cd_a"].nunique()), "sexo": sexo,
            "primer_trimestre_racha": trims[-racha] if racha else None}

    def nombres_de(lista, tipo):
        return [ents[k]["nombre_corto"] if tipo == "ent" else cat.get(k, {}).get("ciudad", k) for k in lista]

    conteos = {
        "entidades": {ind: {v: nombres_de(tt["entidades"][ind][v], "ent") for v in ("baja", "igual", "sube")}
                      for ind in ("desocupacion", "informalidad")},
        "ciudades": {ind: {v: nombres_de(tt["ciudades"][ind][v], "ciu") for v in ("baja", "igual", "sube")}
                     for ind in ("desocupacion", "informalidad")},
        "n_entidades": tt["n_entidades"], "n_ciudades": tt["n_ciudades"],
    }

    meta = {
        "titulo": TITULO, "trims": trims, "ult": ult, "U": U, "ua": ua, "ut": ut,
        "u_texto": f"{ORDINAL[ut]} trimestre de {ua}", "ventana": ventana(ult), "hace_un_anio": hace_un_anio,
        "encuesta": [enc.get(t, "") for t in trims],
        "nacional": {"ultimo": ultimo(tot, U), "cambio": camb(tot, ult), "serie": s_nac, "este": este},
        "entidades": entidades, "localidades": localidades, "ciudades": ciudades, "agregados": agregados,
        "leon": leon, "conteos": conteos, "reglas": tt["reglas"], "peso_cdmx": peso_cdmx,
    }
    # Hechos que afirman los títulos de sección (si cambian, la página se reescribe a mano).
    loc = {x["clave"]: x["cambio"]["informalidad"]["v"] for x in localidades}
    meta["solo_grandes"] = loc.get(1) == "baja" and all(loc.get(k) != "baja" for k in (2, 3, 4))

    dump = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = (PLANTILLA.read_text(encoding="utf-8").replace("__META__", dump).replace("__TITULO__", TITULO)
            .replace("__EMAIL__", args.correo).replace("__AUTOR__", args.autor).replace("__FECHA__", args.fecha)
            .replace("__DATOS__", f"Datos al {ORDINAL[ut]} trimestre de {ua}"))
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(html, encoding="utf-8")
    print(f"{SALIDA} ({SALIDA.stat().st_size / 1024:.0f} KB) | datos al {U} | ventana {meta['ventana']}")
    print("nacional:", meta["nacional"]["cambio"])
    print("entidades:", {k: {v: len(x) for v, x in d.items()} for k, d in conteos["entidades"].items()})
    print("ciudades:", {k: {v: len(x) for v, x in d.items()} for k, d in conteos["ciudades"].items()})
    print("León:", {k: v for k, v in leon.items() if k != "sexo"}, "| solo grandes:", meta["solo_grandes"])
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--autor", default="Rodrigo Méndez Hernández")
    ap.add_argument("--correo", default="cifrapublicamx@gmail.com")
    ap.add_argument("--fecha", default=FECHA)
    sys.exit(main(ap.parse_args()))
