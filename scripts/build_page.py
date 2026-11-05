"""
Cifra Pública — Negocios de León por zona y giro.

Paso 3: arma la página del mapa a partir de las salidas de compara.py (y de extras.py, si existe).
Comparación principal: dos ediciones completas del DENUE (base → final).
Opcional: una edición reciente parcial, que solo se reporta con sus límites.

Uso:
    python -I scripts/build_page.py --base 2019-11 --final 2024-11 --reciente 2025-05 \
        --autor "Nombre Apellido" --correo cifrapublicamx@gmail.com --fecha "5 de noviembre de 2026"
Salida:
    mapa-leon/index.html (usa assets/ para fuentes, logotipo y favicon)
"""
import argparse
import json
import math
from pathlib import Path

import h3
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
PROC = BASE / "data" / "processed"
PLANTILLA = BASE / "site_src" / "mapa-leon.html"
LEAFLET = BASE / "node_modules" / "leaflet" / "dist"
SALIDA = BASE / "mapa-leon" / "index.html"

PLAZA_PRINCIPAL = (21.1221, -101.6826)
ANILLOS = [(0, 2, "0–2 km"), (2, 4, "2–4 km"), (4, 6, "4–6 km"), (6, 8, "6–8 km"), (8, 99, "Más de 8 km")]
SLUG = {"Total": "total", "Restaurantes": "rest", "Cafeterías y neverías": "cafe", "Farmacias": "farm",
        "Gimnasios": "gym", "Estéticas y peluquerías": "este", "Abarrotes y minisúpers": "abar"}
GRANDES = {"51 a 100 personas", "101 a 250 personas", "251 y más personas"}


def km_al_centro(hx: str) -> float:
    lat, lon = h3.cell_to_latlng(hx)
    dy = (lat - PLAZA_PRINCIPAL[0]) * 110.57
    dx = (lon - PLAZA_PRINCIPAL[1]) * 111.32 * math.cos(math.radians(PLAZA_PRINCIPAL[0]))
    return math.hypot(dx, dy)


def anillos(feats: list, sin_nuevas: bool = False) -> list:
    out = []
    for lo, hi, nombre in ANILLOS:
        sel = [f["properties"] for f in feats
               if lo <= km_al_centro(f["properties"]["hex"]) < hi and not (sin_nuevas and f["properties"]["nueva"])]
        a, b = sum(p["total_a"] for p in sel), sum(p["total_b"] for p in sel)
        out.append({"anillo": nombre, "a": a, "b": b, "pct": round(100 * (b - a) / a, 1)})
    return out


def resumen(a: str, b: str) -> dict:
    res = pd.read_csv(PROC / f"resumen_{a}_{b}.csv", index_col=0)
    return {SLUG[g]: {"a": int(r[a]), "b": int(r[b]), "ya_no": int(r.ya_no_aparecen),
                      "nuevos": int(r.aparecen_nuevos), "pct": float(r["cambio_%"])}
            for g, r in res.iterrows() if g in SLUG}


def main(args) -> None:
    a, b, c = args.base, args.final, args.reciente
    geo = json.loads((PROC / f"cambio_{a}_{b}.geojson").read_text(encoding="utf-8"))
    meta = {"version_a": a, "version_b": b, "min_base_pct": geo["metadata"]["min_base_pct"],
            "resumen": resumen(a, b), "anillos": anillos(geo["features"]),
            "anillo_ext_sin_nuevas_pct": anillos(geo["features"], sin_nuevas=True)[-1]["pct"],
            "autor": args.autor, "fecha": args.fecha}
    extras = PROC / f"extras_{a}_{b}.json"
    if extras.exists():  # calzado y curiosidades (scripts/extras.py)
        meta["extras"] = json.loads(extras.read_text(encoding="utf-8"))

    if c:  # edición reciente (parcial): conteos por hexágono y un resumen con sus límites
        g2 = json.loads((PROC / f"cambio_{b}_{c}.geojson").read_text(encoding="utf-8"))
        por_hex = {f["properties"]["hex"]: f["properties"] for f in g2["features"]}
        for f in geo["features"]:
            p2 = por_hex.get(f["properties"]["hex"], {})
            for s in SLUG.values():
                f["properties"][f"{s}_c"] = p2.get(f"{s}_b", 0)
        fuera = sum(p["total_b"] for hx, p in por_hex.items()
                    if hx not in {f["properties"]["hex"] for f in geo["features"]})
        B = pd.read_csv(PROC / f"leon_{b}.csv.gz", dtype=str)
        C = pd.read_csv(PROC / f"leon_{c}.csv.gz", dtype=str, usecols=["id"])
        ya_no = B[~B.id.isin(C.id)]
        meta["reciente"] = {
            "version": c, "resumen": resumen(b, c)["total"], "anillos": anillos(g2["features"]),
            "grandes_pct_todos": round(100 * B.per_ocu.isin(GRANDES).mean(), 1),
            "grandes_pct_ya_no": round(100 * ya_no.per_ocu.isin(GRANDES).mean(), 1),
            "negocios_fuera_del_mapa": int(fuera)}

    dump = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = PLANTILLA.read_text(encoding="utf-8")
    html = (html.replace("/*__LEAFLET_CSS__*/", (LEAFLET / "leaflet.css").read_text(encoding="utf-8"))
                .replace("/*__LEAFLET_JS__*/", (LEAFLET / "leaflet.js").read_text(encoding="utf-8").replace("</script", "<\\/script"))
                .replace("__GEO__", dump(geo)).replace("__META__", dump(meta))
                .replace("__EMAIL__", args.correo).replace("__AUTOR__", args.autor).replace("__FECHA__", args.fecha))
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(html, encoding="utf-8")
    print(f"{SALIDA} ({SALIDA.stat().st_size / 1024:.0f} KB)")
    print("anillos:", [(r["anillo"], r["pct"]) for r in meta["anillos"]],
          "| exterior sin zonas nuevas:", meta["anillo_ext_sin_nuevas_pct"])
    if c:
        r = meta["reciente"]
        print(f"reciente {c}:", r["resumen"], "| anillos:", [(x["anillo"], x["pct"]) for x in r["anillos"]],
              f"| 51+ personas: {r['grandes_pct_todos']}% del total vs {r['grandes_pct_ya_no']}% de los que ya no aparecen",
              f"| negocios {c} fuera del mapa: {r['negocios_fuera_del_mapa']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--final", required=True)
    ap.add_argument("--reciente")
    ap.add_argument("--autor", default="Rodrigo")
    ap.add_argument("--correo", default="cifrapublicamx@gmail.com")
    ap.add_argument("--fecha", required=True)
    main(ap.parse_args())
