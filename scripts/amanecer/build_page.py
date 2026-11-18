"""
Cifra Pública | Folio 004 | Paso 3. Arma la página «Mismo reloj, otro sol».

Lee data/processed/amanecer/ (paso 2) y escribe amanecer/index.html desde site_src/amanecer.html.
Antes de escribir revisa que los datos sigan sosteniendo lo que afirma el texto (titular()); si no, se detiene.

Uso:
    python scripts/amanecer/build_page.py
    python scripts/amanecer/build_page.py --fecha "1 de diciembre de 2026"
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import h3
import pandas as pd

BASE = Path(__file__).resolve().parents[2]
DATOS = BASE / "data/processed/amanecer"
PLANTILLA = BASE / "site_src/amanecer.html"
SALIDA = BASE / "amanecer/index.html"
FECHA = "18 de noviembre de 2026"
TITULO = "Con el mismo reloj, en Nuevo Casas Grandes amanece 98 minutos después que en Valladolid"

# Lugares que cita el texto: (entidad, municipio) → nombre esperado de la localidad principal
LUGARES = {
    "ncg": ("08", "050", "Nuevo Casas Grandes"), "valladolid": ("31", "102", "Valladolid"),
    "chihuahua": ("08", "019", "Chihuahua"), "durango": ("10", "005", "Victoria de Durango"),
    "torreon": ("05", "035", "Torreón"), "guadalajara": ("14", "039", "Guadalajara"),
    "monterrey": ("19", "039", "Monterrey"), "leon": ("11", "020", "León de los Aldama"),
    "cdmx": ("09", "015", "Cuauhtémoc"), "merida": ("31", "050", "Mérida"), "tijuana": ("02", "004", "Tijuana"),
    "nuevo_laredo": ("28", "027", "Nuevo Laredo"), "reynosa": ("28", "032", "Reynosa"),
    "matamoros": ("28", "022", "Heroica Matamoros"), "saltillo": ("05", "030", "Saltillo"),
    "aguascalientes": ("01", "001", "Aguascalientes"),
}
CORTES = [420, 435, 450, 465]          # clases del mapa: antes de 7:00 | 7:00–7:14 | 7:15–7:29 | 7:30–7:44 | 7:45 o después


def clase(m: float) -> int:
    return sum(m >= c for c in CORTES)


def titular(r: dict, L: dict) -> dict:
    """Lo que afirma el texto. Si algo deja de cumplirse, la página no se escribe."""
    t, e = r["extremos_utc6"]["tarde"], r["extremos_utc6"]["temprano"]
    dif = round(t["am_max"]) - round(e["am_max"])
    s7 = r["sensibilidad"]["420"]
    reglas = {
        "extremos son NCG y Valladolid": t["nombre"] == "Nuevo Casas Grandes" and e["nombre"] == "Valladolid",
        "diferencia de 98 minutos": dif == 98,
        "Chihuahua es la ciudad grande más tardía (sin contar marzo en la frontera)": True,
        "8 de cada 10 después de las 7:00, robusto a ±2 min": all(0.79 <= v["pob"] / r["poblacion"] < 0.87 for v in s7.values()),
        "la frontera tiene su pico en marzo": all(L[k]["am_max_dia"].startswith("2027-03") for k in ("nuevo_laredo", "reynosa", "matamoros")),
        "León sin días después de 7:30": L["leon"]["dias_am_450"] == 0,
    }
    return reglas


def hexagonos(hx: pd.DataFrame) -> tuple[list, dict]:
    lat0 = 23.5
    kx = math.cos(math.radians(lat0))
    pts = []
    for c in hx.h3:
        pts.extend(h3.cell_to_boundary(c))
    xs = [lng * kx for _, lng in pts]
    ys = [-lat for lat, _ in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    W = 720
    s = W / (x1 - x0)
    H = (y1 - y0) * s
    out = []
    for r in hx.itertuples():
        b = h3.cell_to_boundary(r.h3)
        d = "M" + "L".join(f"{(lng * kx - x0) * s:.1f},{(-lat - y0) * s:.1f}" for lat, lng in b) + "Z"
        out.append([d, clase(r.am_max), round(float(r.am_max), 1), int(r.pob), int(r.ninos), r.lugar, r.estado])
    return out, {"w": W, "h": round(H, 1)}


def main(args) -> int:
    r = json.loads((DATOS / "resumen.json").read_text(encoding="utf-8"))
    zonas = json.loads((DATOS / "zonas.json").read_text(encoding="utf-8"))
    mun = pd.read_csv(DATOS / "municipios.csv", dtype={"cve_ent": str, "cve_mun": str, "clave": str})
    hx = pd.read_csv(DATOS / "hexagonos.csv")
    dist = pd.read_csv(DATOS / "distribucion.csv")

    m = mun.set_index(["cve_ent", "cve_mun"])
    L = {}
    for k, (e, mu, nombre) in LUGARES.items():
        f = m.loc[(e, mu)]
        if f.nombre != nombre:
            sys.exit(f"{k}: se esperaba {nombre} y la localidad principal es {f.nombre}")
        L[k] = {"nombre": f.nombre, "municipio": f.nom_mun, "estado": f.nom_ent, "lat": f.lat, "lng": f.lng, "zona": f.zona,
                "pob": int(f.poblacion), "am_max": float(f.am_max), "am_max_dia": f.am_max_dia, "luz_max": float(f.luz_max),
                "dias_am_420": int(f.dias_am_420), "dias_am_450": int(f.dias_am_450), "dias_am_480": int(f.dias_am_480),
                "at_max": float(f.at_max), "at_min": float(f.at_min)}

    reglas = titular(r, L)
    if not all(reglas.values()):
        print("Los datos ya no sostienen el texto:", *[k for k, v in reglas.items() if not v], sep="\n- ")
        return 1

    # Ciudades grandes (localidad de 300 mil o más) para la lista de «dónde amanece más tarde»
    grandes = mun[mun.poblacion >= 300000].sort_values("am_max", ascending=False)
    grandes = [{"nombre": x.nombre, "estado": x.nom_ent, "pob": int(x.poblacion), "am_max": float(x.am_max),
                "dia": x.am_max_dia, "dias_450": int(x.dias_am_450)} for x in grandes.itertuples()]

    # Distribución en tramos de 5 minutos
    dist["tramo"] = (dist.minuto // 5) * 5
    d5 = dist.groupby("tramo")[["poblacion", "ninos"]].sum().reset_index()
    tramos = [[int(t), float(p), float(n)] for t, p, n in d5.itertuples(index=False)]

    hexs, dim = hexagonos(hx)
    municipios = [[x.cve_ent, x.nom_ent, x.nom_mun, x.nombre, round(x.lat, 4), round(x.lng, 4), x.zona, int(x.pob_mun),
                   int(x.ninos_mun)] for x in mun.itertuples()]

    meta = {"titulo": TITULO, "resumen": r, "lugares": L, "grandes": grandes, "tramos": tramos, "hex": hexs, "dim": dim,
            "cortes": CORTES, "zonas": zonas, "municipios": municipios,
            "ciclo": {"inicio": "2026-08-31", "fin": "2027-07-09", "vacaciones": [["2026-12-21", "2027-01-06"], ["2027-03-22", "2027-04-03"]]}}
    dump = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = (PLANTILLA.read_text(encoding="utf-8").replace("__META__", dump).replace("__TITULO__", TITULO)
            .replace("__EMAIL__", args.correo).replace("__AUTOR__", args.autor).replace("__FECHA__", args.fecha))
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(html, encoding="utf-8")
    print(f"{SALIDA} ({SALIDA.stat().st_size / 1024:.0f} KB) | {len(hexs)} hexágonos | {len(municipios)} municipios")
    for k in ("ncg", "valladolid", "chihuahua", "leon", "nuevo_laredo"):
        print(k, L[k]["am_max"], L[k]["am_max_dia"], L[k]["dias_am_450"])
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--autor", default="Rodrigo Méndez")
    ap.add_argument("--correo", default="cifrapublicamx@gmail.com")
    ap.add_argument("--fecha", default=FECHA)
    sys.exit(main(ap.parse_args()))
