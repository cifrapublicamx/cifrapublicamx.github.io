"""
Cifra Pública — Negocios de León por zona y giro.

Paso 2: compara dos versiones procesadas por pipeline.py.
El id del DENUE se conserva entre versiones, así que además del cambio neto se pueden
contar aperturas (ids nuevos) y cierres (ids que desaparecen). Ojo: un id que desaparece
no siempre es un cierre; puede ser un cambio de registro. Se reporta como "ya no aparece".

Salidas en data/processed/:
  - cambio_<a>_<b>.geojson : hexágonos con conteos, cambio, % de cambio, aperturas y cierres por giro
  - resumen_<a>_<b>.csv     : totales de León por giro

Uso:
    python -I compara.py 2019-11 2024-11
"""
import json
import sys
from pathlib import Path

import h3
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
PROC = BASE / "data" / "processed"
MIN_BASE = 20      # sin % de cambio en hexágonos con menos negocios en la versión inicial
NUEVA = (5, 20)    # "zona nueva en el directorio": <5 negocios antes y >=20 después
SLUG = {"Total": "total", "Restaurantes": "rest", "Cafeterías y neverías": "cafe",
        "Farmacias": "farm", "Gimnasios": "gym", "Estéticas y peluquerías": "este",
        "Abarrotes y minisúpers": "abar"}


def check_codigos(a: str, b: str) -> None:
    import pipeline
    codigos = set(pipeline.GIROS)
    ca, cb = (pd.read_csv(PROC / f"codigos_{v}.csv", dtype=str) for v in (a, b))
    ca, cb = (c[c.codigo_act.isin(codigos)] for c in (ca, cb))
    faltan = {v: sorted(codigos - set(c.codigo_act)) for v, c in ((a, ca), (b, cb))}
    n = ca.merge(cb, on="codigo_act", suffixes=("_a", "_b"))
    renom = n[n.nombre_act_a.str.strip() != n.nombre_act_b.str.strip()]
    print("== Códigos SCIAN de los giros ==")
    print("códigos sin registros:", faltan, "| mismo código con otro nombre:", len(renom))


def etiquetas(df: pd.DataFrame) -> pd.Series:
    """Colonia(s) principal(es) de cada hexágono, juntando variantes del mismo nombre."""
    d = df[df.colonia_clave != ""]
    cuenta = d.groupby(["hex", "colonia_clave"]).size().rename("n").reset_index()
    nombre = (d.groupby(["colonia_clave"]).colonia
                .agg(lambda s: s.value_counts().index[0]))   # forma más común del nombre
    out = {}
    for hx, g in cuenta.sort_values("n", ascending=False).groupby("hex", sort=False):
        top = g.head(2).reset_index(drop=True)
        lab = nombre[top.colonia_clave[0]]
        if len(top) > 1 and top.n[1] >= 0.5 * top.n[0]:
            lab += " / " + nombre[top.colonia_clave[1]]
        out[hx] = lab
    return pd.Series(out, name="colonia")


def main(a: str, b: str) -> None:
    sys.path.insert(0, str(Path(__file__).parent))
    check_codigos(a, b)
    A = pd.read_csv(PROC / f"leon_{a}.csv.gz", dtype=str)
    B = pd.read_csv(PROC / f"leon_{b}.csv.gz", dtype=str)
    A["sigue"] = A.id.isin(B.id)
    B["nuevo"] = ~B.id.isin(A.id)
    giros = ["Total"] + sorted(set(A.giro.dropna()) | set(B.giro.dropna()))

    def tabla(df, flag=None):
        t = df if flag is None else df[df[flag]]
        tot = t.groupby("hex").size().rename("Total")
        g = t.dropna(subset=["giro"]).groupby(["hex", "giro"]).size().unstack(fill_value=0)
        return pd.concat([tot, g], axis=1)

    idx = pd.Index(sorted(set(A.hex) | set(B.hex)), name="hex")
    na, nb = tabla(A), tabla(B)
    cierres = tabla(A.assign(fue=~A.sigue), "fue")
    aperturas = tabla(B, "nuevo")
    na, nb, cierres, aperturas = (x.reindex(index=idx, columns=giros).fillna(0).astype(int)
                                  for x in (na, nb, cierres, aperturas))
    lab = etiquetas(pd.concat([A, B]))

    features = []
    for hx in idx:
        p = {"hex": hx, "colonia": lab.get(hx, ""),
             "nueva": bool(na.at[hx, "Total"] < NUEVA[0] and nb.at[hx, "Total"] >= NUEVA[1])}
        for g in giros:
            s, n0, n1 = SLUG[g], int(na.at[hx, g]), int(nb.at[hx, g])
            p.update({f"{s}_a": n0, f"{s}_b": n1, f"{s}_d": n1 - n0,
                      f"{s}_pct": round(100 * (n1 - n0) / n0, 1) if n0 >= MIN_BASE else None,
                      f"{s}_ape": int(aperturas.at[hx, g]), f"{s}_cie": int(cierres.at[hx, g])})
        ring = [[round(lng, 5), round(lat, 5)] for lat, lng in h3.cell_to_boundary(hx)]
        features.append({"type": "Feature", "properties": p,
                         "geometry": {"type": "Polygon", "coordinates": [ring + [ring[0]]]}})
    meta = {"version_a": a, "version_b": b, "giros": {SLUG[g]: g for g in giros},
            "min_base_pct": MIN_BASE}
    out = PROC / f"cambio_{a}_{b}.geojson"
    out.write_text(json.dumps({"type": "FeatureCollection", "metadata": meta, "features": features},
                              ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    res = pd.DataFrame({a: na.sum(), b: nb.sum(), "ya_no_aparecen": cierres.sum(),
                        "aparecen_nuevos": aperturas.sum()})
    res["cambio"] = res[b] - res[a]
    res["cambio_%"] = (100 * res.cambio / res[a]).round(1)
    res["siguen_%"] = (100 * (1 - res.ya_no_aparecen / res[a])).round(1)
    res.to_csv(PROC / f"resumen_{a}_{b}.csv")
    print(f"\n== León {a} → {b} ==\n{res.to_string()}")

    d = pd.DataFrame({"colonia": lab.reindex(idx), a: na.Total, b: nb.Total,
                      "cambio": nb.Total - na.Total, "aperturas": aperturas.Total, "ya_no": cierres.Total})
    d["%"] = (100 * d.cambio / d[a]).where(d[a] >= MIN_BASE).round(1)
    nuevas = d[(d[a] < NUEVA[0]) & (d[b] >= NUEVA[1])]
    base = d[d[a] >= MIN_BASE]
    print("\nTop 10 que más ganaron (zonas con ≥20 negocios en la versión inicial):\n", base.nlargest(10, "cambio").to_string())
    print("\nTop 10 que más perdieron:\n", base.nsmallest(10, "cambio").to_string())
    print(f"\nZonas nuevas en el directorio ({len(nuevas)}; {int(nuevas[b].sum())} negocios en {b}):\n",
          nuevas.sort_values(b, ascending=False).to_string())
    print(f"\nGeoJSON: {out} ({out.stat().st_size / 1024:.0f} KB, {len(features)} hexágonos)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
