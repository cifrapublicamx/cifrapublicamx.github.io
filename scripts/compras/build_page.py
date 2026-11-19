"""
Cifra Pública | Folio 005 | Paso 3. Arma la página «¿Dónde se van tus 100 pesos?».

Lee data/processed/compras/ (paso 2) y escribe compras/index.html desde site_src/compras.html.
Antes de escribir revisa que los datos sigan sosteniendo lo que dice el texto (revisar()); si no, se detiene.

Uso:
    python scripts/compras/build_page.py
    python scripts/compras/build_page.py --fecha "20 de noviembre de 2026"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[2]
DATOS = BASE / "data/processed/compras"
PLANTILLA = BASE / "site_src/compras.html"
SALIDA = BASE / "compras/index.html"
AUTOR = "Rodrigo Méndez"
CORREO = "cifrapublicamx@gmail.com"
FECHA = "19 de noviembre de 2026"
ANIOS = (2020, 2022, 2024)
Z90 = 1.645

MONEDAS = ["tiendita", "cadenas", "calle", "especializada"]  # el resto se calcula como 100 menos estos
DETALLE = ["tiendita", "super", "conveniencia", "club", "departamental", "mercado", "tianguis", "ambulantes",
           "especializada", "fuera", "particular", "internet", "otros"]
DECIL = [("canal", "tiendita"), ("canal", "cadenas"), ("canal", "fuera"), ("canal", "internet"),
         ("pago", "efectivo"), ("pago", "tarjeta")]


def cargar():
    ind = pd.read_csv(DATOS / "indicadores.csv")
    cam = pd.read_csv(DATOS / "cambios.csv")
    dec = json.load(open(DATOS / "deciles.json"))
    return ind, cam, dec


def valor(ind, anio, dom, tema, indic):
    r = ind[(ind.anio == anio) & (ind.dominio == dom) & (ind.tema == tema) & (ind.indicador == indic)]
    if len(r) != 1:
        raise SystemExit(f"Falta {anio} {dom} {tema} {indic}")
    return float(r.p.iloc[0]), float(r.ee.iloc[0])


def cambio(cam, dom, tema, indic, desde=2020):
    r = cam[(cam.dominio == dom) & (cam.tema == tema) & (cam.indicador == indic) & (cam.desde == desde)].iloc[0]
    return float(r.dif), float(r.ee), bool(r.significativa_90)


def r1(x):
    return round(x * 100, 4)


def meta(ind, cam, dec):
    M = {"anios": ANIOS, "z90": Z90}
    # 100 monedas: proporción y error por grupo, año, lugar y tipo de gasto
    M["monedas"] = {dom: {tema: {str(a): [[r1(p), r1(e)] for p, e in (valor(ind, a, dom, tema, g) for g in MONEDAS)]
                                 for a in ANIOS} for tema in ("canal", "comida")} for dom in ("gto", "mx")}
    # Tabla de detalle
    M["detalle"] = {dom: {tema: {g: {str(a): [r1(p), r1(e)] for a in ANIOS for p, e in [valor(ind, a, dom, tema, g)]}
                                 for g in DETALLE if not (tema == "comida" and g in ("fuera", "internet", "departamental"))}
                          for tema in ("canal", "comida")} for dom in ("gto", "mx")}
    # Deciles nacionales
    M["deciles"] = {f"{t}_{g}": {str(a): [[r1(p), r1(e)] for p, e in (valor(ind, a, f"d{k}", t, g) for k in range(1, 11))]
                                 for a in ANIOS} for t, g in DECIL}
    M["cortes"] = [round(c) for c in dec["mensual_dic2025"]]
    M["cortes_ago2024"] = [round(c) for c in dec["mensual_ago2024"]]
    M["pago"] = {dom: {g: {str(a): [r1(p), r1(e)] for a in ANIOS for p, e in [valor(ind, a, dom, "pago", g)]}
                       for g in ("efectivo", "tarjeta", "debito", "credito", "transferencia", "fiado")} for dom in ("gto", "mx")}
    M["tiendita_efectivo"] = {dom: {str(a): r1(valor(ind, a, dom, "tiendita_pago", "efectivo")[0]) for a in ANIOS} for dom in ("gto", "mx")}
    M["tiendita_efectivo_ee"] = {dom: {str(a): r1(valor(ind, a, dom, "tiendita_pago", "efectivo")[1]) for a in ANIOS} for dom in ("gto", "mx")}
    M["n"] = {dom: {str(a): int(ind[(ind.anio == a) & (ind.dominio == dom) & (ind.tema == "contexto")].n.iloc[0]) for a in ANIOS}
              for dom in ("gto", "mx")}
    M["gasto_hogar"] = {dom: {str(a): round(float(ind[(ind.anio == a) & (ind.dominio == dom) & (ind.tema == "contexto")].p.iloc[0]))
                              for a in ANIOS} for dom in ("gto", "mx")}
    M["cambios"] = {f"{dom}_{t}_{g}": [round(cambio(cam, dom, t, g)[0] * 100, 2), round(cambio(cam, dom, t, g)[1] * 100, 2), cambio(cam, dom, t, g)[2]]
                    for dom in ("gto", "mx") for t, g in [("canal", "tiendita"), ("comida", "tiendita"), ("pago", "efectivo"),
                                                          ("pago", "tarjeta"), ("canal", "internet"), ("canal", "cadenas"),
                                                          ("comida", "super"), ("comida", "cadenas"), ("canal", "fuera")]}
    return M


def revisar(M, cam):
    """Lo que afirma el texto fijo de la plantilla. Si alguna deja de ser cierta, no se escribe la página."""
    fallas = []
    def ok(cond, msg):
        if not cond:
            fallas.append(msg)
    t20, t24 = M["monedas"]["mx"]["canal"]["2020"][0][0], M["monedas"]["mx"]["canal"]["2024"][0][0]
    ok(f"{t20:.1f}" == "17.5" and f"{t24:.1f}" == "14.3", f"titular: tiendita México {t20} → {t24}")
    ok(round(M["tiendita_efectivo"]["mx"]["2024"]) == 99, "efectivo en la tiendita, México: no redondea a 99")
    # «lo que tumbaría la lectura»: 2022 queda abajo de 16
    ok(M["monedas"]["mx"]["canal"]["2022"][0][0] < 16, "la tiendita en 2022 ya estaba arriba de 16")
    ok(M["cambios"]["gto_canal_tiendita"][2], "la caída de la tiendita en Gto no es significativa")
    # «Subió en 2024» (internet, país): sube de 2022 a 2024 fuera del margen
    i22, i24 = M["detalle"]["mx"]["canal"]["internet"]["2022"], M["detalle"]["mx"]["canal"]["internet"]["2024"]
    ok(i24[0] > i22[0] and (i24[0] - i22[0]) / ((i22[1] ** 2 + i24[1] ** 2) ** 0.5) > Z90, "internet no sube de 2022 a 2024 en el país")
    # «Guanajuato va más lento que el país» en efectivo: cae menos que México, fuera del margen
    ge, me = M["cambios"]["gto_pago_efectivo"], M["cambios"]["mx_pago_efectivo"]
    ok(ge[0] - me[0] > Z90 * (ge[1] ** 2 + me[1] ** 2) ** 0.5, "el efectivo no cae más lento en Gto que en el país")
    ok(M["cambios"]["mx_canal_tiendita"][2], "la caída de la tiendita en México no es significativa")
    ok(M["cambios"]["gto_pago_efectivo"][2], "la caída del efectivo en Gto no es significativa")
    # «pierde con casi todos»: cae en 9 o 10 deciles con significancia
    d20, d24 = M["deciles"]["canal_tiendita"]["2020"], M["deciles"]["canal_tiendita"]["2024"]
    caen = sum((a[0] - b[0]) / ((a[1] ** 2 + b[1] ** 2) ** 0.5) > Z90 for a, b in zip(d20, d24))
    ok(caen >= 9, f"la tiendita cae con significancia solo en {caen} deciles")
    # «la clase media es la que más se fue»: la caída más grande en puntos está en los deciles 3 a 8
    caidas = [a[0] - b[0] for a, b in zip(d20, d24)]
    ok(2 <= caidas.index(max(caidas)) <= 7, f"la mayor caída de la tiendita está en el decil {caidas.index(max(caidas)) + 1}")
    # «el efectivo no se mueve en los hogares de menos ingreso»: deciles 1 a 3 sin cambio significativo
    e20, e24 = M["deciles"]["pago_efectivo"]["2020"], M["deciles"]["pago_efectivo"]["2024"]
    for k in range(3):
        z = (e24[k][0] - e20[k][0]) / ((e20[k][1] ** 2 + e24[k][1] ** 2) ** 0.5)
        ok(abs(z) <= Z90 or abs(e24[k][0] - e20[k][0]) < 1.0, f"el efectivo cambia en el decil {k + 1}: {e20[k][0]} → {e24[k][0]}")
    # «en el decil más alto, 6 de cada 10 pesos»
    ok(round(e24[9][0] / 10) == 6, f"efectivo decil 10 en 2024: {e24[9][0]}")
    # «en la tiendita, 99 de cada 100 pesos son efectivo» (Gto) y casi lo mismo en el país
    ok(round(M["tiendita_efectivo"]["gto"]["2024"]) == 99, "efectivo en la tiendita, Gto")
    ok(M["tiendita_efectivo"]["mx"]["2024"] >= 98.0, "efectivo en la tiendita, México")
    # «internet: alrededor de 1 de cada 100 pesos»; ni el decil más alto pasa de 3
    for dom in ("gto", "mx"):
        v = M["detalle"][dom]["canal"]["internet"]["2024"][0]
        ok(0.5 <= v < 1.5, f"internet {dom} 2024: {v}")
    ok(max(x[0] for x in M["deciles"]["canal_internet"]["2024"]) < 3, "internet en algún decil pasa de 3")
    # Gto depende más de la tiendita que el país
    ok(M["monedas"]["gto"]["canal"]["2024"][0][0] - M["monedas"]["mx"]["canal"]["2024"][0][0] > Z90 * (
        (M["monedas"]["gto"]["canal"]["2024"][0][1] ** 2 + M["monedas"]["mx"]["canal"]["2024"][0][1] ** 2) ** 0.5),
       "Gto no es significativamente más de tiendita que el país")
    # En comida, la tiendita también cae en Gto
    ok(M["cambios"]["gto_comida_tiendita"][2], "en comida, la caída de la tiendita en Gto no es significativa")
    # En el país, en comida gana el súper
    ok(M["cambios"]["mx_comida_super"][2] and M["cambios"]["mx_comida_super"][0] > 0, "en comida, el súper no gana en el país")
    # «la tarjeta de débito explica la mayor parte del cambio» (país)
    deb = M["pago"]["mx"]["debito"]["2024"][0] - M["pago"]["mx"]["debito"]["2020"][0]
    tar = M["pago"]["mx"]["tarjeta"]["2024"][0] - M["pago"]["mx"]["tarjeta"]["2020"][0]
    ok(deb > tar / 2, "el débito no explica la mayor parte del aumento de la tarjeta")
    # «más rápido que en el resto del país»: la caída en Gto es mayor que en México, fuera del margen
    g, m = M["cambios"]["gto_canal_tiendita"], M["cambios"]["mx_canal_tiendita"]
    ok(m[0] - g[0] > Z90 * (g[1] ** 2 + m[1] ** 2) ** 0.5, "la tiendita no cae más rápido en Gto que en el país")
    # «comer fuera» sube en el país y en Gto; en Gto los pesos se reparten (ningún grupo explica más de la mitad)
    ok(M["cambios"]["mx_canal_fuera"][2] and M["cambios"]["mx_canal_fuera"][0] > 0, "comer fuera no sube en el país")
    gan = {k: M["detalle"]["gto"]["canal"][k]["2024"][0] - M["detalle"]["gto"]["canal"][k]["2020"][0] for k in DETALLE if k != "tiendita"}
    ok(max(gan.values()) < 0.5 * (-M["cambios"]["gto_canal_tiendita"][0]), "en Gto un solo lugar se llevó más de la mitad de lo que perdió la tiendita")
    for k in ("fuera", "departamental", "club", "particular"):
        ok(gan[k] > 0, f"en Gto {k} no sube")
    # «sobre todo a comer fuera» (país): es el que más sube
    ganmx = {k: M["detalle"]["mx"]["canal"][k]["2024"][0] - M["detalle"]["mx"]["canal"][k]["2020"][0] for k in DETALLE if k != "tiendita"}
    ok(max(ganmx, key=ganmx.get) == "fuera", "en el país lo que más sube no es comer fuera")
    # Evolución pospandemia: «no fue solo el rebote»
    def par(serie, a1, a2):
        x, y = serie[a1], serie[a2]
        return y[0] - x[0], (y[0] - x[0]) / ((x[1] ** 2 + y[1] ** 2) ** 0.5)
    d, z = par({a: M["monedas"]["mx"]["canal"][a][0] for a in ("2022", "2024")}, "2022", "2024")
    ok(d < 0 and z < -Z90, "la tiendita no sigue bajando de 2022 a 2024 en el país")
    d, z = par({a: M["monedas"]["gto"]["canal"][a][0] for a in ("2022", "2024")}, "2022", "2024")
    ok(d < 0 and z < -Z90, "la tiendita no sigue bajando de 2022 a 2024 en Gto")
    ef = M["pago"]["mx"]["efectivo"]
    d1, _ = par(ef, "2020", "2022"); d2, z2 = par(ef, "2022", "2024")
    ok(d2 < d1 < 0 or (d2 < 0 and d1 >= 0), "el efectivo no cae más rápido de 2022 a 2024 que de 2020 a 2022")
    ok(z2 < -Z90, "la caída del efectivo de 2022 a 2024 no es significativa")
    fu = M["detalle"]["mx"]["canal"]["fuera"]
    ok(fu["2022"][0] - fu["2020"][0] >= 2 * (fu["2024"][0] - fu["2022"][0]), "comer fuera: no es «casi todo rebote»")
    t22, t24d = M["deciles"]["canal_tiendita"]["2022"], M["deciles"]["canal_tiendita"]["2024"]
    n = sum(b[0] < a[0] and (a[0] - b[0]) / ((a[1] ** 2 + b[1] ** 2) ** 0.5) > Z90 for a, b in zip(t22, t24d))
    ok(n >= 7, f"de 2022 a 2024 la tiendita baja con claridad solo en {n} deciles")
    if fallas:
        print("No escribo la página; el texto ya no coincide con los datos:\n- " + "\n- ".join(fallas))
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fecha", default=FECHA)
    args = ap.parse_args()
    ind, cam, dec = cargar()
    M = meta(ind, cam, dec)
    revisar(M, cam)
    t20 = f'{M["monedas"]["mx"]["canal"]["2020"][0][0]:.1f}'
    t24 = f'{M["monedas"]["mx"]["canal"]["2024"][0][0]:.1f}'
    titulo = f"De la pandemia a 2024, la tiendita pasó de {t20} a {t24} de cada 100 pesos que gastan los hogares en México"
    html = PLANTILLA.read_text(encoding="utf-8")
    for k, v in {"__TITULO__": titulo, "__AUTOR__": AUTOR, "__EMAIL__": CORREO, "__FECHA__": args.fecha,
                 "__META__": json.dumps(M, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")}.items():
        html = html.replace(k, v)
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(html, encoding="utf-8")
    print(f"{SALIDA.relative_to(BASE)}: {len(html) / 1024:.0f} KB | {titulo}")


if __name__ == "__main__":
    main()
