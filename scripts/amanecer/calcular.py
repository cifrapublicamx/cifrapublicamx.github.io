"""
Cifra Pública | Folio 004 | Paso 2. Amanecer y primera luz en cada localidad, cada día del ciclo escolar 2026-2027.

Lee data/raw/amanecer/localidades_2020.csv (paso 1) y escribe en data/processed/amanecer/:
  municipios.csv      localidad principal de cada municipio (la más poblada) con sus horas, más población y niños del municipio
  hexagonos.csv       hexágonos H3 (resolución 4) con población, niños y amanecer más tardío ponderado por población
  distribucion.csv    población y niños de 3 a 14 años por minuto del amanecer más tardío en día de clase
  zonas.json          minutos de diferencia con UTC de cada zona horaria, día por día (para que la página calcule igual)
  resumen.json        cifras que cita el texto de la página

Zonas: Ley de los Husos Horarios en los Estados Unidos Mexicanos (DOF 28-10-2022, reforma 29-11-2022);
cambios de horario estacional tomados de IANA tzdata.
Ciclo escolar 2026-2027 (SEP): 31 ago 2026 a 9 jul 2027; vacaciones 21 dic a 6 ene y 22 mar a 3 abr.
Se cuentan los días entre semana fuera de vacaciones (202); el calendario oficial tiene 185 días de clase.

Uso: python scripts/amanecer/calcular.py
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import h3
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sol import evento_utc_min, offset_horas  # noqa: E402

BASE = Path(__file__).resolve().parents[2]
ENTRADA = BASE / "data/raw/amanecer/localidades_2020.csv"
SALIDA = BASE / "data/processed/amanecer"

INICIO, FIN = date(2026, 8, 31), date(2027, 7, 9)
VACACIONES = [(date(2026, 12, 21), date(2027, 1, 6)), (date(2027, 3, 22), date(2027, 4, 3))]
ANIO = 2027                      # año calendario para atardeceres
UMBRALES = (420, 450, 480)       # 7:00, 7:30, 8:00
CENIT_AMANECER, CENIT_LUZ = 90.833, 96.0
RES_H3 = 4

# Zonas horarias por municipio (claves INEGI)
CJ = {"035", "005", "037", "053", "028"}          # Chihuahua, frontera oeste: Janos, Ascensión, Juárez, Praxedis G. Guerrero, Guadalupe
OJ = {"015", "052", "042"}                       # Chihuahua, frontera este: Coyame del Sotol, Ojinaga, Manuel Benavides
COAH = {"002", "003", "012", "013", "014", "019", "022", "023", "025", "037", "038"}
TAMS = {"027", "014", "024", "025", "007", "015", "032", "033", "040", "022"}
ZONAS = ["America/Mexico_City", "America/Chihuahua", "America/Bahia_Banderas", "America/Matamoros", "America/Ojinaga",
         "America/Ciudad_Juarez", "America/Mazatlan", "America/Hermosillo", "America/Tijuana", "America/Cancun"]


def zona(e: str, m: str) -> str:
    if e == "23": return "America/Cancun"
    if e == "02": return "America/Tijuana"
    if e in ("03", "25"): return "America/Mazatlan"
    if e == "26": return "America/Hermosillo"
    if e == "18": return "America/Bahia_Banderas" if m == "020" else "America/Mazatlan"
    if e == "08": return "America/Ciudad_Juarez" if m in CJ else ("America/Ojinaga" if m in OJ else "America/Chihuahua")
    if (e == "05" and m in COAH) or (e == "19" and m == "005") or (e == "28" and m in TAMS): return "America/Matamoros"
    return "America/Mexico_City"


def dias_clase() -> list[date]:
    out, d = [], INICIO
    while d <= FIN:
        if d.weekday() < 5 and not any(a <= d <= b for a, b in VACACIONES):
            out.append(d)
        d += timedelta(days=1)
    return out


def main() -> None:
    loc = pd.read_csv(ENTRADA, dtype={"cve_ent": str, "cve_mun": str, "clave": str})
    loc["zona"] = [zona(e, m) for e, m in zip(loc.cve_ent, loc.cve_mun)]
    lat, lon, zonas = loc.lat.to_numpy(float), loc.lng.to_numpy(float), loc.zona.to_numpy()

    def off(d):
        o = np.zeros(len(loc))
        for z in ZONAS: o[zonas == z] = offset_horas(z, d) * 60
        return o

    dias = dias_clase()
    n = len(loc)
    tras = {u: np.zeros(n, int) for u in UMBRALES}
    luz_tras = {u: np.zeros(n, int) for u in UMBRALES}
    am_max, luz_max = np.full(n, -1.0), np.full(n, -1.0)
    am_max_dia = np.empty(n, dtype=object)
    for d in dias:
        o = off(d)
        am = evento_utc_min(d, lat, lon, CENIT_AMANECER) + o
        luz = evento_utc_min(d, lat, lon, CENIT_LUZ) + o
        for u in UMBRALES:
            tras[u] += am > u
            luz_tras[u] += luz > u
        m = am > am_max
        am_max[m], am_max_dia[m] = am[m], d
        luz_max = np.maximum(luz_max, luz)
    at_max, at_min, am_min = np.full(n, -1.0), np.full(n, 9e9), np.full(n, 9e9)
    for i in range(365):
        d = date(ANIO, 1, 1) + timedelta(days=i)
        o = off(d)
        at = evento_utc_min(d, lat, lon, salida=False) + o
        am_min = np.minimum(am_min, evento_utc_min(d, lat, lon) + o)
        at_max, at_min = np.maximum(at_max, at), np.minimum(at_min, at)

    loc["am_max"], loc["am_max_dia"], loc["luz_max"] = am_max, am_max_dia, luz_max
    for u in UMBRALES:
        loc[f"dias_am_{u}"], loc[f"dias_luz_{u}"] = tras[u], luz_tras[u]
    loc["at_max"], loc["at_min"], loc["am_min"] = at_max, at_min, am_min
    loc["p3a14"] = loc["p3a14"].fillna(0)
    SALIDA.mkdir(parents=True, exist_ok=True)

    # Municipios: localidad principal + totales del municipio
    tot = loc.groupby(["cve_ent", "cve_mun"]).agg(pob_mun=("poblacion", "sum"), ninos_mun=("p3a14", "sum")).reset_index()
    prin = loc.loc[loc.groupby(["cve_ent", "cve_mun"]).poblacion.idxmax()]
    mun = prin.merge(tot, on=["cve_ent", "cve_mun"])
    cols = ["cve_ent", "nom_ent", "cve_mun", "nom_mun", "clave", "nombre", "lat", "lng", "zona", "poblacion", "pob_mun",
            "ninos_mun", "am_max", "am_max_dia", "luz_max", "dias_am_420", "dias_am_450", "dias_am_480", "at_max", "at_min"]
    mun[cols].round({"lat": 5, "lng": 5, "am_max": 2, "luz_max": 2, "at_max": 2, "at_min": 2}).to_csv(SALIDA / "municipios.csv", index=False)

    # Hexágonos
    loc["h3"] = [h3.latlng_to_cell(a, b, RES_H3) for a, b in zip(lat, lon)]
    pesos = loc.poblacion.clip(lower=0)
    loc["_w"] = loc.am_max * pesos
    hx = loc.groupby("h3").agg(pob=("poblacion", "sum"), ninos=("p3a14", "sum"), w=("_w", "sum"),
                               am_min_hex=("am_max", "min"), am_max_hex=("am_max", "max")).reset_index()
    hx = hx[hx.pob > 0].copy()
    hx["am_max"] = hx.w / hx.pob
    lider = loc.sort_values("poblacion", ascending=False).drop_duplicates("h3").set_index("h3")
    hx["lugar"] = hx.h3.map(lider.nombre)
    hx["estado"] = hx.h3.map(lider.nom_ent)
    hx.drop(columns="w").round({"am_max": 2, "am_min_hex": 2, "am_max_hex": 2}).to_csv(SALIDA / "hexagonos.csv", index=False)

    # Distribución por minuto
    loc["minuto"] = np.floor(loc.am_max).astype(int)
    dist = loc.groupby("minuto").agg(poblacion=("poblacion", "sum"), ninos=("p3a14", "sum")).reset_index()
    dist.to_csv(SALIDA / "distribucion.csv", index=False)

    # Zonas: offsets por día (transiciones) del inicio del ciclo al fin de 2027
    d0, z = INICIO, {}
    for nombre in ZONAS:
        tr, prev, d = [], None, d0
        while d <= date(ANIO, 12, 31):
            o = int(round(offset_horas(nombre, d) * 60))
            if o != prev:
                tr.append([(d - d0).days, o]); prev = o
            d += timedelta(days=1)
        z[nombre] = tr
    (SALIDA / "zonas.json").write_text(json.dumps({"inicio": d0.isoformat(), "zonas": z}, ensure_ascii=False, indent=1),
                                       encoding="utf-8")

    # Resumen para el texto
    P, K = float(loc.poblacion.sum()), float(loc.p3a14.sum())
    def tras_de(u, campo="am_max"):
        m = loc[campo] > u
        return {"pob": float(loc.loc[m, "poblacion"].sum()), "ninos": float(loc.loc[m, "p3a14"].sum())}
    sens = {str(u): {str(t): tras_de(t) for t in (u - 2, u, u + 2)} for u in UMBRALES}
    c6 = loc[loc.zona.isin(["America/Mexico_City", "America/Chihuahua"]) & (loc.poblacion >= 20000)]
    tarde, temprano = c6.loc[c6.am_max.idxmax()], c6.loc[c6.am_max.idxmin()]
    m_prin = mun.set_index(["cve_ent", "cve_mun"])
    resumen = {
        "poblacion": P, "ninos": K, "localidades": int(len(loc)), "dias_clase": len(dias),
        "edades_reservadas": {"localidades": int(loc.edades_reservadas.sum()),
                              "poblacion": float(loc.loc[loc.edades_reservadas, "poblacion"].sum())},
        "sensibilidad": sens,
        "extremos_utc6": {k: {"nombre": r.nombre, "estado": r.nom_ent, "pob": float(r.poblacion), "am_max": float(r.am_max),
                              "dia": str(r.am_max_dia), "lng": float(r.lng)} for k, r in (("tarde", tarde), ("temprano", temprano))},
        "municipios_tras": {str(u): int((mun.am_max > u).sum()) for u in UMBRALES},
        "municipios_tras_480_estados": mun[mun.am_max > 480].nom_ent.value_counts().to_dict(),
        "municipios_tras_450_estados": mun[mun.am_max > 450].nom_ent.value_counts().to_dict(),
        "n_municipios": int(len(mun)),
    }
    (SALIDA / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(loc)} localidades | {len(dias)} días de clase | {len(mun)} municipios | {len(hx)} hexágonos")
    print("extremos:", tarde.nombre, round(tarde.am_max, 1), "|", temprano.nombre, round(temprano.am_max, 1))


if __name__ == "__main__":
    main()
