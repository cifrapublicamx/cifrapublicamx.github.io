"""Serie ENIGH 1994-2024 para personas de 25 a 35 años.
Por edición: ingreso laboral monetario por hora (mediana), precio implícito de la tortilla,
minutos de trabajo por kilo, % que vive como hijo(a) en casa de sus papás.
La selección de claves de ingreso laboral se valida contra el concentrado de cada edición.
"""
import glob, os, sys, json
import numpy as np, pandas as pd
from dbfread import DBF

R = os.environ.get('ENIGH_DIR', 'data/raw/enigh')  # una carpeta por edición: 1994/, 1996/, ..., 2024/
INPC_AGO = {1994: 14.433286645444, 1996: 26.686071714930, 1998: 36.731632103784, 2000: 46.719785188278,
            2002: 52.108560301264, 2004: 56.828041181560, 2005: 59.072255360862, 2006: 61.119608647242,
            2008: 67.127492266209, 2010: 73.131749500306, 2012: 79.090540296893, 2014: 85.219965142136,
            2016: 89.809333493599, 2018: 100.492, 2020: 107.867, 2022: 123.803, 2024: 136.013}


def rd(f, cols=None):
    """Lee DBF o CSV, columnas en minúsculas; cols = lista de columnas deseadas (minúsculas)."""
    if f.lower().endswith('.dbf'):
        d = DBF(f, encoding='latin-1', char_decode_errors='ignore')
        fn = {c.lower(): c for c in d.field_names}
        cc = [fn[c] for c in cols if c in fn] if cols else d.field_names
        return pd.DataFrame(([r[c] for c in cc] for r in d), columns=[c.lower() for c in cc])
    df = pd.read_csv(f, encoding='latin-1', dtype=str, low_memory=False,
                     usecols=(lambda c: c.replace('ï»¿', '').replace('﻿', '').lower() in cols) if cols else None)
    df.columns = [c.replace('ï»¿', '').replace('﻿', '').lower() for c in df.columns]
    return df


def find(y, *keys, excl=()):
    fs = glob.glob(f'{R}/{y}/**/*', recursive=True)
    for f in sorted(fs):
        b = os.path.basename(f).lower()
        if any(k in b for k in keys) and not any(e in b for e in excl) and (b.endswith('.dbf') or b.endswith('.csv')):
            return f
    raise FileNotFoundError((y, keys))


def num(s):
    return pd.to_numeric(pd.Series(s).astype(str).str.strip(), errors='coerce')


def wq(x, w, q=.5):
    x = np.asarray(x, float); w = np.asarray(w, float)
    m = ~(np.isnan(x) | np.isnan(w)); x, w = x[m], w[m]
    o = np.argsort(x); x, w = x[o], w[o]; c = np.cumsum(w)
    return x[np.searchsorted(c, q * c[-1])]


def edicion(y):
    old = y <= 2006
    K = ['folio'] if old else ['folioviv', 'foliohog']
    P = K + (['num_ren'] if old else ['numren'])
    # --- archivos
    fpob = find(y, 'pobla')
    fing = find(y, 'ingreso', excl=('gasto', 'jcf', 'nomon'))
    fcon = find(y, 'concen')
    # --- factor y objetivo de validación (ingreso laboral monetario del hogar, trimestral)
    con = rd(fcon)
    fcol = 'factor' if 'factor' in con else ('factor_hog' if 'factor_hog' in con else 'hog')
    if y == 1994:
        hog = rd(find(y, 'hogares'), ['folio', 'factor']); con = con.merge(hog, on='folio', how='left') if 'factor' not in con else con; fcol = 'factor'
    lab_cols = [c for c in ['trabajo', 'negocio', 'coopera', 'otros_trab'] if c in con]
    if y == 2024 or 'ingtrab' in con:
        con['obj'] = num(con['ingtrab']).values - num(con['remu_espec']).fillna(0).values
    else:
        con['obj'] = sum(num(con[c]).fillna(0).values for c in lab_cols)
    for k in K: con[k] = con[k].astype(str).str.strip()
    con['w'] = num(con[fcol]).values
    # --- ingresos por clave
    ing = rd(fing, P + ['clave', 'ing_tri'])
    for k in P: ing[k] = ing[k].astype(str).str.strip()
    ing['clave'] = ing.clave.astype(str).str.strip().str.upper()
    ing['ing_tri'] = num(ing.ing_tri).values
    ing = ing[ing.clave.str.startswith('P')]
    # selección de claves por regresión contra el concentrado
    piv = ing.groupby(K + ['clave']).ing_tri.sum().unstack(fill_value=0)
    piv = piv.join(con.set_index(K)['obj'], how='inner')
    X = piv.drop(columns='obj'); t = piv['obj'].fillna(0)
    # candidatas: claves bajo P100 con algún monto
    cand = [c for c in X.columns if X[c].abs().sum() > 0]
    b, *_ = np.linalg.lstsq(X[cand].values, t.values, rcond=None)
    coef = dict(zip(cand, b))
    sel = sorted([c for c, v in coef.items() if v > 0.5])
    fit = X[sel].sum(axis=1)
    match = np.mean(np.isclose(fit.values, t.values, rtol=0.01, atol=5))
    # --- personas
    pob = rd(fpob, P + ['parentesco', 'edad', 'tot_hrs', 'hrs_sem', 'hrs_sec', 'horastrab', 'horas_trab'])
    for k in P: pob[k] = pob[k].astype(str).str.strip()
    pob['edad'] = num(pob.edad).values
    par = pob.parentesco.astype(str).str.strip()
    if y == 1994:
        pob['hijo'] = par.eq('4'); pob['jefe_c'] = par.isin(['1', '2', '3'])
    elif y <= 2000:
        par = par.str.zfill(2); pob['hijo'] = par.isin(['04', '05']); pob['jefe_c'] = par.isin(['01', '02', '03'])
    else:
        pob['hijo'] = par.str[0].eq('3'); pob['jefe_c'] = par.str[0].isin(['1', '2'])
    # horas semanales
    if y >= 2008:
        tra = rd(find(y, 'trabajo'), P + ['htrab'])
        for k in P: tra[k] = tra[k].astype(str).str.strip()
        tra['htrab'] = num(tra.htrab).values
        h = tra.groupby(P, as_index=False).htrab.sum().rename(columns={'htrab': 'hrs'})
        pob = pob.merge(h, on=P, how='left')
    elif 'hrs_sem' in pob:
        suma = num(pob.hrs_sem).fillna(0).values + (num(pob.hrs_sec).fillna(0).values if 'hrs_sec' in pob else 0)
        tot = num(pob.tot_hrs).fillna(0).values if 'tot_hrs' in pob else 0
        pob['hrs'] = np.maximum(suma, tot)
    elif 'horastrab' in pob:
        pob['hrs'] = num(pob.horastrab).values
    elif 'horas_trab' in pob:
        pob['hrs'] = num(pob.horas_trab).values
    else:
        pob['hrs'] = num(pob.hrs_sem).fillna(0).values + num(pob.hrs_sec).fillna(0).values
    lab = ing[ing.clave.isin(sel)].groupby(P, as_index=False).ing_tri.sum()
    pob = pob.merge(lab, on=P, how='left').merge(con[K + ['w']], on=K, how='left')
    pob['ing_tri'] = pob.ing_tri.fillna(0)
    j = pob[pob.edad.between(25, 35)]
    vive_papas = j[j.hijo].w.sum() / j.w.sum()
    jefe_c = j[j.jefe_c].w.sum() / j.w.sum()
    g = j[(j.ing_tri > 0) & (j.hrs.between(1, 98))].copy()
    g['mes'] = g.ing_tri / 3
    g['hora'] = g.mes / (g.hrs * 52 / 12)
    # --- tortilla
    if y == 2024:
        fg = find(y, 'gastoshogar'); code = '011131'
    elif y in (2008, 2010):
        fg = find(y, 'g_diario'); code = 'A004'
    elif y >= 2012:
        fg = find(y, 'gastohogar', 'gastoshogar'); code = 'A004'
    elif y == 1994:
        fg = find(y, 'gastos94'); code = 'A004'
    else:
        fg = find(y, 'gastos'); code = 'A004'
    ga = rd(fg, K + ['clave', 'cantidad', 'gasto'])
    for k in K: ga[k] = ga[k].astype(str).str.strip()
    ga = ga[ga.clave.astype(str).str.strip() == code]
    ga['cantidad'] = num(ga.cantidad).values; ga['gasto'] = num(ga.gasto).values
    ga = ga[(ga.cantidad > 0) & (ga.gasto > 0)].merge(con[K + ['w']], on=K)
    pt = wq(ga.gasto / ga.cantidad, ga.w)
    hmed = wq(g.hora, g.w)
    f = INPC_AGO[2024] / INPC_AGO[y]
    return dict(anio=y, claves=','.join(sel), coincide_concentrado=round(float(match), 3),
                n_trab=int(len(g)), pob_25_35=float(j.w.sum()),
                ing_mes_med_nom=float(wq(g.mes, g.w)), ing_hora_med_nom=float(hmed),
                ing_hora_p25_real=float(wq(g.hora, g.w, .25) * f), ing_hora_med_real=float(hmed * f),
                ing_hora_p75_real=float(wq(g.hora, g.w, .75) * f),
                horas_med=float(wq(g.hrs, g.w)), tortilla_precio=float(pt), tortilla_real=float(pt * f),
                tortilla_min=float(60 * pt / hmed), n_tortilla=int(len(ga)),
                vive_papas=float(vive_papas), jefe_conyuge=float(jefe_c))


if __name__ == '__main__':
    ys = [int(a) for a in sys.argv[1:]] or sorted(INPC_AGO)
    out = os.environ.get('SERIE_OUT', 'data/processed/poder/serie.jsonl')
    for y in ys:
        try:
            r = edicion(y)
        except Exception as e:
            print(y, 'ERROR', repr(e)); continue
        print(json.dumps(r, ensure_ascii=False))
        with open(out, 'a') as fh: fh.write(json.dumps(r, ensure_ascii=False) + '\n')
