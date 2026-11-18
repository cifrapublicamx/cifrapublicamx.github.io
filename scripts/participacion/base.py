"""Análisis 006 | Une participación por sección (INE) con el Censo 2020 por sección (ECEG, INEGI)
y arma las variables del modelo. También ubica cada sección con las coordenadas de sus casillas.

Uso: python base.py <participacion_seccion.csv> <INE_SECCION_2020.csv> <casillas2024lonlat.csv> <salida.csv>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def div(a, b):
    a, b = a.astype(float), b.astype(float)
    return np.where(b > 0, a / b, np.nan)


def main():
    part_path, eceg_path, coords_path, salida = sys.argv[1:5]
    part = pd.read_csv(part_path)
    e = pd.read_csv(eceg_path, low_memory=False)
    e = e.rename(columns={"ENTIDAD": "entidad", "SECCION": "seccion"})
    num = [c for c in e.columns if c not in ("ID", "entidad", "DISTRITO", "MUNICIPIO", "seccion", "TIPO")]
    for c in num:
        e[c] = pd.to_numeric(e[c], errors="coerce")  # '*' = dato reservado

    f = pd.DataFrame({"entidad": e.entidad, "seccion": e.seccion, "municipio": e.MUNICIPIO,
                      "tipo": e.TIPO, "pobtot": e.POBTOT, "pob18": e.P_18YMAS})
    a18 = e.P_18YMAS
    # Edad (sobre adultos)
    f["jovenes_18_24"] = div(e.P_18A24, a18)
    f["mayores_60"] = div(e.P_60YMAS, a18)
    # Educación
    f["escolaridad"] = e.GRAPROES
    f["posbasica"] = div(e.P18YM_PB, a18)
    f["analfabeta"] = div(e.P15YM_AN, e.P_15YMAS)
    # Trabajo y seguridad social
    f["pea"] = div(e.PEA, e.P_12YMAS)
    f["pea_mujeres"] = div(e.PEA_F, e.P_12YMAS_F)
    f["sin_afiliacion"] = div(e.PSINDER, e.POBTOT)
    f["imss"] = div(e.PDER_IMSS, e.POBTOT)
    f["issste"] = div(e.PDER_ISTE.fillna(0) + e.PDER_ISTEE.fillna(0), e.POBTOT)
    # Hogares y familia
    f["casados"] = div(e.P12YM_CASA, e.P_12YMAS)
    f["ocupantes_vivienda"] = e.PROM_OCUP
    f["jefa_mujer"] = div(e.HOGJEF_F, e.TOTHOG)
    # Migración y arraigo
    f["nacidos_otro_estado"] = div(e.PNACOE, e.POBTOT)
    f["llegaron_desde_2015"] = div(e.PRESOE15, e.P_5YMAS)
    f["casas_deshabitadas"] = div(e.VIVPAR_DES, e.TVIVPAR)
    f["casas_temporales"] = div(e.VIVPAR_UT, e.TVIVPAR)
    # Etnicidad
    f["lengua_indigena"] = div(e.P3YM_HLI, e.P_3YMAS)
    f["afro"] = div(e.POB_AFRO, e.POBTOT)
    # Vivienda y bienes
    v = e.TVIVPARHAB
    f["auto"] = div(e.VPH_AUTOM, v)
    f["internet"] = div(e.VPH_INTER, v)
    f["computadora"] = div(e.VPH_PC, v)
    f["piso_tierra"] = div(e.VPH_PISOTI, v)
    f["sin_drenaje"] = div(e.VPH_NODREN, v)
    f["streaming"] = div(e.VPH_SPMVPI, v)

    # Participación por año
    for anio in (2018, 2021, 2024):
        p = part[part.anio == anio][["entidad", "seccion", "votos", "lista", "casillas", "urbana"]]
        p = p.rename(columns={c: f"{c}_{anio}" for c in ("votos", "lista", "casillas", "urbana")})
        f = f.merge(p, on=["entidad", "seccion"], how="left")
        f[f"part_{anio}"] = div(f[f"votos_{anio}"], f[f"lista_{anio}"])

    # Registro contra población: personas en lista nominal por adulto que vivía ahí en 2020
    f["lista_por_adulto"] = div(f.lista_2024, f.pob18)

    # Coordenadas: promedio de las casillas de la sección (2024)
    c = pd.read_csv(coords_path)
    c = c.rename(columns={"edon": "entidad"})
    cg = c.groupby(["entidad", "seccion"]).agg(lon=("lon", "mean"), lat=("lat", "mean"),
                                               mun_ine=("mun", "first")).reset_index()
    f = f.merge(cg, on=["entidad", "seccion"], how="left")

    resumen = {
        "secciones_censo": int(len(e)),
        "secciones_ine_2024": int((part.anio == 2024).sum()),
        "con_participacion": {str(a): int(f[f"part_{a}"].notna().sum()) for a in (2018, 2021, 2024)},
        "con_coordenadas": int(f.lon.notna().sum()),
    }
    resumen["ine_2024_sin_censo"] = resumen["secciones_ine_2024"] - resumen["con_participacion"]["2024"]
    print(json.dumps(resumen, indent=1))
    f.to_csv(salida, index=False)
    (Path(salida).parent / "base_resumen.json").write_text(json.dumps(resumen, indent=1))


if __name__ == "__main__":
    main()
