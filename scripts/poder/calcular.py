"""Análisis 007: poder adquisitivo de personas de 25 a 35 años, ENIGH 1994 contra ENIGH 2024.

Calcula, con márgenes de error por bootstrap de unidades primarias de muestreo dentro de estratos:
- ingreso laboral monetario por hora (mediana) de quienes trabajan y tienen ingreso;
- precio implícito (gasto / cantidad) de 12 alimentos y su costo en minutos de trabajo;
- personas de 25 a 35 que viven como hijas o hijos en el hogar de sus papás;
- tenencia de la vivienda y renta de los hogares con jefa o jefe de 25 a 35.

Uso: python scripts/poder/calcular.py --e94 RUTA_ENIGH_1994 --e24 RUTA_ENIGH_2024 [--reps 300]
"""
import argparse, json, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
from serie import rd, num

INPC_AGO = {1994: 14.433286645444, 2024: 136.013}
ITEMS = {  # clave: (nombre, clave 1994, claves 2024, unidad)
    'tortilla': ('Tortilla de maíz', 'A004', ['011131'], 'kg'),
    'huevo': ('Huevo', 'A078', ['011481'], 'kg'),
    'frijol': ('Frijol', 'A116', ['011761'], 'kg'),
    'arroz': ('Arroz', 'A017', ['011111'], 'kg'),
    'leche': ('Leche', 'A060', ['011411'], 'l'),
    'aceite': ('Aceite vegetal', 'A080', ['011512'], 'l'),
    'azucar': ('Azúcar', 'A146', ['011810'], 'kg'),
    'jitomate': ('Jitomate', 'A088', ['011727'], 'kg'),
    'papa': ('Papa', 'A085', ['011751'], 'kg'),
    'pollo': ('Pollo', 'A033', ['01122F'], 'kg'),
    'bistec': ('Bistec de res', 'A022', ['011221'], 'kg'),
    'refresco': ('Refresco', 'A188', ['012601', '012602'], 'l'),
}
LAB94 = [f'P{i:03d}' for i in range(1, 16)]  # remuneraciones, negocios y cooperativas (Ingreso_Gasto_enigh94)
LAB24 = [f'P{i:03d}' for i in list(range(1, 10)) + [11, 13, 14, 15, 16, 18, 20, 21, 22, 35, 36] + list(range(67, 82))]


def wmed_rep(x, W, q=.5):
    """Cuantil ponderado para cada columna de pesos W (n x R)."""
    o = np.argsort(x); x = x[o]; W = W[o]
    c = np.cumsum(W, axis=0); t = q * c[-1]
    idx = (c < t).sum(axis=0)
    return x[np.minimum(idx, len(x) - 1)]


def multiplicadores(upm_est, R, seed):
    """Bootstrap de UPM dentro de estratos (Rao-Wu, m_h = n_h - 1). Devuelve dict upm -> vector de R factores."""
    rng = np.random.default_rng(seed)
    out = {}
    for est, g in upm_est.groupby('est'):
        u = g.upm.unique(); n = len(u)
        if n == 1:
            for x in u: out[x] = np.ones(R)
            continue
        m = n - 1
        draws = rng.integers(0, n, size=(R, m))
        cnt = np.zeros((R, n))
        for r in range(R): cnt[r] = np.bincount(draws[r], minlength=n)
        f = cnt * n / m
        for j, x in enumerate(u): out[x] = f[:, j]
    return out


def cargar94(d):
    hog = rd(f'{d}/hogares.dbf', ['folio', 'factor', 'tenencia', 'num_cua'])
    con = rd(f'{d}/concen.dbf', ['folio', 'est_dis', 'upm'])
    pob = rd(f'{d}/POBLA94.dbf', ['folio', 'num_ren', 'parentesco', 'edad', 'hrs_sem', 'hrs_sec', 'tot_hrs'])
    ing = rd(f'{d}/ingresos.dbf', ['folio', 'num_ren', 'clave', 'ing_tri'])
    gas = rd(f'{d}/gastos94.dbf', ['folio', 'clave', 'cantidad', 'gasto'])
    for t in (hog, con, pob, ing, gas):
        for k in t.columns:
            if k in ('folio', 'num_ren', 'clave', 'parentesco', 'tenencia', 'est_dis', 'upm'): t[k] = t[k].astype(str).str.strip()
    H = hog.merge(con, on='folio')
    H = pd.DataFrame({'h': H.folio, 'w': num(H.factor).values, 'est': H.est_dis, 'upm': H.upm,
                      'ten': H.tenencia.map({'1': 'propia', '2': 'propia', '3': 'propia', '4': 'pagando', '5': 'renta'}).fillna('otra').values,
                      'cuartos': num(H.num_cua).values})
    lab = ing[ing.clave.isin(LAB94)].assign(v=lambda x: num(x.ing_tri).values).groupby(['folio', 'num_ren'], as_index=False).v.sum()
    P = pob.merge(lab, on=['folio', 'num_ren'], how='left')
    hrs = np.maximum(num(P.hrs_sem).fillna(0).values + num(P.hrs_sec).fillna(0).values, num(P.tot_hrs).fillna(0).values)
    P = pd.DataFrame({'h': P.folio, 'edad': num(P.edad).values, 'par': P.parentesco.map({'1': 'jefe', '2': 'jefe', '3': 'conyuge', '4': 'hijo'}).fillna('otro').values,
                      'hrs': hrs, 'ing': P.v.fillna(0).values / 3})
    G = pd.DataFrame({'h': gas.folio, 'clave': gas.clave, 'q': num(gas.cantidad).values, 'g': num(gas.gasto).values})
    renta = G[G.clave == 'G005'].groupby('h').g.sum()
    return H, P, G, renta


def cargar24(d):
    con = rd(f'{d}/concentradohogar/concentradohogar.csv', ['folioviv', 'foliohog', 'factor', 'est_dis', 'upm'])
    viv = rd(f'{d}/viviendas/viviendas.csv', ['folioviv', 'tenencia', 'renta', 'num_cuarto'])
    pob = rd(f'{d}/poblacion/poblacion.csv', ['folioviv', 'foliohog', 'numren', 'parentesco', 'edad'])
    ing = rd(f'{d}/ingresos/ingresos.csv', ['folioviv', 'foliohog', 'numren', 'clave', 'ing_tri'])
    tra = rd(f'{d}/trabajos/trabajos.csv', ['folioviv', 'foliohog', 'numren', 'htrab'])
    gas = rd(f'{d}/gastoshogar/gastoshogar.csv', ['folioviv', 'foliohog', 'clave', 'cantidad', 'gasto'])
    key = lambda t: t.folioviv.str.strip() + '-' + t.foliohog.str.strip()
    H = con.merge(viv, on='folioviv')
    # tenencia y renta son de la vivienda; se asignan a cada hogar que la habita (como en 1994)
    H = pd.DataFrame({'h': key(H), 'w': num(H.factor).values, 'est': H.est_dis.str.strip(), 'upm': H.upm.str.strip(),
                      'ten': H.tenencia.astype(str).str.strip().map({'4': 'propia', '3': 'pagando', '1': 'renta'}).fillna('otra').values,
                      'cuartos': num(H.num_cuarto).values, 'renta_v': num(H.renta).values})
    lab = ing[ing.clave.str.strip().isin(LAB24)].assign(v=lambda x: num(x.ing_tri).values)
    lab['p'] = key(lab) + '-' + lab.numren.str.strip(); lab = lab.groupby('p').v.sum()
    tra['p'] = key(tra) + '-' + tra.numren.str.strip(); hr = num(tra.htrab).groupby(tra.p.values).sum()
    pob['p'] = key(pob) + '-' + pob.numren.str.strip()
    par = pob.parentesco.astype(str).str.strip().str[0].map({'1': 'jefe', '2': 'conyuge', '3': 'hijo'}).fillna('otro')
    P = pd.DataFrame({'h': key(pob), 'edad': num(pob.edad).values, 'par': par.values,
                      'hrs': pob.p.map(hr).fillna(0).values, 'ing': pob.p.map(lab).fillna(0).values / 3})
    G = pd.DataFrame({'h': key(gas), 'clave': gas.clave.str.strip(), 'q': num(gas.cantidad).values, 'g': num(gas.gasto).values})
    renta = H.set_index('h').renta_v.dropna()
    renta = renta[renta > 0]
    return H, P, G, renta


def estimar(anio, H, P, G, renta, R, seed):
    hw = H.set_index('h')
    mult = multiplicadores(H[['est', 'upm']].drop_duplicates(), R, seed)
    def pesos(hs):
        upm = hw.upm.reindex(hs).values; w = hw.w.reindex(hs).values
        M = np.vstack([mult[u] for u in upm])
        return np.column_stack([w, w[:, None] * M])  # columna 0 = estimación puntual
    res = {'anio': anio}
    # personas de 25 a 35
    J = P[P.edad.between(25, 35)]
    WJ = pesos(J.h.values)
    for k in ('hijo', 'jefe', 'conyuge'):
        res[f'pct_{k}'] = ((J.par.values == k)[:, None] * WJ).sum(0) / WJ.sum(0)
    res['pob_25_35'] = WJ[:, 0].sum()
    T = J[(J.ing > 0) & (J.hrs.between(1, 98))]
    WT = WJ[(J.ing.values > 0) & (J.hrs.between(1, 98).values)]
    hora = (T.ing / (T.hrs * 52 / 12)).values
    res['hora_med'] = wmed_rep(hora, WT); res['hora_p25'] = wmed_rep(hora, WT, .25); res['hora_p75'] = wmed_rep(hora, WT, .75)
    res['mes_med'] = wmed_rep(T.ing.values, WT); res['horas_med'] = wmed_rep(T.hrs.values.astype(float), WT)
    res['n_trab'] = len(T)
    # alimentos
    for k, (nom, c94, c24, u) in ITEMS.items():
        cl = [c94] if anio == 1994 else c24
        g = G[G.clave.isin(cl) & (G.q > 0) & (G.g > 0)].copy()
        g['pu'] = (g.g / g.q).round(4); g['upm'] = hw.upm.reindex(g.h).values; g['w'] = hw.w.reindex(g.h).values
        a = g.groupby(['upm', 'pu'], as_index=False).w.sum()  # los multiplicadores solo dependen de la UPM
        Wg = np.column_stack([a.w.values, a.w.values[:, None] * np.vstack([mult[u] for u in a.upm])])
        pr = wmed_rep(a.pu.values, Wg)
        res[f'precio_{k}'] = pr; res[f'min_{k}'] = 60 * pr / res['hora_med']; res[f'n_{k}'] = len(g)
    # hogares con jefa o jefe de 25 a 35
    jef = P[(P.par == 'jefe') & P.edad.between(25, 35)].drop_duplicates('h').h
    Hj = H[H.h.isin(jef)]
    WH = pesos(Hj.h.values)
    for t in ('propia', 'pagando', 'renta', 'otra'):
        res[f'ten_{t}'] = ((Hj.ten.values == t)[:, None] * WH).sum(0) / WH.sum(0)
    rr = Hj[(Hj.ten == 'renta') & Hj.h.isin(renta.index)]
    WR = pesos(rr.h.values); rv = renta.reindex(rr.h).values
    res['renta_med'] = wmed_rep(rv, WR); res['renta_horas'] = res['renta_med'] / res['hora_med']
    res['renta_cuartos_med'] = wmed_rep(rr.cuartos.values.astype(float), WR); res['n_renta'] = len(rr)
    res['hogares_jefe_25_35'] = WH[:, 0].sum()
    # resumen: punto y error estándar
    out = {}
    for k, v in res.items():
        if isinstance(v, np.ndarray):
            out[k] = [float(v[0]), float(np.std(v[1:], ddof=1))]
        else:
            out[k] = v if isinstance(v, (int, str)) else float(v)
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    base = os.environ.get('ENIGH_DIR', 'data/raw/enigh')
    ap.add_argument('--e94', default=f'{base}/1994'); ap.add_argument('--e24', default=f'{base}/2024')
    ap.add_argument('--reps', type=int, default=300); ap.add_argument('--out', default='data/processed/poder/resultados.json')
    a = ap.parse_args()
    r94 = estimar(1994, *cargar94(a.e94), a.reps, 94)
    print('1994 listo', file=sys.stderr)
    r24 = estimar(2024, *cargar24(a.e24), a.reps, 24)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump({'1994': r94, '2024': r24, 'inpc_ago': INPC_AGO,
               'items': {k: {'nombre': v[0], 'unidad': v[3], 'clave94': v[1], 'claves24': v[2]} for k, v in ITEMS.items()},
               'reps': a.reps}, open(a.out, 'w'), ensure_ascii=False, indent=1)
    for k in ['hora_med', 'mes_med', 'pct_hijo', 'ten_propia', 'ten_pagando', 'ten_renta', 'renta_horas', 'min_tortilla']:
        print(k, r94[k], r24[k])
