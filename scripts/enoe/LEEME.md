# Folio 003 | Informalidad y empleo en México (ENOE)

Participación, desocupación, informalidad laboral y ocupación en el sector informal para el total nacional, las 32 entidades, los cuatro tamaños de localidad y las 39 ciudades de la ENOE, cada trimestre desde 2019, con su intervalo de 90%. Por sexo y por sector: total nacional, agregado de 36 ciudades, León y comparables (Querétaro, Aguascalientes, San Luis Potosí, Puebla y Tijuana). Fuente: INEGI | ENOE, población de 15 años y más | microdatos (tabla SDEM).

El cálculo reproduce lo que publica el INEGI: en 2026-T2 coincide en las seis ciudades y en el agregado; el total nacional y cinco entidades se cuadran en `control.md` contra el boletín del trimestre.

Título del folio (17 nov 2026): «Menos desempleo, la misma informalidad: así cambió el trabajo en las ciudades desde 2019». `control.md` revisa en cada corrida si los datos lo siguen sosteniendo.

## Orden

1. **ENOE | 1. sondeo** (hecho el 12 nov 2026).
2. **ENOE | 2. llenado**: desde 2019-1. Baja ~30 trimestres (~1 GB, unos 30 minutos) y abre un PR con `data/processed/enoe/`. Con «rehacer» marcado vuelve a calcular también los trimestres que ya están (hace falta cuando el script agrega indicadores, como el 17 nov 2026 con el total nacional y las entidades).
3. **ENOE | 3. actualización trimestral**: corre sola los días 26 y 28 de febrero, mayo, agosto y noviembre, y el 3 del mes siguiente. Si el INEGI ya publicó un trimestre nuevo, abre o actualiza el PR `enoe/actualizacion`. Con un PR abierto, no hace nada más.

## Qué hay en `data/processed/enoe/`

- `trimestral/AAAA-TN/`: por trimestre, `nacional.csv`, `ciudades.csv`, `desgloses.csv` y `meta.json`.
- `nacional_trimestral.csv`: total nacional (`dominio` = nacional), 32 entidades (`entidad`, clave `CVE_ENT`) y cuatro tamaños de localidad (`localidad`: 1 = 100 mil y más habitantes, 2 = 15 mil a 99 999, 3 = 2 500 a 14 999, 4 = menos de 2 500).
- `ciudades_trimestral.csv`: todas las ciudades y los agregados: «39 ciudades» (desde 2020), «36 ciudades» (el conjunto que existe desde 2019) y «36 ciudades sin Ciudad de México».
- `desgloses_trimestral.csv`: nacional, 36 ciudades, León y comparables por sexo y por sector.
- `control.md`: si el título se sostiene; nacional, tamaño de localidad y agregados contra 2019; las entidades; León y comparables; cuadre contra lo publicado; cobertura. Es el texto del PR.

Cada tasa trae `_ic90`: el intervalo de 90% en puntos. Cambios contra 2019: promedio de los últimos cuatro trimestres contra el promedio de 2019; margen conservador (promedio de los `_ic90` de cada lado y raíz de la suma de cuadrados). Un cambio solo cuenta si es mayor que ese margen.

## La página

- `scripts/enoe/build_page.py` arma `informalidad/index.html` desde la plantilla `site_src/informalidad.html` y los CSV de `data/processed/enoe/`. Corre sin argumentos; la actualización trimestral lo llama después de consolidar.
- Los textos se corrigen en la plantilla (`site_src/informalidad.html`), no en `informalidad/index.html`: ese archivo se reescribe cada vez que se arma la página.
- El título está en `consolidar.py` (`TITULO`) y lo revisa `titular()`. Si los datos dejan de sostenerlo, `build_page.py` no escribe nada y termina con error.
- Los títulos de sección se calculan con los datos. La imagen para redes (`assets/og/informalidad.png`) y la tarjeta de la portada son fijas: muestran el mapa del 2.º trimestre de 2026.

## Método

- Universo: entrevista completa (`R_DEF` = 00), residentes (`C_RES` 1 o 3), 15 a 98 años.
- Factor: `FAC` hasta 2020-T1, `FAC_TRI` después. Diseño: estrato (`EST_D` o `EST_D_TRI`) y `UPM`, linealización con reemplazo.
- Informalidad laboral = ocupados con `EMP_PPAL` = 1 entre ocupados. Sector informal = `TUE_PPAL` = 1 entre ocupados.
- 2020-T2 no existe (ETOE). 2020-T3 a 2022-T4 es la ENOE Nueva Edición, en parte por teléfono: se marca.
- Coatzacoalcos, Ciudad del Carmen y Tapachula entraron en 2020-T1: contra 2019 se compara con el agregado de 36.
- Comparaciones entre años: mismo trimestre, o promedios de cuatro trimestres (hay estacionalidad).
- Tamaño de localidad: `T_LOC` en 2019 y `T_LOC_TRI` desde 2020-T3.
- 2024-T4: el INEGI actualizó la población de las ciudades (saltos de hasta 19% en un trimestre con la misma muestra). Las tasas se comparan; las cifras en número de personas no se comparan a través de ese trimestre.

## Notas técnicas

- El INEGI responde 200 también a archivos que no existen y su HEAD no trae tamaño: un trimestre cuenta como publicado solo si sus primeros bytes son «PK» (zip).
- `CVE_ENT` se llamaba `ENT` hasta 2025-T2; el script acepta los dos.

## Plan B (laptop)

```bash
pip install -r scripts/enoe/requirements.txt
python scripts/enoe/extraer.py --faltantes --desde 2019-1 --max 60 --borrar-crudo
python scripts/enoe/consolidar.py
```
