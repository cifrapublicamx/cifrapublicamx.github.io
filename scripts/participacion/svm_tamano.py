"""Análisis 006 | ¿El SVM mejora con más datos?

Misma validación por municipio que modelo.py (censo + estado), con muestras de entrenamiento
de 16 mil y 32 mil secciones. Tarda unos 6 minutos.

Uso: python svm_tamano.py <base_seccion.csv.gz> <salida.json>
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
from sklearn.model_selection import GroupKFold

sys.path.insert(0, str(Path(__file__).parent))
import modelo  # noqa: E402
from modelo import CENSO, ajusta_predice, carga, metricas, modelos  # noqa: E402


def main():
    d = carga(sys.argv[1])
    cols = CENSO + ["entidad"]
    out = {}
    for n in (16000, 32000):
        modelo.SVM_MUESTRA = n
        s = np.zeros(len(d))
        t0 = time.time()
        for tr, te in GroupKFold(n_splits=5).split(d, d.y, d.mun_id):
            s[te] = ajusta_predice("svm", modelos(CENSO, True)["svm"], d.loc[tr, cols], d.loc[tr, "y"],
                                   d.loc[te, cols])
        out[n] = metricas(d.y, s) | {"segundos": round(time.time() - t0)}
        print(n, json.dumps(out[n]), flush=True)
    Path(sys.argv[2]).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
