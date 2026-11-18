# Análisis 006 | Participación por sección electoral

¿Se puede adivinar con el censo en qué secciones votó menos de la mitad de la lista nominal? Página: `/participacion/`.

## Datos de origen (van en `data/raw/participacion/`, no se suben al repo)

| Archivo | De dónde sale |
| --- | --- |
| `PRES_2024.csv` | INE, Cómputos Distritales 2024, base de datos de Presidencia (computos2024.ine.mx → Base de datos). Copia idéntica en el repositorio [emagar/elecRetrns](https://github.com/emagar/elecRetrns), `datosBrutos/result-casillas-fed/fed2024all/pres/20240608_2030_COMPUTOS_PRES.zip`. |
| `Diputados2021.csv` | INE, Cómputos Distritales 2021, Diputaciones. En elecRetrns: `datosBrutos/result-casillas-fed/fed2021all/`. |
| `Presidente2018.csv` | INE, Cómputos Distritales 2018, Presidencia. En elecRetrns: `datosBrutos/result-casillas-fed/fed2018all/`. |
| `casillas2024lonlat.csv` | Coordenadas de las casillas de 2024, en elecRetrns: `datosBrutos/result-casillas-fed/fed2024all/`. |
| `INE_SECCION_2020.csv` | INEGI, Estadísticas Censales a Escalas Geoelectorales 2020: `https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/geoelectorales/eceg_2020_csv.zip` → `conjunto_de_datos/`. |

## Cómo reproducirlo

```bash
pip install pandas numpy scikit-learn h3
P=data/processed/participacion; R=data/raw/participacion
python scripts/participacion/extraer.py $R $P/participacion_seccion.csv.gz          # votos y lista por sección
python scripts/participacion/base.py $P/participacion_seccion.csv.gz $R/INE_SECCION_2020.csv \
       $R/casillas2024lonlat.csv $P/base_seccion.csv.gz                              # une con el censo
python scripts/participacion/modelo.py $P/base_seccion.csv.gz $P                    # ~4 min
python scripts/participacion/svm_tamano.py $P/base_seccion.csv.gz $P/svm_tamano.json # ~6 min, opcional
python scripts/participacion/analisis.py $P/base_seccion.csv.gz $P                  # ~4 min
python scripts/participacion/build_page.py --fecha "20 de noviembre de 2026"
```

`build_page.py` revisa que los datos sigan sosteniendo lo que dice el texto fijo (quién gana, el orden de importancia, León arriba e Irapuato abajo de lo predicho); si algo cambia, se detiene antes de escribir la página.

## Qué hace cada paso

- `extraer.py`: suma votos y lista nominal por sección en casillas básicas, contiguas y extraordinarias. Deja fuera especiales, voto anticipado, extranjero, prisión preventiva y actas sin datos. Guarda también los totales oficiales del INE (`oficiales_ine.json`).
- `base.py`: une con el censo por estado y número de sección (cartografía de enero de 2021) y arma los 29 datos de cada sección.
- `modelo.py`: regla simple, regresión logística, SVM (kernel radial, muestra de 16 mil secciones por bloque) y gradient boosting. Validación por municipio (5 bloques de municipios), Guanajuato a ciegas (entrena con 31 estados, sin la variable del estado) y con historia (participación de 2018 y 2021). También un gradient boosting de regresión para el porcentaje predicho por sección.
- `analisis.py`: escalera de información (solo estado, solo censo), importancia por permutación por grupos, curvas de dependencia parcial en Guanajuato, el modelo aditivo del simulador, hexágonos H3 de León y el resumen por municipio de Guanajuato.
- `build_page.py`: arma `participacion/index.html` desde `site_src/participacion.html`, con Leaflet adentro.

## Notas de método

- Objetivo: la sección votó menos de la mitad de su lista nominal en la elección presidencial de 2024 (14.7% de 67,473 secciones).
- Ninguna predicción que se publica sale de un modelo que haya visto el municipio de la sección.
- Las 2,766 secciones de 2024 creadas o redibujadas después de la cartografía de 2021 no tienen censo y quedan fuera.
- No se usa ningún resultado por partido.
