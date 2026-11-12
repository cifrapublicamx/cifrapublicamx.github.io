"""
Cifra Pública | Folio 003 | Extracción mensual del archivo de asegurados del IMSS.

Por cada mes guarda en data/processed/empleo/mensual/AAAA-MM/:
- municipios.csv.gz       todo el país, un renglón por municipio (total de puestos y salario)
- detalle_sector.csv.gz   municipios elegidos, por división, grupo y fracción
- detalle_tamano.csv.gz   municipios elegidos, por grupo y tamaño de patrón
- detalle_sexo_edad.csv.gz municipios elegidos, por sexo y rango de edad
- detalle_salario.csv.gz  municipios elegidos, por rango salarial en UMA
- sectores_municipios.csv.gz  todo el país, solo los sectores de data/fuentes/empleo/sectores.csv
- meta.json               de dónde salió, cuánto pesó, qué columnas traía y totales

El CSV del IMSS (~400 MB) se baja a data/raw/empleo/ (fuera del repo) y se borra con --borrar-crudo.

Antes de extraer, data/fuentes/empleo/claves.json debe decir cómo vienen las claves de
municipio («inegi» o «imss»): lo confirma el sondeo.

Uso:
    python scripts/empleo/extraer.py --mes 2026-08
    python scripts/empleo/extraer.py --faltantes --desde 2019-01 --max 12 --borrar-crudo
    python scripts/empleo/extraer.py --plan --desde 2019-01          # años con meses pendientes (JSON)
    python scripts/empleo/extraer.py --archivo data/raw/empleo/asg-2026-08-31.csv --mes 2026-08
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import imss  # noqa: E402

import pandas as pd  # noqa: E402

VERSION = "2026-11-12"
MEDIDAS_TOTAL = ["ta", "teu", "tec", "tpu", "tpc", "ta_sal", "masa_sal_ta", "asegurados", "no_trabajadores"]
MEDIDAS_DET = ["ta", "teu", "tec", "tpu", "tpc", "ta_sal", "masa_sal_ta"]
CORTES = {  # nombre -> columnas
    "detalle_sector": ["sector_economico_1", "sector_economico_2", "sector_economico_4"],
    "detalle_tamano": ["sector_economico_2", "tamano_patron"],
    "detalle_sexo_edad": ["sexo", "rango_edad"],
    "detalle_salario": ["rango_uma"],
}
GZ = {"method": "gzip", "mtime": 0}   # mismo contenido = mismos bytes (sin ruido en los PR)


def norm(c) -> str:
    c = ("" if c is None else str(c)).strip()
    return str(int(c)) if c.isdigit() else c.upper()


def _norm_serie(serie: pd.Series) -> pd.Series:
    """norm() sobre una columna, calculado una vez por valor distinto (son pocos)."""
    return serie.map({v: norm(v) for v in serie.unique()})


def lee_claves() -> str:
    archivo = imss.FUENTES / "claves.json"
    if not archivo.exists():
        return "pendiente"
    return json.loads(archivo.read_text(encoding="utf-8")).get("claves_municipio", "pendiente")


def lee_municipios(modo: str) -> dict[tuple[str, str], str]:
    """{(entidad, municipio) normalizados como vienen en el IMSS: clave_inegi}"""
    out = {}
    for fila in csv.DictReader((imss.FUENTES / "municipios.csv").open(encoding="utf-8")):
        if modo == "imss":
            e, m = fila.get("cve_entidad_imss", ""), fila.get("cve_municipio_imss", "")
            if not (e and m):
                print(f"Aviso: {fila['municipio']} no tiene clave IMSS en municipios.csv; se omite del detalle.")
                continue
        else:
            e, m = fila["clave_inegi"][:2], fila["clave_inegi"][2:]
        out[(norm(e), norm(m))] = fila["clave_inegi"]
    return out


def lee_sectores() -> list[tuple[str, str]]:
    archivo = imss.FUENTES / "sectores.csv"
    if not archivo.exists():
        return []
    return [(f["nivel"].strip(), norm(f["clave"])) for f in csv.DictReader(archivo.open(encoding="utf-8"))
            if f.get("nivel") and f.get("clave")]


def _suma(acum: dict, df: pd.DataFrame, llaves: list[str], medidas: list[str]):
    if df.empty:
        return
    g = df.groupby(llaves, sort=False)[medidas].sum()
    previo = acum.get("df")
    acum["df"] = g if previo is None else previo.add(g, fill_value=0)


def _escribe(df: pd.DataFrame | None, ruta: Path, llaves: list[str], medidas: list[str]):
    if df is None:
        df = pd.DataFrame(columns=llaves + medidas)
    else:
        df = df.reset_index()
    for c in medidas:
        if c in df.columns:
            df[c] = df[c].round(2) if c.startswith("masa") else df[c].round().astype("int64")
    df = df.sort_values(llaves).reset_index(drop=True)
    df.to_csv(ruta, index=False, compression=GZ if ruta.suffix == ".gz" else None)


def procesa(ruta: Path, mes: str, rec: imss.Recurso | None, modo: str) -> dict:
    t0 = time.time()
    fmt = imss.detecta_formato(ruta)
    faltan = [c for c in imss.REQUERIDAS if c not in fmt.columnas]
    if faltan:
        raise KeyError(f"{mes}: faltan columnas requeridas {faltan}. Columnas del archivo: {fmt.columnas}")
    medidas_tot = [c for c in MEDIDAS_TOTAL if c in fmt.columnas]
    usar = sorted({"cve_entidad", "cve_municipio", *sum(CORTES.values(), []), *medidas_tot},
                  key=fmt.columnas.index)
    elegidos = lee_municipios(modo)
    sectores = lee_sectores()
    niveles = sorted({n for n, _ in sectores})
    acum = defaultdict(dict)
    filas = 0
    vistos = set()
    for parte in imss.lee_por_partes(ruta, fmt, usar):
        filas += len(parte)
        parte["e"] = _norm_serie(parte["cve_entidad"])
        parte["m"] = _norm_serie(parte["cve_municipio"])
        _suma(acum["municipios"], parte, ["e", "m"], medidas_tot)
        llave = list(zip(parte["e"], parte["m"]))
        parte["clave_inegi"] = [elegidos.get(k, "") for k in llave]
        det = parte[parte["clave_inegi"] != ""]
        vistos.update(det["clave_inegi"].unique())
        for nombre, cols in CORTES.items():
            meds = ["ta", "ta_sal"] if nombre == "detalle_salario" else MEDIDAS_DET
            _suma(acum[nombre], det, ["clave_inegi", *cols], meds)
        for nivel in niveles:
            claves = {c for n, c in sectores if n == nivel}
            normalizado = _norm_serie(parte[nivel])
            sel = parte[normalizado.isin(claves)].copy()
            if not sel.empty:
                sel["nivel"] = nivel
                sel["clave"] = normalizado[sel.index]
                _suma(acum["sectores_municipios"], sel, ["e", "m", "nivel", "clave"],
                      ["ta", "tpu", "tpc", "ta_sal", "masa_sal_ta"])

    destino = imss.MENSUAL / mes
    destino.mkdir(parents=True, exist_ok=True)
    mun = acum["municipios"].get("df")
    if mun is not None:
        mun.index = mun.index.set_names(["cve_entidad", "cve_municipio"])
    _escribe(mun, destino / "municipios.csv.gz", ["cve_entidad", "cve_municipio"], medidas_tot)
    for nombre, cols in CORTES.items():
        meds = ["ta", "ta_sal"] if nombre == "detalle_salario" else MEDIDAS_DET
        _escribe(acum[nombre].get("df"), destino / f"{nombre}.csv.gz", ["clave_inegi", *cols], meds)
    if niveles:
        sm = acum["sectores_municipios"].get("df")
        if sm is not None:
            sm.index = sm.index.set_names(["cve_entidad", "cve_municipio", "nivel", "clave"])
        _escribe(sm, destino / "sectores_municipios.csv.gz", ["cve_entidad", "cve_municipio", "nivel", "clave"],
                 ["ta", "tpu", "tpc", "ta_sal", "masa_sal_ta"])

    totales = {c: float(mun[c].sum()) for c in medidas_tot} if mun is not None else {}
    meta = {
        "mes": mes,
        "fecha_corte": rec.fecha_corte if rec else None,
        "url": rec.url if rec else str(ruta),
        "bytes": ruta.stat().st_size,
        "sha256": imss.sha256(ruta),
        "filas": filas,
        "codificacion": fmt.codificacion,
        "separador": fmt.separador,
        "columnas": fmt.columnas,
        "columnas_nuevas": [c for c in fmt.columnas if c not in imss.DIMENSIONES + imss.MEDIDAS],
        "claves_municipio": modo,
        "municipios_elegidos_sin_datos": sorted(set(elegidos.values()) - vistos),
        "totales": totales,
        "segundos": round(time.time() - t0, 1),
        "procesado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "version_script": VERSION,
    }
    imss.escribe_json(destino / "meta.json", meta)
    return meta


def pendientes(desde: str, hasta: str | None, s=None, bitacora=None) -> dict[str, imss.Recurso]:
    hasta = hasta or f"{imss.anio_actual()}-12"
    anios = range(int(desde[:4]), int(hasta[:4]) + 1)
    disponibles = imss.descubrir(anios, s=s, bitacora=bitacora)
    hechos = imss.meses_procesados()
    return {m: r for m, r in disponibles.items() if desde <= m <= hasta and m not in hechos}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mes", nargs="*", default=[], help="uno o más AAAA-MM")
    ap.add_argument("--archivo", help="procesar un CSV ya descargado (con --mes)")
    ap.add_argument("--faltantes", action="store_true", help="procesar los meses que aún no están")
    ap.add_argument("--plan", action="store_true", help="solo listar los años con meses pendientes")
    ap.add_argument("--desde", default="2019-01")
    ap.add_argument("--hasta", default="")
    ap.add_argument("--max", type=int, default=3, help="tope de meses por corrida")
    ap.add_argument("--borrar-crudo", action="store_true")
    ap.add_argument("--rehacer", action="store_true", help="volver a procesar aunque ya exista")
    a = ap.parse_args()

    s = imss.sesion()
    modo = lee_claves()
    if modo not in ("inegi", "imss"):
        print("Alto: data/fuentes/empleo/claves.json todavía dice «pendiente». Corre el sondeo, revisa "
              "cómo vienen las claves de municipio y cambia el valor a «inegi» o «imss».")
        imss.resumen_github("**Alto:** falta confirmar las claves de municipio en `data/fuentes/empleo/claves.json`.")
        return 2

    if a.plan:
        pend = pendientes(a.desde, a.hasta or None)
        anios = sorted({m[:4] for m in pend})
        print(json.dumps({"anios": anios, "meses": sorted(pend)}))
        salida = os.environ.get("GITHUB_OUTPUT")
        if salida:
            with open(salida, "a", encoding="utf-8") as f:
                f.write(f"anios={json.dumps(anios)}\n")
                f.write(f"total={len(pend)}\n")
        return 0

    if a.archivo:
        if len(a.mes) != 1:
            ap.error("--archivo va con un solo --mes")
        meta = procesa(Path(a.archivo), a.mes[0], None, modo)
        print(json.dumps(meta["totales"], ensure_ascii=False))
        return 0

    if a.faltantes:
        trabajo = pendientes(a.desde, a.hasta or None)
    else:
        disponibles = imss.descubrir(sorted({int(m[:4]) for m in a.mes}))
        trabajo = {m: disponibles[m] for m in a.mes if m in disponibles}
        for m in a.mes:
            if m not in disponibles:
                print(f"{m}: no está en el portal.")
        if not a.rehacer:
            trabajo = {m: r for m, r in trabajo.items() if m not in imss.meses_procesados()}
    meses = sorted(trabajo)[: a.max]
    print(f"Meses por procesar ({len(meses)} de {len(trabajo)}): {', '.join(meses) or 'ninguno'}")
    renglones = ["| Mes | Puestos (ta) | MB | Descarga (s) | Proceso (s) | Estado |", "|---|---|---|---|---|---|"]
    fallas = 0
    for mes in meses:
        rec = trabajo[mes]
        try:
            t0 = time.time()
            ruta = imss.descargar(rec, s=s)
            t_desc = time.time() - t0
            meta = procesa(ruta, mes, rec, modo)
            renglones.append(f"| {mes} | {meta['totales'].get('ta', 0):,.0f} | {meta['bytes'] / 1e6:,.0f} | "
                             f"{t_desc:,.0f} | {meta['segundos']:,.0f} | ok |")
            print(f"{mes}: ok ({meta['totales'].get('ta', 0):,.0f} puestos)", flush=True)
            if a.borrar_crudo:
                ruta.unlink(missing_ok=True)
        except Exception as e:                             # noqa: BLE001
            fallas += 1
            motivo = " ".join(str(e).split()).replace("|", "/")[:200]
            renglones.append(f"| {mes} | — | — | — | — | falla: {type(e).__name__}: {motivo} |")
            print(f"{mes}: FALLA\n{traceback.format_exc()}", flush=True)
    imss.resumen_github("### Extracción\n\n" + "\n".join(renglones) + "\n")
    salida = os.environ.get("GITHUB_OUTPUT")
    if salida:
        with open(salida, "a", encoding="utf-8") as f:
            f.write(f"nuevos={len(meses) - fallas}\n")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
