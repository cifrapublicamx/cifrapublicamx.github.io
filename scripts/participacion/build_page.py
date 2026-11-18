"""
Cifra Pública | Análisis 006 | Paso 5. Arma la página «Participación por sección».

Lee data/processed/participacion/ (pasos 1 a 4) y escribe participacion/index.html desde
site_src/participacion.html. Antes de escribir revisa que los datos sigan sosteniendo lo que
dice el texto (revisar()); si no, se detiene.

Uso:
    python scripts/participacion/build_page.py
    python scripts/participacion/build_page.py --fecha "20 de noviembre de 2026"
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[2]
DATOS = BASE / "data/processed/participacion"
PLANTILLA = BASE / "site_src/participacion.html"
SALIDA = BASE / "participacion/index.html"
LEAFLET = BASE / "node_modules" / "leaflet" / "dist"
AUTOR = "Rodrigo Méndez"
CORREO = "cifrapublicamx@gmail.com"
FECHA = "20 de noviembre de 2026"

SECS_COLS = ["seccion", "lista_2024", "part_2024", "part_2021", "pred_part", "prob_boosting", "y",
             "escolaridad", "mayores_60", "jovenes_18_24", "issste", "sin_afiliacion", "casas_deshabitadas"]
ESTADOS = ["Aguascalientes", "Baja California", "Baja California Sur", "Campeche", "Coahuila", "Colima",
           "Chiapas", "Chihuahua", "Ciudad de México", "Durango", "Guanajuato", "Guerrero", "Hidalgo",
           "Jalisco", "Estado de México", "Michoacán", "Morelos", "Nayarit", "Nuevo León", "Oaxaca", "Puebla",
           "Querétaro", "Quintana Roo", "San Luis Potosí", "Sinaloa", "Sonora", "Tabasco", "Tamaulipas",
           "Tlaxcala", "Veracruz", "Yucatán", "Zacatecas"]


def pct(x, nd=1):
    v = round(100 * float(x), nd)
    return int(v) if nd == 0 else v


def recall_k(y, s):
    y, s = np.asarray(y), np.asarray(s)
    k = int(y.sum())
    return int(y[np.argsort(-s)[:k]].sum()), k


def meta(fecha: str) -> dict:
    D = json.loads((DATOS / "pagina_datos.json").read_text())
    of = json.loads((DATOS / "oficiales_ine.json").read_text())
    svm_t = json.loads((DATOS / "svm_tamano.json").read_text()) if (DATOS / "svm_tamano.json").exists() else {}
    R = D["resultados"]
    A, B, C = R["A_municipios"], R["B_guanajuato"], R["C_con_historia"]
    E = D["escalera"]

    def fila(k, nombre, desc, m, tipo):
        return {"k": k, "n": nombre, "d": desc, "v": pct(m["precision_top10"], 0), "auc": round(m["auc"], 3),
                "rec": pct(m["recall_k_base"], 0), "t": tipo}

    escalera = [
        {"k": "azar", "n": "Al azar", "d": "sin ningún dato", "v": pct(R["tasa_base"], 0), "auc": 0.5,
         "rec": pct(R["tasa_base"], 0), "t": "base"},
        fila("regla", "Una sola variable", "las que tienen más afiliados al ISSSTE votan más", A["regla"], "base"),
        fila("estado", "Solo el estado", "cuánto votó poco el resto de su estado", E["solo_estado"], "base"),
        fila("censo", "Solo el censo", "gradient boosting sin saber el estado", E["solo_censo"], "modelo"),
        fila("logistica", "Regresión logística", "censo y estado", A["logistica"], "modelo"),
        fila("svm", "SVM", "censo y estado", A["svm"], "modelo"),
        fila("boosting", "Gradient boosting", "censo y estado", A["boosting"], "mejor"),
        fila("historia", "Gradient boosting con historia", "censo, estado y lo que votó en 2018 y 2021",
             C["boosting"], "historia"),
    ]
    ciegas = [
        {"k": "azar", "n": "Al azar", "v": pct(B["boosting"]["tasa_base"], 0), "auc": 0.5, "t": "base"},
        {"k": "regla", "n": "Una sola variable (ISSSTE)", "v": pct(B["regla"]["precision_top10"], 0),
         "auc": round(B["regla"]["auc"], 3), "t": "base"},
        {"k": "logistica", "n": "Regresión logística", "v": pct(B["logistica"]["precision_top10"], 0),
         "auc": round(B["logistica"]["auc"], 3), "t": "mejor"},
        {"k": "svm", "n": "SVM", "v": pct(B["svm"]["precision_top10"], 0), "auc": round(B["svm"]["auc"], 3),
         "t": "modelo"},
        {"k": "boosting", "n": "Gradient boosting", "v": pct(B["boosting"]["precision_top10"], 0),
         "auc": round(B["boosting"]["auc"], 3), "t": "modelo"},
    ]
    imp = D["importancia"]
    top = max(imp.values())
    importancia = sorted([{"g": g, "v": round(100 * v / top)} for g, v in imp.items()], key=lambda r: -r["v"])

    mun_n = pd.read_csv(DATOS / "municipios_gto.csv", dtype=str)
    nombres = {int(r.mun): r.nombre for r in mun_n.itertuples()}
    cortos = {"Dolores Hidalgo Cuna de la Independencia Nacional": "Dolores Hidalgo", "Silao de la Victoria": "Silao"}
    nombres = {k: cortos.get(v, v) for k, v in nombres.items()}
    mun = [{"m": int(r["municipio"]), "n": nombres.get(int(r["municipio"]), str(r["municipio"])),
            "l": int(r["lista"]), "s": int(r["secciones"]), "r": pct(r["real"]), "p": pct(r["pred"]),
            "b": pct(r["bajo"])} for r in D["gto_municipios"]]
    mun.sort(key=lambda r: -r["l"])

    secs = pd.DataFrame(D["leon_secciones"])
    hits, k = recall_k(secs.y, secs.prob_boosting)
    sim = D["simulador"]
    por_estado = [{"e": ESTADOS[int(r["entidad"]) - 1], "p": pct(r["part"]), "b": pct(r["bajo"])}
                  for r in D["por_estado"]]
    por_estado.sort(key=lambda r: r["p"])

    return {
        "fecha": fecha,
        "n_vars": 29,
        "oficial": {a: of[a]["participacion"] for a in of},
        "ctx": D["contexto"],
        "escalera": escalera,
        "ciegas": ciegas,
        "importancia": importancia,
        "curvas": D["curvas"],
        "sim": {"vars": sim["variables"], "base": sim["base_gto"], "formas": sim["formas"],
                "perfiles": sim["perfiles"], "mae_gto": round(sim["mae_puntos_gto"], 1),
                "mae": round(sim["mae_puntos"], 1)},
        "regresion": {k2: round(v, 3) for k2, v in R["regresion"].items()},
        "hex": D["leon_hex"],
        "secs_cols": SECS_COLS,
        "secs": [[None if pd.isna(r[c]) else (int(r[c]) if c in ("seccion", "lista_2024", "y") else round(float(r[c]), 3))
                  for c in SECS_COLS] for r in D["leon_secciones"]],
        "leon": D["leon_metricas"] | {"hits": hits, "k": k},
        "gto": D["gto_metricas"],
        "mun": mun,
        "estados": por_estado,
        "p2021": D["prueba_2021"],
        "svm_t": {str(n): {"v": pct(m["precision_top10"], 0), "auc": round(m["auc"], 3)} for n, m in svm_t.items()},
        "historia_auc": round(C["boosting"]["auc"], 3),
        "solo_historia": pct(E["solo_historia"]["precision_top10"], 0),
        "base": json.loads((DATOS / "base_resumen.json").read_text()),
        "regla_var": A["regla"]["variable"],
        "regla_var_gto": B["regla"]["variable"],
    }


def revisar(M: dict, titulo_n: int) -> None:
    """Lo que el texto fijo afirma, contra los datos. Si algo deja de ser cierto, se detiene."""
    esc = {r["k"]: r for r in M["escalera"]}
    assert esc["boosting"]["v"] == titulo_n
    assert M["regla_var"] == "issste" and M["regla_var_gto"] == "issste", "la regla simple ya no es el ISSSTE"
    lm = M["leon"]
    assert lm["hits"] / lm["k"] >= 0.5, "en León el modelo ya no acierta el orden"
    assert esc["boosting"]["v"] > max(esc["svm"]["v"], esc["logistica"]["v"]), "el boosting ya no gana"
    assert esc["censo"]["v"] > esc["estado"]["v"], "el censo ya no supera al estado"
    assert esc["historia"]["v"] > esc["boosting"]["v"], "la historia ya no mejora"
    assert M["solo_historia"] > esc["boosting"]["v"], "la historia sola ya no supera al censo"
    assert M["importancia"][0]["g"] == "El estado" and M["importancia"][1]["g"] == "Escolaridad", \
        "cambió el orden de importancia"
    ci = {r["k"]: r for r in M["ciegas"]}
    assert ci["logistica"]["v"] == max(r["v"] for r in M["ciegas"]), "en Guanajuato a ciegas ya no gana la logística"
    assert ci["boosting"]["v"] < ci["svm"]["v"], "en Guanajuato a ciegas el boosting ya no queda abajo del SVM"
    mun = {r["n"]: r for r in M["mun"]}
    assert mun["León"]["r"] > mun["León"]["p"], "León ya no vota más de lo predicho"
    assert mun["Irapuato"]["r"] < mun["Irapuato"]["p"], "Irapuato ya no vota menos de lo predicho"
    cu = M["curvas"]["escolaridad"]
    assert cu["y"][-1] > cu["y"][0], "la escolaridad ya no sube la participación"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fecha", default=FECHA)
    args = ap.parse_args()
    M = meta(args.fecha)
    n = next(r["v"] for r in M["escalera"] if r["k"] == "boosting")
    titulo = f"De 100 secciones que el modelo señaló, en {n} votó menos de la mitad"
    revisar(M, n)
    html = PLANTILLA.read_text(encoding="utf-8")
    js = json.dumps(M, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = (html.replace("__TITULO__", titulo).replace("__AUTOR__", AUTOR).replace("__FECHA__", args.fecha)
                .replace("__EMAIL__", CORREO).replace("__META__", js)
                .replace("/*__LEAFLET_CSS__*/", (LEAFLET / "leaflet.css").read_text(encoding="utf-8"))
                .replace("/*__LEAFLET_JS__*/", (LEAFLET / "leaflet.js").read_text(encoding="utf-8")
                         .replace("</script", "<\\/script")))
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(html, encoding="utf-8")
    print(f"{SALIDA.relative_to(BASE)}: {len(html) / 1024:.0f} KB | {titulo}")


if __name__ == "__main__":
    main()
