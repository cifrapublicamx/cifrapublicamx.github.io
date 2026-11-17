"""
Cifra Pública | Folio 003 | Junta los trimestres de la ENOE y escribe el control.

Lee data/processed/enoe/trimestral/*/ y escribe en data/processed/enoe/:
- nacional_trimestral.csv   total nacional, 32 entidades y 4 tamaños de localidad, todos los trimestres
- ciudades_trimestral.csv   todas las ciudades y agregados, todos los trimestres
- desgloses_trimestral.csv  nacional, 36 ciudades, León y comparables por sexo y sector
- control.md                el titular y si se sostiene, nacional y ciudades contra 2019, las 32
                            entidades, León y comparables, cuadre contra lo publicado por el INEGI
                            y cobertura. Es también el texto del PR.

Cambios contra 2019: promedio de los últimos cuatro trimestres contra el promedio de los cuatro de
2019 (así cada lado tiene todas las estaciones). Margen conservador: el promedio de los cuatro
intervalos de 90% de cada lado, como si los trimestres estuvieran totalmente correlacionados (la
ENOE repite viviendas: panel rotatorio), y la raíz de la suma de cuadrados de los dos lados. Un
cambio «se distingue» si es mayor que ese margen.

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

TITULO = "Menos desempleo, la misma informalidad: así cambió el trabajo en las ciudades desde 2019"
BASE = [f"2019-T{t}" for t in (1, 2, 3, 4)]
INDICADORES = (("informalidad", "Informalidad"), ("desocupacion", "Desocupación"),
               ("participacion", "Participación"), ("sector_informal", "Sector informal"))


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


# ---------------------------------------------------------------- promedios de cuatro trimestres

def promedio(filas: pd.DataFrame, trims: list[str], ind: str):
    """Promedio y margen conservador de un indicador en esos trimestres; None si falta alguno."""
    s = filas[filas["trimestre"].isin(trims)]
    if len(s) != len(trims) or s[ind].isna().any() or s[ind + "_ic90"].isna().any():
        return None, None
    return float(s[ind].mean()), float(s[ind + "_ic90"].mean())


def cambio(filas: pd.DataFrame, ult: list[str], ind: str) -> dict | None:
    """2019 contra los últimos cuatro trimestres: valores, diferencia, margen y veredicto."""
    a, ea = promedio(filas, BASE, ind)
    b, eb = promedio(filas, ult, ind)
    if a is None or b is None:
        return None
    d, m, si = compara(b, a, eb, ea)
    return {"antes": a, "ahora": b, "dif": d, "margen": m,
            "veredicto": ("baja" if d < 0 else "sube") if si else "igual"}


def texto_promedios(c: dict | None) -> str:
    if c is None:
        return "—"
    return f"{c['antes']:.1f} → {c['ahora']:.1f} ({c['dif']:+.1f} ± {c['margen']:.1f}, {c['veredicto']})"


def conteo(tabla: pd.DataFrame, clave: str, claves: list[str], ult: list[str], ind: str) -> dict:
    """Cuántas unidades bajan, siguen igual o suben, y cuáles."""
    out = {"baja": [], "igual": [], "sube": []}
    for k in claves:
        c = cambio(tabla[tabla[clave] == k], ult, ind)
        if c is not None:
            out[c["veredicto"]].append(k)
    return out


def titular(ciu: pd.DataFrame, ult: list[str]) -> dict:
    """Los hechos del título, calculados sobre las 36 ciudades que existen desde 2019.
    «Menos desempleo»: la desocupación baja en más ciudades que en las que sube y baja en el agregado.
    «La misma informalidad»: en la mayoría de las ciudades no cambia más allá del margen, y en menos
    ciudades baja la informalidad que la desocupación."""
    numericas = ciu[ciu["cd_a"].str.fullmatch(r"\d+")]
    en_2019 = sorted(set(numericas[numericas["trimestre"].isin(BASE)]["cd_a"]), key=int)
    des = conteo(numericas, "cd_a", en_2019, ult, "desocupacion")
    inf = conteo(numericas, "cd_a", en_2019, ult, "informalidad")
    agg_des = cambio(ciu[ciu["cd_a"] == "36 ciudades"], ult, "desocupacion")
    n = len(en_2019)
    reglas = {
        "la desocupación baja en más ciudades que en las que sube": len(des["baja"]) > len(des["sube"]),
        "la desocupación del agregado de 36 baja": bool(agg_des and agg_des["veredicto"] == "baja"),
        "la informalidad no cambia en la mayoría de las ciudades": len(inf["igual"]) > n / 2,
        "la informalidad baja en menos ciudades que la desocupación": len(inf["baja"]) < len(des["baja"]),
    }
    return {"n": n, "desocupacion": des, "informalidad": inf, "reglas": reglas,
            "se_sostiene": all(reglas.values())}


# ---------------------------------------------------------------- lectura

def lee_trimestres(trims):
    partes_c, partes_n, partes_d, metas = [], [], [], {}
    for a, t in trims:
        d = TRIMESTRAL / f"{a}-T{t}"
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        metas[(a, t)] = meta
        cabeza = {"anio": a, "trim": t, "trimestre": f"{a}-T{t}", "encuesta": meta["encuesta"]}
        for nombre, partes, tipos in (("ciudades.csv", partes_c, {"cd_a": str}),
                                      ("nacional.csv", partes_n, {"clave": str}),
                                      ("desgloses.csv", partes_d, {"cd_a": str})):
            ruta = d / nombre
            if ruta.exists() and ruta.stat().st_size > 5:
                x = pd.read_csv(ruta, dtype=tipos)
                for i, (k, v) in enumerate(cabeza.items()):
                    x.insert(i, k, v)
                partes.append(x)
    junta = lambda partes: pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()  # noqa: E731
    return junta(partes_c), junta(partes_n), junta(partes_d), metas


def main() -> int:
    trims = sorted(hechos())
    if not trims:
        print("No hay trimestres extraídos todavía.")
        return 0
    cat = nombres()
    ents = inegi.entidades()
    ciu, nac, des, metas = lee_trimestres(trims)

    nombre_ciudad = lambda x: cat.get(x, {}).get("ciudad", x)  # noqa: E731
    ciu.insert(5, "ciudad", ciu["cd_a"].map(nombre_ciudad))
    ciu.to_csv(inegi.PROCESADO / "ciudades_trimestral.csv", index=False)
    if not nac.empty:
        def nombre_nac(fila):
            if fila["dominio"] == "nacional":
                return "Nacional"
            if fila["dominio"] == "entidad":
                return ents.get(fila["clave"], {}).get("nombre_corto", fila["clave"])
            return inegi.LOCALIDADES.get(int(fila["clave"]), fila["clave"])
        nac.insert(6, "nombre", nac.apply(nombre_nac, axis=1))
        nac.to_csv(inegi.PROCESADO / "nacional_trimestral.csv", index=False)
    if not des.empty:
        des.insert(5, "ciudad", des["cd_a"].map(nombre_ciudad))
        des.to_csv(inegi.PROCESADO / "desgloses_trimestral.csv", index=False)

    ua, ut = trims[-1]
    etiquetas = [f"{a}-T{t}" for a, t in trims]
    ult = etiquetas[-4:]
    hay_base = all(b in etiquetas for b in BASE)
    L = [f"# ENOE | control al {ua}-T{ut}", "",
         f"Generado {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. "
         f"{len(trims)} trimestres, de {etiquetas[0]} a {etiquetas[-1]}.", "",
         f"Cambios contra 2019: promedio de los últimos cuatro trimestres ({ult[0]} a {ult[-1]}) contra el "
         "promedio de 2019, con margen conservador de 90%. «baja» y «sube» = el cambio es mayor que su "
         "margen; «igual» = no se distingue.", ""]

    # Titular
    if hay_base:
        tt = titular(ciu, ult)
        L += ["## El titular", "", f"«{TITULO}»", "",
              f"**¿Se sostiene?** {'sí' if tt['se_sostiene'] else '**NO: revisar el título antes de publicar**'}", ""]
        for regla, ok in tt["reglas"].items():
            L.append(f"- {'✓' if ok else '✗'} {regla}")
        for ind, nombre in (("desocupacion", "Desocupación"), ("informalidad", "Informalidad")):
            c = tt[ind]
            L.append(f"- {nombre} en las {tt['n']} ciudades: baja en {len(c['baja'])}, igual en {len(c['igual'])}, "
                     f"sube en {len(c['sube'])}.")
            for v in ("baja", "sube"):
                if c[v] and (ind == "informalidad" or v == "sube"):
                    L.append(f"  - {v}: {', '.join(nombre_ciudad(k) for k in c[v])}")
        L.append("")

        # Nacional, tamaño de localidad y agregados de ciudades
        L += ["## Nacional, por tamaño de localidad y agregados de ciudades", "",
              "| | " + " | ".join(n for _, n in INDICADORES[:3]) + " |", "|---|---|---|---|"]
        renglones = []
        if not nac.empty:
            renglones.append(("Nacional", nac[nac["dominio"] == "nacional"]))
            for k, n in inegi.LOCALIDADES.items():
                renglones.append((f"Localidades de {n.lower()}", nac[(nac["dominio"] == "localidad") & (nac["clave"] == str(k))]))
        for et in ("36 ciudades", "36 ciudades sin Ciudad de México", str(inegi.CDMX)):
            etiqueta_c = nombre_ciudad(et) + (" (ciudad de la ENOE)" if et == str(inegi.CDMX) else "")
            renglones.append((etiqueta_c, ciu[ciu["cd_a"] == et]))
        for nombre, filas in renglones:
            L.append(f"| {nombre} | " + " | ".join(texto_promedios(cambio(filas, ult, i)) for i, _ in INDICADORES[:3]) + " |")
        L.append("")

        # Entidades
        if not nac.empty:
            en = nac[nac["dominio"] == "entidad"]
            claves = sorted(set(en["clave"]), key=int)
            ultimo = en[en["trimestre"] == etiquetas[-1]].sort_values("informalidad")
            L += [f"## Las {len(claves)} entidades", ""]
            for ind, nombre in INDICADORES[:3]:
                c = conteo(en, "clave", claves, ult, ind)
                L.append(f"- {nombre}: baja en {len(c['baja'])}, igual en {len(c['igual'])}, sube en {len(c['sube'])}.")
                for v in ("baja", "sube"):
                    if c[v] and ind != "participacion":
                        L.append(f"  - {v}: {', '.join(ents.get(k, {}).get('nombre_corto', k) for k in c[v])}")
            if len(ultimo):
                L.append(f"- Informalidad en {etiquetas[-1]}: más baja {ultimo['nombre'].iloc[0]} "
                         f"{ultimo['informalidad'].iloc[0]:.1f}; más alta {ultimo['nombre'].iloc[-1]} "
                         f"{ultimo['informalidad'].iloc[-1]:.1f}.")
            L.append("")
    else:
        L += ["No están los cuatro trimestres de 2019: no se calculan los cambios contra 2019.", ""]

    # León y comparables
    elegidas = ["5"] + [k for k, f in cat.items() if f.get("papel") == "comparable"]
    L += [f"## {ua}-T{ut}: León y comparables", "",
          "| | Informalidad % | contra hace un año (mismo trimestre) | 2019 → últimos cuatro trimestres | Participación % | Desocupación % |",
          "|---|---|---|---|---|---|"]

    def valor(cd, a, t, col):
        r = ciu[(ciu["anio"] == a) & (ciu["trim"] == t) & (ciu["cd_a"] == cd)]
        return None if r.empty or pd.isna(r[col].iloc[0]) else float(r[col].iloc[0])

    for cd in elegidas + ["36 ciudades"]:
        inf, ic = valor(cd, ua, ut, "informalidad"), valor(cd, ua, ut, "informalidad_ic90")
        prev = compara(inf, valor(cd, ua - 1, ut, "informalidad"), ic, valor(cd, ua - 1, ut, "informalidad_ic90"))
        nombre = nombre_ciudad(cd)
        L.append(f"| {'**' + nombre + '**' if cd == '5' else nombre} | {f1(inf)} ± {f1(ic)} | {texto_cambio(*prev)} | "
                 f"{texto_promedios(cambio(ciu[ciu['cd_a'] == cd], ult, 'informalidad')) if hay_base else '—'} | "
                 f"{f1(valor(cd, ua, ut, 'participacion'))} | {f1(valor(cd, ua, ut, 'desocupacion'))} |")
    L += [""]

    ultc = ciu[(ciu["anio"] == ua) & (ciu["trim"] == ut) & ciu["cd_a"].str.fullmatch(r"\d+")]
    L += ["Lugar de León entre las ciudades (1 = la más alta):", ""]
    for col, nombre in (("informalidad", "Informalidad"), ("participacion", "Participación"),
                        ("desocupacion", "Desocupación")):
        orden = ultc.sort_values(col, ascending=False).reset_index(drop=True)
        pos = orden.index[orden["cd_a"] == "5"]
        if len(pos):
            L.append(f"- {nombre}: lugar {pos[0] + 1} de {len(orden)} "
                     f"(más alta: {orden['ciudad'].iloc[0]} {orden[col].iloc[0]:.1f}; "
                     f"más baja: {orden['ciudad'].iloc[-1]} {orden[col].iloc[-1]:.1f}).")
    L.append("")

    # Cuadre contra lo publicado
    L += ["## Cuadre contra lo publicado por el INEGI", ""]

    def publicado(clave: str, a: int, t: int, ind: str):
        """clave: «Nacional», «ent:NN», «loc:N», clave de ciudad o etiqueta de agregado."""
        if clave == "Nacional" or clave.startswith(("ent:", "loc:")):
            if nac.empty:
                return None, clave
            dom, k = (("nacional", "0") if clave == "Nacional" else
                      ("entidad" if clave.startswith("ent:") else "localidad", str(int(clave[4:]))))
            r = nac[(nac["anio"] == a) & (nac["trim"] == t) & (nac["dominio"] == dom) & (nac["clave"] == k)]
            nombre = (r["nombre"].iloc[0] if len(r) else clave) + (" (entidad)" if dom == "entidad" else "")
        else:
            k = str(int(clave)) if clave.isdigit() else clave
            r = ciu[(ciu["anio"] == a) & (ciu["trim"] == t) & (ciu["cd_a"] == k)]
            nombre = nombre_ciudad(k)
        return (None if r.empty or pd.isna(r[ind].iloc[0]) else float(r[ind].iloc[0])), nombre

    archivo_p = inegi.FUENTES / "publicados.csv"
    filas = []
    if archivo_p.exists():
        for f in csv.DictReader(archivo_p.open(encoding="utf-8")):
            v, nombre = publicado(f["cd_a"], int(f["anio"]), int(f["trim"]), f["indicador"])
            if v is not None:
                filas.append(f"| {f['anio']}-T{f['trim']} | {nombre} | {f['indicador']} | "
                             f"{v:.1f} | {float(f['valor']):.1f} | {v - float(f['valor']):+.1f} |")
    if filas:
        L += ["| Trimestre | Dónde | Indicador | Calculado | Publicado | Diferencia |", "|---|---|---|---|---|---|"] + filas
    else:
        L.append("No hay cifras publicadas cargadas para los trimestres extraídos.")
    L.append("")

    # Cobertura
    esperados = inegi.trimestres(trims[0], trims[-1])
    faltan = [f"{a}-T{t}" for a, t in esperados if (a, t) not in trims]
    sin_nacional = [f"{a}-T{t}" for a, t in trims if "entidades" not in metas[(a, t)]]
    valores = lambda k: ", ".join(sorted({str(m.get(k)) for m in metas.values() if m.get(k) is not None}))  # noqa: E731
    L += ["## Cobertura", "",
          f"- Faltan: {', '.join(faltan) if faltan else 'ninguno'} (2020-T2 no existe: fue la ETOE).",
          f"- Ciudades por trimestre: {valores('ciudades')} (36 en 2019; 39 desde 2020).",
          f"- Entidades por trimestre: {valores('entidades') or '—'}. Tamaños de localidad: {valores('tamanos_localidad') or '—'} "
          f"(columna: {valores('localidad') or '—'}).",
          f"- Trimestres extraídos con la versión anterior, sin nacional ni entidades: {', '.join(sin_nacional) or 'ninguno'}.",
          f"- ENOE Nueva Edición (en parte por teléfono): "
          f"{', '.join(f'{a}-T{t}' for a, t in trims if metas[(a, t)]['encuesta'] == 'ENOE N') or 'ninguno'}.",
          "- Las cifras en número de personas no se comparan a través de 2024-T4: ese trimestre el INEGI "
          "actualizó la población de las ciudades (las tasas sí se comparan).",
          ""]

    texto = "\n".join(L) + "\n"
    (inegi.PROCESADO / "control.md").write_text(texto, encoding="utf-8")
    inegi.resumen_github(texto)
    print(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
