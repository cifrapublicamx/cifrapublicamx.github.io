# Cifra Pública

Datos públicos de León y Guanajuato convertidos en mapas, tableros y herramientas para decidir.

## León crece desde las orillas · `/mapa-leon/`

Dónde ganó y dónde perdió negocios León entre 2019 y 2024, por zona y giro, con el Directorio Estadístico Nacional de Unidades Económicas (DENUE) del INEGI.

### Cómo reproducirlo

1. Descarga del INEGI (DENUE → descarga masiva → Guanajuato → CSV) las ediciones **11/2019**, **11/2024** y **05/2025** y guarda los CSV en `data/raw/` como `denue_gto_2019_11.csv`, `denue_gto_2024_11.csv` y `denue_gto_2025_05.csv`.
2. Instala dependencias: `pip install pandas h3` y `npm install`.
3. Corre:

```bash
python scripts/pipeline.py data/raw/denue_gto_2019_11.csv 2019-11
python scripts/pipeline.py data/raw/denue_gto_2024_11.csv 2024-11
python scripts/pipeline.py data/raw/denue_gto_2025_05.csv 2025-05
python scripts/compara.py 2019-11 2024-11
python scripts/compara.py 2024-11 2025-05
python scripts/extras.py 2019-11 2024-11
python scripts/build_page.py --base 2019-11 --final 2024-11 --reciente 2025-05 \
  --autor "Rodrigo Méndez Hernández" --correo cifrapublicamx@gmail.com --fecha "5 de noviembre de 2026"
```

`mapa-leon/index.html` trae los datos y Leaflet adentro; las fuentes (Bricolage Grotesque y Figtree, licencia OFL), el logotipo y el favicon viven en `assets/` y los comparten todas las páginas.

### Qué hace cada paso

- `pipeline.py`: filtra León, asigna cada negocio a un hexágono H3 (resolución 8, ~0.7 km²) y a un giro.
- `compara.py`: cruza dos ediciones por la clave de INEGI (aparecen / ya no aparecen), revisa que los códigos SCIAN de los giros existan en ambas y genera el GeoJSON.
- `extras.py`: cifras de apoyo (calzado por tamaño y en el Coecillo, y las curiosidades).
- `build_page.py`: calcula los anillos de distancia a la Plaza Principal y arma la página desde `site_src/mapa-leon.html`.

### Notas de método

- La comparación principal usa solo ediciones actualizadas por completo con Censos Económicos (11/2019, 11/2024). Las intermedias, como la 05/2025, actualizan sobre todo a los negocios grandes: la página las muestra aparte y no saca de ellas conclusiones sobre el patrón.
- Abarrotes y minisúpers van juntos: entre 11/2024 y 05/2026 el INEGI movió cientos de negocios de León entre esos dos códigos.
- "Ya no aparece" puede ser un cierre o un cambio de registro.

`data/processed/` contiene las salidas intermedias; los CSV originales del INEGI no se suben al repo.

## León gasta más por habitante desde 2023 · `/gasto-leon/`

Cuánto gasta el Municipio de León, para qué, en qué, de dónde sale el dinero y cuánto se aparta de lo aprobado, de 2016 a 2025, en pesos de 2025 y por habitante, con Querétaro, Puebla y Tijuana como referencia. Fuente principal: la cuenta pública anual de la Tesorería de León.

### Cómo reproducirlo

Los archivos de origen ya están en `data/fuentes/gasto/` (pesan poco y uno de ellos ya no se puede descargar del sitio de la Tesorería):

- `cuenta_publica/`: estados analíticos del ejercicio del presupuesto de egresos, por función (finalidad y función) y por capítulo (capítulo y concepto), 2016–2025. Tesorería de León → Transparencia financiera → Ley General de Contabilidad Gubernamental → año → Cuenta Pública Anual. Los .XLS del sitio son .xlsx por dentro; aquí van con su extensión real.
- `efipem_ciudades_2016_2025.csv`: León, Querétaro, Puebla y Tijuana en la Estadística de Finanzas Públicas Estatales y Municipales del INEGI (datos abiertos, recorte de la base municipal; 2025 preliminar).
- `poblacion_ciudades.csv`: población de las cuatro ciudades en el Censo 2020 y la Encuesta Intercensal 2025 (INEGI).
- `inpc_mensual.csv`: INPC mensual, base 2a quincena de julio de 2018 = 100 (INEGI).
- `poblacion_anclas.csv`: población de León en la Encuesta Intercensal 2015, el Censo 2020 y la Encuesta Intercensal 2025 (INEGI).
- `cifras_seguridad_publicadas.csv`: los porcentajes de «seguridad» publicados en prensa que la página compara, con su fuente.

Instala dependencias (`pip install pandas openpyxl`) y corre:

```bash
python scripts/gasto/extraer.py
python scripts/gasto/validar.py
python scripts/gasto/reales.py
python scripts/gasto/control_efipem.py
python scripts/gasto/ingresos_y_ciudades.py
python scripts/gasto/build_page.py --autor "Rodrigo Méndez Hernández" \
  --correo cifrapublicamx@gmail.com --fecha "9 de noviembre de 2026"
```

### Qué hace cada paso

- `extraer.py`: lee los 20 Excel y los deja en una tabla larga (`data/processed/gasto/egresos_leon.csv`). 2016 y 2017 traen la clave del CONAC; los demás años se emparejan por nombre.
- `validar.py`: falla si a un año le faltan claves, si un subtotal no suma o si el total por función no coincide con el total por capítulo.
- `reales.py`: pasa todo a pesos de 2025 (promedio anual del INPC) y por habitante (población interpolada entre 2015, 2020 y 2025).
- `control_efipem.py`: compara cada año, capítulo por capítulo, con la EFIPEM del INEGI.
- `ingresos_y_ciudades.py`: ingresos de León por origen (EFIPEM) y comparación con Querétaro, Puebla y Tijuana en el último año con cifras definitivas para las cuatro.
- `build_page.py`: arma la página desde `site_src/gasto-leon.html`.

### Notas de método

- Se usa lo devengado. Es la administración central: SAPAL, el DIF y los demás organismos llevan cuentas aparte.
- La comparación entre ciudades excluye la disponibilidad final y el pago de deuda del gasto. Cada ciudad organiza distinto sus servicios, así que sirve para ubicar a León, no para calificar.
- 2021, capítulo y concepto: el archivo anual no se puede descargar del sitio (responde con un aviso de «solo para consumo interno»); se usa el del cuarto trimestre, acumulado al cierre, que da el mismo total.
- La EFIPEM coincide con la cuenta pública si se le quita la «disponibilidad final», que el INEGI cuenta como egreso.
- La clasificación por función cambió en 2018 y 2022 en algunas funciones (Comunicaciones, Construcción, Transporte, Otros asuntos sociales, Protección social); las series de diez años se muestran por finalidad y para seguridad pública.
- Los meses de agosto de 2024 a diciembre de 2025 del INPC no vienen en el archivo de datos abiertos del INEGI (llega a julio de 2024). Se tomaron de una reproducción de las tablas del INEGI y se cotejaron con los valores publicados por el INEGI para diciembre de 2024 (137.949), noviembre de 2025 (142.645) y diciembre de 2025 (143.042). Enero de 2016 a julio de 2024 coincide exacto con el archivo oficial.
