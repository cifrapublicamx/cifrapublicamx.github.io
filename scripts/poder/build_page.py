"""Arma poder/index.html desde site_src/poder.html con los resultados de calcular.py y serie.py.

Uso: python scripts/poder/build_page.py --autor "Rodrigo Méndez" --correo cifrapublicamx@gmail.com --fecha "20 de noviembre de 2026"
"""
import argparse, json, os

ap = argparse.ArgumentParser()
ap.add_argument('--autor', default='Rodrigo Méndez')
ap.add_argument('--correo', default='cifrapublicamx@gmail.com')
ap.add_argument('--fecha', default='20 de noviembre de 2026')
ap.add_argument('--consulta', default='20 de noviembre de 2026')
ap.add_argument('--inpc_hoy', type=float, default=147.026, help='INPC del último mes publicado (base 2a qna jul 2018)')
ap.add_argument('--inpc_hoy_mes', default='octubre de 2026')
a = ap.parse_args()

R = json.load(open('data/processed/poder/resultados.json'))
S = [json.loads(l) for l in open('data/processed/poder/serie.jsonl')]
INPC = {1994: 14.433286645444, 1996: 26.686071714930, 1998: 36.731632103784, 2000: 46.719785188278,
        2002: 52.108560301264, 2004: 56.828041181560, 2005: 59.072255360862, 2006: 61.119608647242,
        2008: 67.127492266209, 2010: 73.131749500306, 2012: 79.090540296893, 2014: 85.219965142136,
        2016: 89.809333493599, 2018: 100.492, 2020: 107.867, 2022: 123.803, 2024: 136.013}
serie = [dict(a=s['anio'], h=round(s['ing_hora_med_real'], 2), p25=round(s['ing_hora_p25_real'], 2),
              p75=round(s['ing_hora_p75_real'], 2), t=round(s['tortilla_min'], 2), tp=round(s['tortilla_real'], 2),
              vp=round(100 * s['vive_papas'], 2), n=s['n_trab']) for s in S]
f = INPC[2024] / INPC[1994]
items = []
for k, it in R['items'].items():
    a94, a24 = R['1994'], R['2024']
    items.append(dict(k=k, nombre=it['nombre'], u=it['unidad'],
                      p94=a94[f'precio_{k}'][0], p24=a24[f'precio_{k}'][0],
                      m94=a94[f'min_{k}'], m24=a24[f'min_{k}'], n94=a94[f'n_{k}'], n24=a24[f'n_{k}']))
meta = dict(z90=1.6449, inpc94=INPC[1994], inpc24=INPC[2024], factor=f, inpc_hoy=a.inpc_hoy, inpc_hoy_mes=a.inpc_hoy_mes,
            r94=R['1994'], r24=R['2024'], items=items, serie=serie, reps=R['reps'])
html = open('site_src/poder.html', encoding='utf-8').read()
titulo = 'Un kilo de tortilla te cuesta 29 minutos de trabajo. A tus papás, a tu edad, les costaba 15'
for k, v in {'__TITULO__': titulo, '__AUTOR__': a.autor, '__EMAIL__': a.correo, '__FECHA__': a.fecha,
             '__CONSULTA__': a.consulta, '__META__': json.dumps(meta, ensure_ascii=False, separators=(',', ':'))}.items():
    html = html.replace(k, v)
os.makedirs('poder', exist_ok=True)
open('poder/index.html', 'w', encoding='utf-8').write(html)
print('poder/index.html', len(html), 'bytes')
