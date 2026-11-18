"""Cifra Pública | Folio 004 | Paso 1.
ITER 2020 (INEGI) -> tabla de localidades con coordenadas decimales, población total y por edad escolar.
Las filas 9998/9999 son subtotales de localidades de una y dos viviendas que ya aparecen una por una: se descartan
(la suma de localidades sin ellas cuadra exacto con el total nacional, 126 014 024).

Uso: python scripts/amanecer/prep_iter.py [ruta al CSV del ITER]  (por omisión data/raw/conjunto_de_datos_iter_00CSV20.csv)
Salida: data/raw/amanecer/localidades_2020.csv (no se sube al repo)."""
import re, sys
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).resolve().parents[2]
src = sys.argv[1] if len(sys.argv) > 1 else BASE / "data/raw/conjunto_de_datos_iter_00CSV20.csv"
SALIDA = BASE / "data/raw/amanecer/localidades_2020.csv"
cols = ['ENTIDAD','NOM_ENT','MUN','NOM_MUN','LOC','NOM_LOC','LONGITUD','LATITUD','POBTOT','P_3A5','P_6A11','P_12A14','P_15A17']
df = pd.read_csv(src, usecols=cols, dtype=str, encoding='utf-8-sig')
df = df[(df.ENTIDAD != '00') & (df.MUN != '000') & (~df.LOC.isin(['0000','9998','9999']))].copy()
def dms(s):
    if not isinstance(s, str): return np.nan
    m = re.match(r"\s*(\d+)°\s*(\d+)'\s*([\d.]+)\"\s*([NSEW])", s)
    if not m: return np.nan
    v = int(m[1]) + int(m[2])/60 + float(m[3])/3600
    return -v if m[4] in 'WS' else v
df['lat'] = df.LATITUD.map(dms); df['lng'] = df.LONGITUD.map(dms)
num = lambda c: pd.to_numeric(df[c], errors='coerce')  # '*' = confidencial, 'N/D' = no disponible
df['poblacion'] = num('POBTOT')
for c, out in [('P_3A5','p3a5'),('P_6A11','p6a11'),('P_12A14','p12a14'),('P_15A17','p15a17')]: df[out] = num(c)
df['edades_reservadas'] = df[['p3a5','p6a11','p12a14','p15a17']].isna().any(axis=1)
sin = df.lat.isna()
print('filas:', len(df), '| sin coordenadas:', sin.sum(), '| población sin coordenadas:', int(df.loc[sin,'poblacion'].sum()), '| total:', int(df.poblacion.sum()))
print('localidades con edades reservadas:', df.edades_reservadas.sum(), '| su población:', int(df.loc[df.edades_reservadas,'poblacion'].sum()))
SALIDA.parent.mkdir(parents=True, exist_ok=True)
out = df[~sin].rename(columns={'ENTIDAD':'cve_ent','NOM_ENT':'nom_ent','MUN':'cve_mun','NOM_MUN':'nom_mun','LOC':'clave','NOM_LOC':'nombre'})
out['p3a14'] = out[['p3a5','p6a11','p12a14']].sum(axis=1, min_count=3)
out[['cve_ent','nom_ent','cve_mun','nom_mun','clave','nombre','lat','lng','poblacion','p3a5','p6a11','p12a14','p15a17','p3a14','edades_reservadas']].to_csv(SALIDA, index=False)
print('salida:', len(out), 'localidades | población asignada:', int(out.poblacion.sum()), '| 3 a 14 con dato:', int(out.p3a14.sum()))
