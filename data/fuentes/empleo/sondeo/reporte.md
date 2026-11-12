# Sondeo del portal de datos abiertos del IMSS | 2026-11-12 19:14 UTC

Espejos probados: http://datos.imss.gob.mx, http://www2.imss.gob.mx

## 1. Qué hay en el portal

| Año | Meses | De / a | Cómo se encontró | Servidor |
| --- | --- | --- | --- | --- |
| 2019 | 0 | — | — | — |
| 2020 | 0 | — | — | — |
| 2021 | 0 | — | — | — |
| 2022 | 0 | — | — | — |
| 2023 | 0 | — | — | — |
| 2024 | 0 | — | — | — |
| 2025 | 0 | — | — | — |
| 2026 | 0 | — | — | — |

Meses que faltan dentro del rango: 2019-01.
Búsqueda: 33 s.

<details><summary>Bitácora de la búsqueda</summary>

```
http://datos.imss.gob.mx: contesta (HTTP 503, 0.3 s)
http://www2.imss.gob.mx: contesta (HTTP 503, 0.3 s)
2019 | http://datos.imss.gob.mx | asg-2019 | recursos_api: FALLA HTTPError: 503 Server Error: Service Unavailable for url: http://datos.imss.gob.mx/api/3/action/package_show?id=asg-2019 (5.4 s)
2019 | http://datos.imss.gob.mx | asg-2019 | recursos_html: FALLA HTTPError: 503 Server Error: Service Unavailable for url: http://datos.imss.gob.mx/dataset/asg-2019 (5.4 s)
2019 | http://datos.imss.gob.mx | asg2019 | recursos_api: FALLA HTTPError: 503 Server Error: Service Unavailable for url: http://datos.imss.gob.mx/api/3/action/package_show?id=asg2019 (5.3 s)
http://datos.imss.gob.mx: 3 fallas seguidas, se deja de usar. Diagnóstico: HTTP 503 | text/html | PARECE BLOQUEO | <html style="height:100%"><head><META NAME="ROBOTS" CONTENT="NOINDEX, NOFOLLOW"><meta name="format-detection" content="telephone=no"><meta name="viewport" content="initial-scale=1.0"><meta http-equiv=
2019 | http://www2.imss.gob.mx | asg-2019 | recursos_api: FALLA HTTPError: 503 Server Error: Service Unavailable for url: http://www2.imss.gob.mx/api/3/action/package_show?id=asg-2019 (5.3 s)
2019 | http://www2.imss.gob.mx | asg-2019 | recursos_html: FALLA HTTPError: 503 Server Error: Service Unavailable for url: http://www2.imss.gob.mx/dataset/asg-2019 (5.4 s)
2019 | http://www2.imss.gob.mx | asg2019 | recursos_api: FALLA HTTPError: 503 Server Error: Service Unavailable for url: http://www2.imss.gob.mx/api/3/action/package_show?id=asg2019 (5.5 s)
http://www2.imss.gob.mx: 3 fallas seguidas, se deja de usar. Diagnóstico: HTTP 503 | text/html | PARECE BLOQUEO | <html style="height:100%"><head><META NAME="ROBOTS" CONTENT="NOINDEX, NOFOLLOW"><meta name="format-detection" content="telephone=no"><meta name="viewport" content="initial-scale=1.0"><meta http-equiv=
```
</details>


## Error

```
RuntimeError: No se encontró ningún archivo mensual. Revisa la bitácora: puede ser bloqueo del portal a GitHub o cambio de direcciones.
Traceback (most recent call last):
  File "/home/runner/work/cifrapublicamx.github.io/cifrapublicamx.github.io/scripts/empleo/sondeo.py", line 301, in main
    raise RuntimeError("No se encontró ningún archivo mensual. Revisa la bitácora: "
RuntimeError: No se encontró ningún archivo mensual. Revisa la bitácora: puede ser bloqueo del portal a GitHub o cambio de direcciones.

```
