# Folio 003 | Informalidad y empleo por ciudad (ENOE)

Participación, desocupación, informalidad laboral y ocupación en el sector informal para las 39 ciudades de la ENOE, cada trimestre desde 2019, con su intervalo de 90%. León y sus comparables (Querétaro, Aguascalientes, San Luis Potosí, Puebla y Tijuana) además por sexo y por sector. Fuente: INEGI | ENOE, población de 15 años y más | microdatos (tabla SDEM).

El cálculo reproduce lo que publica el INEGI: en 2026-T2 coincide en las seis ciudades y en el agregado.

## Orden

1. **ENOE | 1. sondeo** (hecho el 12 nov 2026).
2. **ENOE | 2. llenado**: una vez, desde 2019-1. Baja ~30 trimestres (~1 GB, unos 30 minutos) y abre un PR con `data/processed/enoe/`.
3. **ENOE | 3. actualización trimestral**: corre sola los días 26 y 28 de febrero, mayo, agosto y noviembre, y el 3 del mes siguiente. Si el INEGI ya publicó un trimestre nuevo, abre o actualiza el PR `enoe/actualizacion`. Con un PR abierto, no hace nada más.

## Qué hay en `data/processed/enoe/`

- `trimestral/AAAA-TN/`: por trimestre, `ciudades.csv`, `desgloses.csv` y `meta.json`.
- `ciudades_trimestral.csv`: todas las ciudades y los agregados («39 ciudades» y «36 ciudades», el conjunto que existe desde 2019).
- `desgloses_trimestral.csv`: León y comparables por sexo y por sector.
- `control.md`: último trimestre contra hace un año y contra 2019, lugar de León entre las 39, cuadre contra lo publicado. Es el texto del PR.

Cada tasa trae `_ic90`: el intervalo de 90% en puntos. Un cambio entre dos trimestres solo cuenta si es mayor que la raíz de la suma de los cuadrados de los dos `_ic90`.

## Método

- Universo: entrevista completa (`R_DEF` = 00), residentes (`C_RES` 1 o 3), 15 a 98 años.
- Factor: `FAC` hasta 2020-T1, `FAC_TRI` después. Diseño: estrato (`EST_D` o `EST_D_TRI`) y `UPM`, linealización con reemplazo.
- Informalidad laboral = ocupados con `EMP_PPAL` = 1 entre ocupados. Sector informal = `TUE_PPAL` = 1 entre ocupados.
- 2020-T2 no existe (ETOE). 2020-T3 a 2022-T4 es la ENOE Nueva Edición, en parte por teléfono: se marca.
- Coatzacoalcos, Ciudad del Carmen y Tapachula entraron en 2020-T1: contra 2019 se compara con el agregado de 36.
- Comparaciones entre años: mismo trimestre (hay estacionalidad).

## Notas técnicas

- El INEGI responde 200 también a archivos que no existen y su HEAD no trae tamaño: un trimestre cuenta como publicado solo si sus primeros bytes son «PK» (zip).
- `CVE_ENT` se llamaba `ENT` hasta 2025-T2; el script acepta los dos.

## Plan B (laptop)

```bash
pip install -r scripts/enoe/requirements.txt
python scripts/enoe/extraer.py --faltantes --desde 2019-1 --max 60 --borrar-crudo
python scripts/enoe/consolidar.py
```
