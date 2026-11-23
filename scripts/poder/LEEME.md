# Análisis 007 | Poder adquisitivo de quienes tienen de 25 a 35 años, 1994 contra 2024 · `/poder/`

Cuántos minutos de trabajo le cuestan a la persona típica de 25 a 35 años la tortilla y otros 11 alimentos, cuánto gana por hora, si vive en casa de sus papás y si su hogar es dueño de su vivienda, en 1994 y en 2024, con los microdatos de la ENIGH del INEGI. La serie usa todas las ediciones de 1994 a 2024.

## Datos

Los microdatos no se suben al repo. Bájalos del INEGI (ENIGH → microdatos) y descomprímelos en `data/raw/enigh/<año>/`, una carpeta por edición:

- 1994 a 2014, versión tradicional: `hogares`, `poblacion`, `ingresos`, `gastos` (en 2008 y 2010, además `G_diario`), `concen` o `concentrado`, y desde 2008 `trabajos` y `viviendas`.
- 2016 a 2024, Nueva serie: `viviendas`, `hogares`, `poblacion`, `ingresos`, `trabajos`, `gastoshogar`, `concentradohogar`.

Desde un script, la lista de archivos de cada edición sale de
`https://www.inegi.org.mx/app/api/descarga/componente/descargamasiva/lista/archivoscompaginacion?tema=0&subtema=0&areaGeografica=0&proyecto=0&anio=0&tipodocto=4&agrupacion=VG9kYXM=&idBiinegi=<id>&desde=1&hasta=80&textoBuscar=&ordenar=orden&ingles=0&datosAbiertos=0&orden=`
(id 1707 para 1994, 1706 para 1996, … 1696 para 2014; 2781, 2922, 2993, 3229 y 3434 para 2016 a 2024) y cada archivo vive en `https://www.inegi.org.mx/contenidos<pathLogico><formato>`.

## Cómo reproducirlo

```bash
pip install pandas numpy dbfread
export ENIGH_DIR=data/raw/enigh
python scripts/poder/serie.py                 # serie 1994-2024 -> data/processed/poder/serie.jsonl
python scripts/poder/calcular.py --reps 200   # 1994 y 2024 con márgenes de error -> data/processed/poder/resultados.json
python scripts/poder/build_page.py --autor "Rodrigo Méndez" --correo cifrapublicamx@gmail.com --fecha "20 de noviembre de 2026"
```

`serie.py` agrega una línea por edición; borra `serie.jsonl` antes de correrlo de nuevo.

## Notas de método

- **Ingreso por hora:** ingreso monetario por trabajo del último trimestre entre 3, dividido entre horas semanales × 52/12. Solo personas de 25 a 35 años con ingreso mayor a cero y entre 1 y 98 horas. En cada edición las claves de ingreso se eligen por regresión contra el ingreso por trabajo del concentrado del INEGI; la suma por hogar coincide en más del 99% de los hogares en todas las ediciones (columna `coincide_concentrado`).
- **Horas:** 1994 a 2002, horas del empleo principal más el secundario; 2004 a 2006, `horastrab`/`horas_trab`; desde 2008, suma de `htrab` de la tabla de trabajos.
- **Precios:** mediana ponderada de gasto entre cantidad de cada compra de la libreta de gastos. Tortilla A004 en el catálogo tradicional y en la Nueva serie hasta 2022; 011131 en 2024. Las claves de los otros 11 alimentos están en `calcular.py`.
- **Minutos** = 60 × precio ÷ ingreso por hora mediano, del mismo año; no hace falta deflactar. Para pesos de 2024 se usa el INPC de agosto de cada año.
- **Márgenes de error:** bootstrap de UPM dentro de estratos (Rao-Wu), 200 réplicas, al 90%. Los precios redondos hacen que las medianas brinquen de escalón en escalón; el margen puede quedarse corto.
- **Corte de 2016:** la serie usa la versión tradicional hasta 2014 y la Nueva serie desde 2016, sin empalmar. La Nueva serie capta más ingreso.
- **Fuera:** bienes durables (la ENIGH no da precio por pieza; los índices por genérico del INPC no se alcanzaron a bajar sin token de la API) y precio de compra de vivienda.
