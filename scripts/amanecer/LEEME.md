# Folio 004 | Mismo reloj, otro sol

A qué hora sale el sol en cada localidad de México, cada día del ciclo escolar 2026-2027. Página: `/amanecer/`.

## Cómo reproducirlo

1. Descarga del INEGI el Censo de Población y Vivienda 2020 → Datos abiertos → **Principales resultados por localidad (ITER)**, «Estados Unidos Mexicanos», CSV. Descomprime y deja `conjunto_de_datos_iter_00CSV20.csv` en `data/raw/` (no se sube al repo).
2. Instala dependencias: `pip install pandas numpy h3 tzdata`.
3. Corre, desde la raíz del repo:

```bash
python scripts/amanecer/prep_iter.py      # ITER → data/raw/amanecer/localidades_2020.csv
python scripts/amanecer/calcular.py       # → data/processed/amanecer/
python scripts/amanecer/build_page.py     # → amanecer/index.html
```

`calcular.py` tarda unos 15 segundos. `build_page.py` revisa que los datos sigan sosteniendo lo que dice el texto (los extremos, los 98 minutos, «8 de cada 10», el pico de marzo en la frontera, León sin días después de las 7:30); si algo falla, no escribe la página.

## Qué hace cada paso

- `prep_iter.py`: convierte las coordenadas del ITER (grados, minutos y segundos) a decimales, toma población total y de 3 a 5, 6 a 11, 12 a 14 y 15 a 17 años. Descarta las filas 9998 y 9999 (subtotales de localidades de una y dos viviendas, que ya aparecen una por una); sin ellas, la suma cuadra exacto con el total nacional (126,014,024).
- `sol.py`: ecuaciones de posición solar de la NOAA, vectorizadas. Amanecer con cenit de 90.833° (borde superior del sol con refracción); primera luz con 96° (crepúsculo civil). Precisión de uno a dos minutos.
- `calcular.py`: asigna la zona horaria de cada municipio (Ley de los Husos Horarios, reforma del DOF del 29-11-2022; cambios de horario estacional de IANA tzdata), calcula amanecer y primera luz para los 202 días entre semana del ciclo fuera de vacaciones y los atardeceres de 2027, y escribe los agregados.
- `build_page.py`: arma la página desde `site_src/amanecer.html`. La página vuelve a calcular el sol en el navegador para el buscador con las mismas ecuaciones; se revisó que coincida con Python en los 2,469 municipios (diferencia máxima: 0.005 minutos).

## Salidas (`data/processed/amanecer/`)

- `municipios.csv`: localidad principal de cada municipio (la más poblada), con sus horas, más la población y los niños de 3 a 14 años del municipio.
- `hexagonos.csv`: hexágonos H3 de resolución 4 con población, niños y amanecer más tardío pesado por población.
- `distribucion.csv`: población y niños por minuto del amanecer más tardío.
- `zonas.json`: minutos de diferencia con UTC de cada zona, como transiciones día por día desde el 31 de agosto de 2026.
- `resumen.json`: cifras que cita el texto, incluida la sensibilidad de los cortes de 7:00, 7:30 y 8:00 a ±2 minutos.

## Notas

- El ciclo escolar 2026-2027 de la SEP va del 31 de agosto de 2026 al 9 de julio de 2027, con vacaciones del 21 de diciembre al 6 de enero y del 22 de marzo al 3 de abril. Se cuentan días entre semana fuera de vacaciones (202); el calendario oficial tiene 185 días de clase.
- Horario de verano: Baja California y 30 municipios de la frontera (11 de Coahuila, Anáhuac en Nuevo León, 10 de Tamaulipas y 8 de Chihuahua). Ojinaga, Coyame del Sotol y Manuel Benavides siguen la hora del centro de EE. UU.; Juárez, Janos, Ascensión, Praxedis G. Guerrero y Guadalupe, la de montaña.
- En 81,257 localidades pequeñas (414,737 habitantes) el INEGI reserva las edades; esos niños no se cuentan.
- La cifra «población donde amanece después de las 7:30» es frágil (Monterrey, Aguascalientes, Saltillo y Guadalajara quedan a un minuto del corte): la página la muestra como distribución, no como titular.
