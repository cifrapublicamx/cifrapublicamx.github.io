"""
Cifra Pública — Negocios de León por zona y giro.

Paso 2b: cifras de apoyo para la pieza (calzado y curiosidades), a partir de las tablas de pipeline.py.

Uso:
    python -I scripts/extras.py 2019-11 2024-11
Salida:
    data/processed/extras_<a>_<b>.json
"""
import json
import sys
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
PROC = BASE / "data" / "processed"

TAMANOS = {"Hasta 5 personas": ["0 a 5 personas"],
           "De 6 a 50": ["6 a 10 personas", "11 a 30 personas", "31 a 50 personas"],
           "Más de 50": ["51 a 100 personas", "101 a 250 personas", "251 y más personas"]}
CURIOSIDADES = {
    "ciber": {"nombre": "Cibercafés", "codigos": ["561432"]},
    "mascotas": {"nombre": "Tiendas de mascotas y veterinarias", "codigos": ["465911", "541941"]},
    "consultorios": {"nombre": "Consultorios de psicología, nutrición y quiropráctica", "codigos": ["621331", "621391", "621311"]},
    "quiro": {"nombre": "Consultorios de quiropráctica", "codigos": ["621311"]},
    "limpieza": {"nombre": "Tiendas de artículos de limpieza", "codigos": ["467115"]},
}
CALZADO = "3162"            # fabricación de calzado
ZAPATERIAS = "46321"        # comercio al por menor de calzado


def main(a: str, b: str) -> None:
    A = pd.read_csv(PROC / f"leon_{a}.csv.gz", dtype=str)
    B = pd.read_csv(PROC / f"leon_{b}.csv.gz", dtype=str)
    geo = json.loads((PROC / f"cambio_{a}_{b}.geojson").read_text(encoding="utf-8"))
    coecillo = [f["properties"]["hex"] for f in geo["features"] if "Coecillo" in f["properties"]["colonia"]]

    cal = lambda d: d[d.codigo_act.str.startswith(CALZADO)]
    ca, cb = cal(A), cal(B)
    out = {"calzado": {
        "a": len(ca), "b": len(cb), "siguen_pct": round(100 * ca.id.isin(B.id).mean(), 1),
        "siguen_pct_todos": round(100 * A.id.isin(B.id).mean(), 1),
        "tamanos": [{"tamano": t, "a": int(ca.per_ocu.isin(v).sum()), "b": int(cb.per_ocu.isin(v).sum())} for t, v in TAMANOS.items()],
        "coecillo": {"hexagonos": len(coecillo),
                     "calzado_a": int(ca.hex.isin(coecillo).sum()), "calzado_b": int(cb.hex.isin(coecillo).sum()),
                     "total_a": int(A.hex.isin(coecillo).sum()), "total_b": int(B.hex.isin(coecillo).sum())},
        "zapaterias_a": int(A.codigo_act.str.startswith(ZAPATERIAS).sum()),
        "zapaterias_b": int(B.codigo_act.str.startswith(ZAPATERIAS).sum()),
    }}
    for t in out["calzado"]["tamanos"]:
        t["pct"] = round(100 * (t["b"] - t["a"]) / t["a"], 1)

    out["curiosidades"] = {}
    for k, c in CURIOSIDADES.items():
        n0, n1 = int(A.codigo_act.isin(c["codigos"]).sum()), int(B.codigo_act.isin(c["codigos"]).sum())
        out["curiosidades"][k] = {"nombre": c["nombre"], "a": n0, "b": n1, "pct": round(100 * (n1 - n0) / n0, 1)}

    # ¿Las tiendas de limpieza son el giro de 6 dígitos con 500+ negocios que más creció?
    ga, gb = A.groupby("codigo_act").size(), B.groupby("codigo_act").size()
    t = pd.DataFrame({"a": ga, "b": gb}).fillna(0)
    t = t[t.a >= 500]
    t["pct"] = 100 * (t.b - t.a) / t.a
    rank = t.sort_values("pct", ascending=False)
    out["limpieza_es_el_que_mas_crecio_500"] = bool(rank.index[0] == "467115")
    out["giros_500_que_mas_crecieron"] = [(i, round(r.pct, 1)) for i, r in rank.head(4).iterrows()]

    (PROC / f"extras_{a}_{b}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
