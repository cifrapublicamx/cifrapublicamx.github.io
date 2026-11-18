"""Análisis 006 | Cifras, curvas, simulador y mapa para la página.

Lee la base por sección y las predicciones fuera de muestra de modelo.py y escribe
out/pagina_datos.json con todo lo que dibuja la página.

Uso: python analisis.py <base_seccion.csv> <carpeta_out>
"""
import json
import sys
from pathlib import Path

import h3
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

sys.path.insert(0, str(Path(__file__).parent))
from modelo import CENSO, HISTORIA, SEMILLA, carga, metricas  # noqa: E402

GTO = 11
LEON = 20
GRUPOS = {
    "El estado": ["entidad"],
    "Escolaridad": ["escolaridad", "posbasica", "analfabeta"],
    "Edad": ["jovenes_18_24", "mayores_60"],
    "Trabajo y seguridad social": ["pea", "pea_mujeres", "sin_afiliacion", "imss", "issste"],
    "Bienes y servicios de la casa": ["auto", "internet", "computadora", "piso_tierra", "sin_drenaje",
                                      "streaming", "ocupantes_vivienda"],
    "Arraigo y migración": ["nacidos_otro_estado", "llegaron_desde_2015", "casas_deshabitadas",
                            "casas_temporales", "log_lista_por_adulto"],
    "Hogar": ["casados", "jefa_mujer"],
    "Lengua indígena y afromexicanos": ["lengua_indigena", "afro"],
    "Tamaño y tipo de sección": ["log_adultos", "rural", "mixta"],
}
SIM = ["escolaridad", "mayores_60", "jovenes_18_24", "issste", "sin_afiliacion", "casas_deshabitadas"]
CURVAS = SIM + ["computadora", "log_lista_por_adulto"]


def cat(X, ref=None):
    if ref is None:
        return X.assign(entidad=X.entidad.astype("category"))
    return X.assign(entidad=pd.Categorical(X.entidad, categories=ref.entidad.cat.categories))


def clf(**kw):
    return HistGradientBoostingClassifier(max_iter=400, learning_rate=0.06, max_leaf_nodes=31,
                                          min_samples_leaf=40, l2_regularization=1.0,
                                          random_state=SEMILLA, **kw)


def reg(**kw):
    return HistGradientBoostingRegressor(max_iter=500, learning_rate=0.05, max_leaf_nodes=31,
                                         min_samples_leaf=40, l2_regularization=1.0,
                                         random_state=SEMILLA, **kw)


def escalera(d, oof):
    """Qué tanto ayuda cada capa de información (validación por municipio)."""
    gkf = list(GroupKFold(n_splits=5).split(d, d.y, d.mun_id))
    solo_estado = np.zeros(len(d))
    solo_censo = np.zeros(len(d))
    solo_historia = np.zeros(len(d))
    for tr, te in gkf:
        tasas = d.loc[tr].groupby("entidad").y.mean()
        solo_estado[te] = d.loc[te, "entidad"].map(tasas).fillna(d.loc[tr, "y"].mean()).values
        m = clf().fit(d.loc[tr, CENSO], d.loc[tr, "y"])
        solo_censo[te] = m.predict_proba(d.loc[te, CENSO])[:, 1]
        m = clf().fit(d.loc[tr, HISTORIA], d.loc[tr, "y"])
        solo_historia[te] = m.predict_proba(d.loc[te, HISTORIA])[:, 1]
    return {
        "solo_estado": metricas(d.y, solo_estado),
        "solo_censo": metricas(d.y, solo_censo),
        "solo_historia": metricas(d.y, solo_historia),
    }


def importancia(d):
    """Permutación por grupos de variables, en municipios que el modelo no vio."""
    cols = CENSO + ["entidad"]
    rng = np.random.default_rng(SEMILLA)
    caidas = {g: [] for g in GRUPOS}
    for tr, te in GroupKFold(n_splits=5).split(d, d.y, d.mun_id):
        Xtr = cat(d.loc[tr, cols])
        m = clf(categorical_features=["entidad"]).fit(Xtr, d.loc[tr, "y"])
        Xte = cat(d.loc[te, cols], Xtr)
        yte = d.loc[te, "y"].values
        base = roc_auc_score(yte, m.predict_proba(Xte)[:, 1])
        for g, vs in GRUPOS.items():
            for _ in range(3):
                Xp = Xte.copy()
                perm = rng.permutation(len(Xp))
                for v in vs:
                    Xp[v] = Xp[v].values[perm]
                caidas[g].append(base - roc_auc_score(yte, m.predict_proba(Xp)[:, 1]))
    return {g: float(np.mean(v)) for g, v in caidas.items()}


def curvas(d, modelo_pct, cols):
    """Dependencia parcial en Guanajuato: participación promedio predicha al mover una variable."""
    fondo = cat(d.loc[d.entidad == GTO, cols], cat(d[cols]))
    out = {}
    for v in CURVAS:
        lo, hi = d[v].quantile([0.02, 0.98])
        grid = np.linspace(lo, hi, 25)
        ys = []
        for g in grid:
            X = fondo.copy()
            X[v] = g
            ys.append(float(modelo_pct.predict(X).mean()))
        dist = d.loc[d.entidad == GTO, v].quantile([0.1, 0.5, 0.9]).tolist()
        out[v] = {"x": grid.tolist(), "y": ys, "gto_p10_p50_p90": dist}
    return out


def simulador(d):
    """Modelo aditivo de 6 datos + estado (cada variable por su lado): exacto en el navegador."""
    cols = SIM + ["entidad"]
    cst = [[i] for i in range(len(cols))]
    pred = np.zeros(len(d))
    for tr, te in GroupKFold(n_splits=5).split(d, d.y, d.mun_id):
        Xtr = cat(d.loc[tr, cols])
        m = reg(categorical_features=["entidad"], interaction_cst=cst).fit(Xtr, d.loc[tr, "part_2024"])
        pred[te] = m.predict(cat(d.loc[te, cols], Xtr))
    err = d.part_2024 - pred
    Xall = cat(d[cols])
    m = reg(categorical_features=["entidad"], interaction_cst=cst).fit(Xall, d.part_2024)
    # Perfil típico de Guanajuato (mediana) y curvas de cada variable
    perfil = d.loc[d.entidad == GTO, SIM].median()
    X0 = Xall.iloc[[0]].copy()
    for v in SIM:
        X0[v] = perfil[v]
    X0["entidad"] = pd.Categorical([GTO], categories=Xall.entidad.cat.categories)
    base = float(m.predict(X0)[0])
    formas = {}
    for v in SIM:
        lo, hi = d[v].quantile([0.01, 0.99])
        grid = np.linspace(lo, hi, 61)
        X = pd.concat([X0] * len(grid), ignore_index=True)
        X[v] = grid
        X["entidad"] = pd.Categorical([GTO] * len(grid), categories=Xall.entidad.cat.categories)
        ys = m.predict(X)
        formas[v] = {"x": grid.tolist(), "delta": (ys - base).tolist()}
    # comprobación: suma de formas = predicción del modelo en secciones reales de Gto
    g = d[d.entidad == GTO].sample(300, random_state=SEMILLA)
    aprox = np.full(len(g), base)
    for v in SIM:
        aprox += np.interp(g[v], formas[v]["x"], formas[v]["delta"])
    real = m.predict(cat(g[cols], Xall))
    gto = d[d.entidad == GTO]
    perfiles = {
        "gto": perfil.to_dict(),
        "leon": gto.loc[gto.municipio == LEON, SIM].median().to_dict(),
        "gto_rural": gto.loc[gto.tipo == 4, SIM].median().to_dict(),
        "leon_alta_escolaridad": gto.loc[(gto.municipio == LEON) & (gto.escolaridad >= gto.loc[
            gto.municipio == LEON, "escolaridad"].quantile(0.9)), SIM].median().to_dict(),
    }
    return {
        "variables": SIM, "perfil_gto": perfil.to_dict(), "perfiles": perfiles,
        "base_gto": base, "formas": formas,
        "mae_puntos": float(100 * err.abs().mean()),
        "mae_puntos_gto": float(100 * err[d.entidad == GTO].abs().mean()),
        "error_aproximacion_puntos": float(100 * np.abs(aprox - real).max()),
    }


def hexagonos(p, res=8):
    p = p[p.lon.notna()].copy()
    p["hex"] = [h3.latlng_to_cell(la, lo, res) for la, lo in zip(p.lat, p.lon)]
    p["pred_votos"] = p.pred_part * p.lista_2024
    g = p.groupby("hex").agg(secciones=("seccion", "size"), lista=("lista_2024", "sum"),
                             votos=("votos_2024", "sum"), pred_votos=("pred_votos", "sum"),
                             bajo=("y", "sum"), lista_2021=("lista_2021", "sum"),
                             votos_2021=("votos_2021", "sum"),
                             secs=("seccion", lambda s: sorted(s.tolist()))).reset_index()
    out = []
    for r in g.itertuples():
        out.append({
            "h": r.hex, "s": int(r.secciones), "l": int(r.lista),
            "r": round(r.votos / r.lista, 4), "p": round(r.pred_votos / r.lista, 4),
            "r21": round(r.votos_2021 / r.lista_2021, 4) if r.lista_2021 > 0 else None,
            "b": int(r.bajo), "secs": [int(x) for x in r.secs],
            "poly": [[round(la, 5), round(lo, 5)] for la, lo in h3.cell_to_boundary(r.hex)],
        })
    return out


def main():
    d = carga(sys.argv[1])
    sal = Path(sys.argv[2])
    res = json.loads((sal / "resultados.json").read_text())
    pred = pd.read_csv(sal / "predicciones_seccion.csv.gz")

    datos = {"resultados": res}
    print("escalera…", flush=True)
    datos["escalera"] = escalera(d, None)
    print("importancia…", flush=True)
    datos["importancia"] = importancia(d)
    print("curvas…", flush=True)
    cols = CENSO + ["entidad"]
    m_pct = reg(categorical_features=["entidad"]).fit(cat(d[cols]), d.part_2024)
    datos["curvas"] = curvas(d, m_pct, cols)
    print("simulador…", flush=True)
    datos["simulador"] = simulador(d)

    # Cifras de contexto (solo casillas básicas, contiguas y extraordinarias)
    def resumen(x):
        return {"secciones": int(len(x)), "lista": int(x.lista_2024.sum()),
                "part": float(x.votos_2024.sum() / x.lista_2024.sum()),
                "part_2021": float(x.votos_2021.sum() / x.lista_2021.sum()),
                "bajo": float(x.y.mean()), "bajo_n": int(x.y.sum())}
    p = pred.merge(d[["entidad", "seccion", "lista_2021", "votos_2021"] + SIM + ["posbasica", "computadora"]],
                   on=["entidad", "seccion"], how="left")
    datos["contexto"] = {
        "nacional": resumen(p), "guanajuato": resumen(p[p.entidad == GTO]),
        "leon": resumen(p[(p.entidad == GTO) & (p.municipio == LEON)]),
    }
    por_estado = p.groupby("entidad").apply(
        lambda x: pd.Series({"part": x.votos_2024.sum() / x.lista_2024.sum(), "bajo": x.y.mean()}),
        include_groups=False)
    datos["por_estado"] = por_estado.round(4).reset_index().to_dict(orient="records")

    # León: secciones y hexágonos; Guanajuato: municipios
    leon = p[(p.entidad == GTO) & (p.municipio == LEON)].copy()
    datos["leon_hex"] = hexagonos(leon)
    leon_tab = leon[["seccion", "lista_2024", "part_2024", "part_2021", "pred_part", "prob_boosting", "y"]
                    + SIM].copy()
    datos["leon_secciones"] = leon_tab.round(4).to_dict(orient="records")
    datos["leon_metricas"] = {
        "auc": float(roc_auc_score(leon.y, leon.prob_boosting)) if leon.y.nunique() > 1 else None,
        "mae_puntos": float(100 * (leon.part_2024 - leon.pred_part).abs().mean()),
        "sesgo_puntos": float(100 * (leon.part_2024 - leon.pred_part).mean()),
        "dentro_5": float(((leon.part_2024 - leon.pred_part).abs() < 0.05).mean()),
    }
    g = p[p.entidad == GTO].copy()
    g["pv"] = g.pred_part * g.lista_2024
    mun = g.groupby("municipio").agg(lista=("lista_2024", "sum"), votos=("votos_2024", "sum"),
                                     pv=("pv", "sum"), secciones=("seccion", "size"), bajo=("y", "mean"))
    mun["real"] = mun.votos / mun.lista
    mun["pred"] = mun.pv / mun.lista
    datos["gto_municipios"] = mun[["lista", "secciones", "real", "pred", "bajo"]].round(4).reset_index()\
        .to_dict(orient="records")
    datos["gto_metricas"] = {
        "auc": float(roc_auc_score(g.y, g.prob_boosting)),
        "mae_puntos": float(100 * (g.part_2024 - g.pred_part).abs().mean()),
    }
    # ¿Sirve para una intermedia? El modelo se entrenó con 2024; se compara contra 2021
    q = p[p.part_2021.notna()]
    datos["prueba_2021"] = {
        "bajo_2021": float((q.part_2021 < 0.5).mean()),
        "auc_2021": float(roc_auc_score(q.part_2021 < 0.5, -q.pred_part)),
    }
    (sal / "pagina_datos.json").write_text(json.dumps(datos, ensure_ascii=False))
    resumen_txt = {k: v for k, v in datos.items() if k not in ("leon_hex", "leon_secciones", "curvas",
                                                                "simulador", "por_estado", "gto_municipios")}
    print(json.dumps(resumen_txt, indent=1, ensure_ascii=False)[:6000])
    print("simulador:", {k: datos["simulador"][k] for k in ("mae_puntos", "mae_puntos_gto",
                                                            "error_aproximacion_puntos", "base_gto")})


if __name__ == "__main__":
    main()
