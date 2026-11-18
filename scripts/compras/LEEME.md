# Folio 005 | ¿A dónde se van tus 100 pesos?

Dónde compran los hogares y cómo pagan, en el país (por defecto) y en Guanajuato, de la pandemia (2020) a 2024, la ENIGH más reciente. El peso de la pieza está en el cambio de 2022 a 2024, ya sin el rebote de la reapertura. Página: `/compras/`.

## Cómo reproducirlo

1. Descarga del INEGI la ENIGH Nueva serie → Microdatos → **Datos abiertos (CSV)** de 2020, 2022 y 2024 y descomprime todo en una misma carpeta, sin cambiar los nombres (no se sube al repo). `extraer.py` usa solo `gastoshogar` y `concentradohogar` de cada año.
2. Instala dependencias: `pip install pandas numpy`.
3. Corre, desde la raíz del repo:

```bash
python scripts/compras/extraer.py RUTA/A/LA/CARPETA_ENIGH   # → data/processed/compras/hogares_<año>.csv.gz
python scripts/compras/calcular.py                         # → indicadores.csv, cambios.csv, deciles.json
python scripts/compras/build_page.py                       # → compras/index.html
```

`extraer.py` tarda alrededor de un minuto y `calcular.py`, unos 40 segundos. `build_page.py` revisa que los datos sigan sosteniendo lo que dice el texto (el titular de 17.5 a 14.3 en el país, que la caída de la tiendita y del efectivo sea mayor que el margen de error, que la tiendita caiga en al menos 9 deciles y más en medio, que el efectivo no se mueva en los deciles 1 a 3, el internet abajo de 1.5 de cada 100 pesos, a dónde se fueron los pesos, etc.); si algo falla, no escribe la página.

## Qué hace cada paso

- `extraer.py`: une cada gasto con su hogar, se queda con el gasto monetario del hogar (tipo G1) y suma, por hogar, el gasto trimestral por lugar de compra, por forma de pago (solo compras con lugar), en comida y bebida para la casa por lugar, y en la tiendita por forma de pago. Calcula los deciles nacionales de ingreso corriente de cada edición. Se detiene si algún gasto no encuentra su hogar.
- `calcular.py`: proporciones (gasto en un lugar / gasto con lugar de compra) para el país, Guanajuato, urbano y rural y cada decil, con error estándar por linealización de Taylor (estratos `est_dis`, UPM `upm`). Los dominios se estiman sin recortar la muestra. Diferencias entre ediciones como muestras independientes. Cortes de deciles de 2024 llevados a pesos de diciembre de 2025 con el INPC de `data/fuentes/gasto/inpc_mensual.csv`.
- `build_page.py`: arma la página desde `site_src/compras.html` y escribe los datos que usa adentro.

## Salidas (`data/processed/compras/`)

- `hogares_<año>.csv.gz`: un renglón por hogar (folio, entidad, estrato, UPM, factor, ingreso, decil, urbano y las sumas de gasto `L`, `P`, `F`, `T`).
- `indicadores.csv`: año, dominio (`mx`, `gto`, `mx_urb`, `mx_rur`, `d1`…`d10`), tema (`canal`, `comida`, `pago`, `tiendita_pago`, `contexto`), indicador, proporción, error estándar, intervalo al 90% y hogares en muestra.
- `cambios.csv`: diferencias 2020→2024 y 2022→2024 con su error y si son distintas de cero al 90%.
- `deciles.json`: cortes de ingreso de 2024.

## Notas

- Lugar de compra y forma de pago tienen el mismo catálogo en las tres ediciones. Cerca de 31% del gasto monetario del hogar no tiene lugar de compra (luz, renta, colegiaturas, transporte) y queda fuera; la proporción casi no cambia entre ediciones.
- En 2024 el INEGI pasó las claves de productos a la Clasificación del Consumo Individual por Finalidades (COICOP 2018): de 4 a 6 caracteres. Solo afecta al corte «comida para la casa» (`es_comida_casa()` en `extraer.py`). Ojo: la comida preparada para llevar (pizza, pollo rostizado, carnitas, barbacoa) está en A198–A202 antes de 2024 y en 11112x en 2024; y en 2024 hay alimentos en la sección 1811. Sin ese ajuste, «comer fuera» salta de 12 a 18 de cada 100 pesos de un año a otro.
- 2020 se levantó de agosto a noviembre de 2020, en pandemia. La página compara también contra 2022.
- Grupos: «súper y cadenas» = supermercado, departamental, club de precios y conveniencia; «mercado y calle» = mercado, tianguis y ambulantes; «todo lo demás» = restaurantes, fondas, cafeterías y bares, otras personas, internet, Diconsa, Liconsa y compras fuera del país.
- La ENIGH representa al país y a cada estado. Con unos 3,100 hogares por edición, Guanajuato no se parte en deciles.
