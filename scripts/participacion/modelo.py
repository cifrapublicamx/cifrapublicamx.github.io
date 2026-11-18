"""Análisis 006 | ¿Se puede adivinar con el censo dónde vota menos de la mitad?

Objetivo: sección donde votó menos de la mitad de la lista nominal (presidencia 2024).
Compara una regla simple, regresión logística, SVM (kernel RBF) y gradient boosting.

Validaciones (ninguna usa la sección que predice):
  A) por municipio: el modelo predice cada municipio sin haber visto ninguna sección suya
     (conoce el estado; 5 bloques de municipios).
  B) Guanajuato a ciegas: entrena con los otros 31 estados, sin saber el estado, y predice
     las secciones de Guanajuato.
  C) con historia: igual que A pero sumando la participación de 2018 y 2021.

Uso: python modelo.py <base_seccion.csv> <carpeta_salida>
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, QuantileTransformer
from sklearn.svm import SVC

SEMILLA = 2027
CENSO = [
    "jovenes_18_24", "mayores_60", "escolaridad", "posbasica", "analfabeta", "pea",
    "pea_mujeres", "sin_afiliacion", "imss", "issste", "casados", "ocupantes_vivienda",
    "jefa_mujer", "nacidos_otro_estado", "llegaron_desde_2015", "casas_deshabitadas",
    "casas_temporales", "lengua_indigena", "afro", "auto", "internet", "computadora",
    "piso_tierra", "sin_drenaje", "streaming", "log_lista_por_adulto", "log_adultos",
    "rural", "mixta",
]
HISTORIA = ["part_2018", "part_2021"]
UMBRAL = 0.5
SVM_MUESTRA = 16000


def carga(ruta):
    d = pd.read_csv(ruta)
    d = d[d.part_2024.between(0.01, 1) & (d.lista_2024 >= 100) & (d.pob18 >= 50)].copy()
    d["log_lista_por_adulto"] = np.log(d.lista_por_adulto.clip(0.3, 5))
    d["log_adultos"] = np.log(d.pob18)
    d["rural"] = (d.tipo == 4).astype(int)
    d["mixta"] = (d.tipo == 3).astype(int)
    d["mun_id"] = d.entidad * 1000 + d.municipio
    d["y"] = (d.part_2024 < UMBRAL).astype(int)
    for c in HISTORIA:
        d[c] = d[c].clip(0, 1)
    return d.reset_index(drop=True)


def prepro(num, con_estado):
    pasos = [("num", make_pipeline(SimpleImputer(strategy="median"),
                                   QuantileTransformer(output_distribution="normal",
                                                       n_quantiles=500, random_state=SEMILLA)), num)]
    if con_estado:
        pasos.append(("edo", OneHotEncoder(handle_unknown="ignore"), ["entidad"]))
    return ColumnTransformer(pasos)


def modelos(num, con_estado):
    return {
        "logistica": make_pipeline(prepro(num, con_estado),
                                   LogisticRegression(C=0.5, max_iter=2000, class_weight="balanced")),
        "svm": make_pipeline(prepro(num, con_estado),
                             SVC(C=1.0, gamma="scale", kernel="rbf", class_weight="balanced")),
        "boosting": HistGradientBoostingClassifier(
            max_iter=400, learning_rate=0.06, max_leaf_nodes=31, min_samples_leaf=40,
            l2_regularization=1.0, categorical_features=(["entidad"] if con_estado else None),
            random_state=SEMILLA),
    }


def ajusta_predice(nombre, modelo, Xtr, ytr, Xte):
    if nombre == "svm" and len(Xtr) > SVM_MUESTRA:
        rng = np.random.default_rng(SEMILLA)
        idx = rng.choice(len(Xtr), SVM_MUESTRA, replace=False)
        Xtr, ytr = Xtr.iloc[idx], ytr.iloc[idx]
    if nombre == "boosting" and "entidad" in Xtr:
        Xtr = Xtr.assign(entidad=Xtr.entidad.astype("category"))
        Xte = Xte.assign(entidad=pd.Categorical(Xte.entidad, categories=Xtr.entidad.cat.categories))
    modelo.fit(Xtr, ytr)
    if hasattr(modelo, "predict_proba"):
        return modelo.predict_proba(Xte)[:, 1]
    return modelo.decision_function(Xte)


def metricas(y, s):
    y, s = np.asarray(y), np.asarray(s)
    orden = np.argsort(-s)
    base = y.mean()
    k10 = max(1, int(round(0.10 * len(y))))
    kb = max(1, int(round(base * len(y))))
    return {
        "n": int(len(y)), "tasa_base": float(base),
        "auc": float(roc_auc_score(y, s)), "ap": float(average_precision_score(y, s)),
        "precision_top10": float(y[orden[:k10]].mean()),
        "lift_top10": float(y[orden[:k10]].mean() / base),
        "recall_k_base": float(y[orden[:kb]].sum() / y.sum()),
    }


def regla_simple(d, idx_tr, idx_te):
    """Mejor variable sola del censo (elegida en entrenamiento por AUC)."""
    mejor, mejor_auc, signo = None, 0, 1
    for c in CENSO:
        x = d.loc[idx_tr, c].fillna(d.loc[idx_tr, c].median())
        a = roc_auc_score(d.loc[idx_tr, "y"], x)
        if max(a, 1 - a) > mejor_auc:
            mejor, mejor_auc, signo = c, max(a, 1 - a), (1 if a >= 0.5 else -1)
    x = d.loc[idx_te, mejor].fillna(d.loc[idx_tr, mejor].median())
    return signo * x.values, mejor


def validacion_municipios(d, feats, con_estado, etiqueta, guarda_oof=False):
    gkf = GroupKFold(n_splits=5)
    cols = feats + (["entidad"] if con_estado else [])
    oof = {k: np.zeros(len(d)) for k in ("regla", "logistica", "svm", "boosting")}
    reglas = []
    for i, (tr, te) in enumerate(gkf.split(d, d.y, d.mun_id)):
        s, r = regla_simple(d, tr, te)
        oof["regla"][te] = s
        reglas.append(r)
        for nombre, m in modelos(feats, con_estado).items():
            t0 = time.time()
            oof[nombre][te] = ajusta_predice(nombre, m, d.loc[tr, cols], d.loc[tr, "y"], d.loc[te, cols])
            print(f"  [{etiqueta}] bloque {i + 1} {nombre}: {time.time() - t0:.0f}s", flush=True)
    res = {k: metricas(d.y, v) for k, v in oof.items()}
    res["regla"]["variable"] = max(set(reglas), key=reglas.count)
    return res, oof


def guanajuato_a_ciegas(d, feats):
    tr = d.index[d.entidad != 11]
    te = d.index[d.entidad == 11]
    out, scores = {}, {}
    s, r = regla_simple(d, tr, te)
    out["regla"] = metricas(d.loc[te, "y"], s) | {"variable": r}
    scores["regla"] = s
    for nombre, m in modelos(feats, False).items():
        s = ajusta_predice(nombre, m, d.loc[tr, feats], d.loc[tr, "y"], d.loc[te, feats])
        out[nombre] = metricas(d.loc[te, "y"], s)
        scores[nombre] = s
        print(f"  [gto] {nombre} listo", flush=True)
    return out, scores, te


def main():
    d = carga(sys.argv[1])
    sal = Path(sys.argv[2])
    sal.mkdir(parents=True, exist_ok=True)
    print(f"{len(d):,} secciones | votó menos de la mitad: {d.y.mean():.1%}")

    resultados = {"n": len(d), "tasa_base": float(d.y.mean())}
    resultados["A_municipios"], oof = validacion_municipios(d, CENSO, True, "A")
    resultados["C_con_historia"], oof_h = validacion_municipios(d, CENSO + HISTORIA, True, "C")
    resultados["B_guanajuato"], s_gto, idx_gto = guanajuato_a_ciegas(d, CENSO)

    # Regresión (porcentaje), boosting, validación por municipio, para mapas y simulador
    gkf = GroupKFold(n_splits=5)
    pred = np.zeros(len(d))
    cols = CENSO + ["entidad"]
    for tr, te in gkf.split(d, d.y, d.mun_id):
        reg = HistGradientBoostingRegressor(max_iter=500, learning_rate=0.05, max_leaf_nodes=31,
                                            min_samples_leaf=40, l2_regularization=1.0,
                                            categorical_features=["entidad"], random_state=SEMILLA)
        Xtr = d.loc[tr, cols].assign(entidad=d.loc[tr, "entidad"].astype("category"))
        Xte = d.loc[te, cols].assign(entidad=pd.Categorical(d.loc[te, "entidad"],
                                                            categories=Xtr.entidad.cat.categories))
        reg.fit(Xtr, d.loc[tr, "part_2024"])
        pred[te] = reg.predict(Xte)
    err = d.part_2024 - pred
    resultados["regresion"] = {
        "mae_puntos": float(100 * err.abs().mean()),
        "dentro_5_puntos": float((err.abs() < 0.05).mean()),
        "r2": float(1 - (err ** 2).sum() / ((d.part_2024 - d.part_2024.mean()) ** 2).sum()),
    }

    out = d[["entidad", "municipio", "seccion", "tipo", "lon", "lat", "lista_2024", "votos_2024",
             "part_2018", "part_2021", "part_2024", "y"]].copy()
    out["prob_boosting"] = oof["boosting"]
    out["prob_logistica"] = oof["logistica"]
    out["svm_score"] = oof["svm"]
    out["prob_con_historia"] = oof_h["boosting"]
    out["pred_part"] = pred
    out.to_csv(sal / "predicciones_seccion.csv.gz", index=False)
    g = d.loc[idx_gto, ["entidad", "municipio", "seccion", "y", "part_2024"]].copy()
    for k, v in s_gto.items():
        g[f"score_{k}"] = v
    g.to_csv(sal / "guanajuato_a_ciegas.csv", index=False)
    (sal / "resultados.json").write_text(json.dumps(resultados, indent=2, ensure_ascii=False))
    print(json.dumps(resultados, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
