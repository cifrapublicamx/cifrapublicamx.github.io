# Folio 003 | Empleo formal (IMSS)

Puestos de trabajo afiliados al IMSS, mes a mes desde 2019: todo el país a nivel municipio (total) y detalle por sector, tamaño de patrón, sexo, edad y salario para los municipios de `data/fuentes/empleo/municipios.csv`. Fuente: IMSS | Datos abiertos | «Puestos de trabajo registrados por los patrones en el IMSS y asegurados sin un empleo asociado» (un CSV de ~400 MB por mes).

Todo corre en GitHub Actions. Cada workflow abre un PR; el merge lo haces tú.

## Una sola vez: permisos de Actions

Settings → Actions → General → Workflow permissions:

- «Read and write permissions»
- ☑ «Allow GitHub Actions to create and approve pull requests»
- Save

## Orden

1. **Empleo IMSS | 1. sondeo** (Actions → el workflow → Run workflow). Baja el mes más reciente, revisa columnas, claves y catálogos, y abre un PR con `data/fuentes/empleo/sondeo/reporte.md`. El mismo reporte sale en el resumen de la corrida.
2. Con el reporte:
   - `data/fuentes/empleo/claves.json`: cambiar `pendiente` por `inegi` (si Guanajuato = 11 y León = 20) o por `imss` (y entonces llenar `cve_entidad_imss` y `cve_municipio_imss` en `municipios.csv`). Mientras diga `pendiente`, la extracción no corre.
   - `data/fuentes/empleo/sectores.csv`: los grupos o fracciones del calzado que se van a seguir en todo el país.
   - Confirmar la lista de `municipios.csv`: agregar un municipio después obliga a rehacer los ~94 meses.
3. **Empleo IMSS | 2. llenado inicial**, desde 2019-01. Un job por año, dos a la vez. Al final, un PR con todo y `data/processed/empleo/control.md` (cuadre contra boletines, saltos y último mes).
4. **Empleo IMSS | 3. actualización mensual** corre sola los días 12, 16, 21 y 26. Si hay un mes nuevo, abre o actualiza el PR `empleo/actualizacion`. Mientras ese PR esté abierto, no hace nada más.

## Qué hace cada script

- `imss.py`: busca los archivos del mes en el portal (API de DKAN y, si falla, la página), los baja por http (el portal no sirve https) y los lee (latin-1 o UTF-8; separador detectado).
- `sondeo.py`: el reporte del paso 1.
- `extraer.py`: un mes → `data/processed/empleo/mensual/AAAA-MM/` (agregados de pocos KB y `meta.json`). El CSV crudo va a `data/raw/empleo/`, que no entra al repo.
- `consolidar.py`: junta los meses en series y escribe `control.md`.
- `abrir_pr.sh`: abre o actualiza el PR (solo lo usan los workflows).

## Plan B: si el IMSS no deja descargar desde GitHub

Lo mismo en tu laptop, con Python 3.11 o más reciente:

```bash
pip install -r scripts/empleo/requirements.txt
python scripts/empleo/sondeo.py
python scripts/empleo/extraer.py --faltantes --desde 2019-01 --max 100 --borrar-crudo
python scripts/empleo/consolidar.py
```

Luego subes `data/processed/empleo/` y `data/fuentes/empleo/sondeo/`.

## Notas de método

- El municipio es el del registro patronal, no el del centro de trabajo.
- El salario es el salario base de cotización (tope de 25 UMA, piso de un salario mínimo); el salario diario promedio = `masa_sal_ta / ta_sal`.
- Rupturas conocidas que `control.md` marca: reforma de subcontratación (jul–sep 2021), plataformas digitales (desde jul 2025 y ajuste en ene–mar 2026), registro patronal fraudulento cancelado (may 2026).
