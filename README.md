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
