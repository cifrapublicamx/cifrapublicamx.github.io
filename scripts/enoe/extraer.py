"""
Cifra Pública | Folio 003 | Extracción trimestral de la ENOE.

Por cada trimestre guarda en data/processed/enoe/trimestral/AAAA-TN/:
- nacional.csv    total nacional, 32 entidades y 4 tamaños de localidad (dominio, clave)
- ciudades.csv    las 39 ciudades, el agregado de 39 (desde 2020), el comparable de 36 (sin las
                  ciudades que entraron en 2020) y el de 36 sin la Ciudad de México
- desgloses.csv   total nacional, agregado de 36 ciudades, León y comparables (papel
                  foco/comparable en ciudades.csv) por sexo y por sector (RAMA_EST2): las mismas
                  tasas y, por sector, su peso en la ocupación
- meta.json       archivo, tamaño, huella, filas, columnas, factor y diseño usados
En cada archivo: participación, desocupación, informalidad y sector informal, cada una con su
intervalo de 90%, más muestra y totales.

El zip (~30 MB) se baja a data/raw/enoe/ (fuera del repo) y se borra con --borrar-crudo.

Uso:
    python scripts/enoe/extraer.py --trimestres 2026-2
    python scripts/enoe/extraer.py --faltantes --desde 2019-1 --max 40 --borrar-crudo
    python scripts/enoe/extraer.py --faltantes --rehacer --desde 2019-1 --max 60 --borrar-crudo
                                                     # vuelve a calcular también los ya hechos
    python scripts/enoe/extraer.py --plan --desde 2019-1        # trimestres pendientes (JSON)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inegi  # noqa: E402

import pandas as pd  # noqa: E402

VERSION = "2026-11-17"
TRIMESTRAL = inegi.PROCESADO / "trimestral"
SECTORES = {1: "Agropecuario", 2: "Extractiva y electricidad", 3: "Manufactura", 4: "Construcción",
            5: "Comercio", 6: "Restaurantes y alojamiento", 7: "Transportes y comunicaciones",
            8: "Servicios profesionales y financieros", 9: "Servicios sociales", 10: "Servicios diversos",
            11: "Gobierno"}
ENOE_N = [(2020, 3), (2020, 4)] + [(a, t) for a in (2021, 2022) for t in (1, 2, 3, 4)]


def carpeta(anio: int, trim: int) -> Path:
    return TRIMESTRAL / f"{anio}-T{trim}"


def hechos() -> set[tuple[int, int]]:
    if not TRIMESTRAL.exists():
        return set()
    out = set()
    for d in TRIMESTRAL.iterdir():
        if (d / "meta.json").exists():
            a, t = d.name.split("-T")
            out.add((int(a), int(t)))
    return out


def parse_trim(texto: str) -> tuple[int, int]:
    a, t = texto.replace("T", "").replace("t", "").split("-")
    return int(a), int(t)


def elegidas() -> list[int]:
    archivo = inegi.FUENTES / "ciudades.csv"
    return [int(f["cd_a"]) for f in csv.DictReader(archivo.open(encoding="utf-8"))
            if f.get("papel") in ("foco", "comparable")]


def procesa(anio: int, trim: int, zip_path: Path) -> dict:
    t0 = time.time()
    df, info = inegi.lee_sdem(zip_path)
    if info["faltan"]:
        raise KeyError(f"{inegi.etiqueta(anio, trim)}: faltan columnas {info['faltan']}")
    p = inegi.prepara(df, info)
    del df

    nacional = pd.DataFrame([{"dominio": d, "clave": k, **inegi.tasas(p, dom)}
                             for d, k, dom in inegi.dominios_nacionales(p)])
    filas = [{"cd_a": et, **inegi.tasas(p, dom)} for et, dom in inegi.dominios_ciudades(p)]
    ciudades = pd.DataFrame(filas)

    desg = []
    sexo_ok = "sex" in p.columns
    sector_ok = "rama_est2" in p.columns
    c36 = dict(inegi.dominios_ciudades(p, solo=set()))["36 ciudades"]
    grupos = [("Nacional", pd.Series(True, index=p.index)), ("36 ciudades", c36)]
    grupos += [(c, p["cd_a"] == c) for c in elegidas()]
    for c, en_c in grupos:
        if not en_c.any():
            continue
        if sexo_ok:
            for s, nombre in ((1, "Hombres"), (2, "Mujeres")):
                desg.append({"cd_a": c, "corte": "sexo", "valor": nombre,
                             **inegi.tasas(p, en_c & (p["sex"] == s))})
        if sector_ok:
            for k, nombre in SECTORES.items():
                en_k = (p["rama_est2"] == k).astype("int8")
                p["_sector"] = (p["ocup"] * en_k).astype("int8")
                fila = inegi.tasas(p, en_c & (en_k == 1), {"informalidad": ("inf", "ocup")})
                peso, peso_se = inegi._razon(p, "_sector", "ocup", en_c)
                fila["peso_en_ocupacion"] = round(100 * peso, 2) if peso == peso else None
                fila["peso_en_ocupacion_ic90"] = round(100 * 1.645 * peso_se, 2) if peso_se == peso_se else None
                desg.append({"cd_a": c, "corte": "sector", "valor": nombre, **fila})
    desgloses = pd.DataFrame(desg)

    destino = carpeta(anio, trim)
    destino.mkdir(parents=True, exist_ok=True)
    nacional.to_csv(destino / "nacional.csv", index=False)
    ciudades.to_csv(destino / "ciudades.csv", index=False)
    desgloses.to_csv(destino / "desgloses.csv", index=False)
    h = hashlib.sha256()
    with open(zip_path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    meta = {
        "trimestre": inegi.etiqueta(anio, trim), "anio": anio, "trim": trim,
        "encuesta": "ENOE N" if (anio, trim) in ENOE_N else "ENOE",
        "archivo": zip_path.name, "url": inegi.url_trimestre(anio, trim),
        "bytes": zip_path.stat().st_size, "sha256": h.hexdigest(),
        "tabla": info["tabla"], "codificacion": info["codificacion"], "filas": info["filas"],
        "poblacion_15_muestra": int(len(p)), "peso": info["peso"], "estrato": info["estrato"],
        "upm": info["upm"], "ciudades": int(ciudades["cd_a"].map(lambda x: isinstance(x, (int, float))).sum()),
        "entidades": int((nacional["dominio"] == "entidad").sum()),
        "localidad": info.get("localidad"), "tamanos_localidad": int((nacional["dominio"] == "localidad").sum()),
        "segundos": round(time.time() - t0, 1),
        "procesado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "version_script": VERSION,
    }
    inegi.escribe_json(destino / "meta.json", meta)
    return meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trimestres", nargs="*", default=[], help="AAAA-T (p. ej. 2026-2)")
    ap.add_argument("--faltantes", action="store_true")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--desde", default="2019-1")
    ap.add_argument("--hasta", default="")
    ap.add_argument("--max", type=int, default=4)
    ap.add_argument("--borrar-crudo", action="store_true")
    ap.add_argument("--rehacer", action="store_true")
    a = ap.parse_args()

    s = inegi.sesion()
    salida = os.environ.get("GITHUB_OUTPUT")
    if a.faltantes or a.plan:
        hasta = parse_trim(a.hasta) if a.hasta else None
        ya = set() if a.rehacer else hechos()
        candidatos = [t for t in inegi.trimestres(parse_trim(a.desde), hasta) if t not in ya]
        trabajo = []
        for t in candidatos:                      # solo lo que de verdad ya está publicado
            c = inegi.consulta(s, inegi.url_trimestre(*t))
            if inegi.disponible(c):
                trabajo.append(t)
            else:
                inegi.log(f"{inegi.etiqueta(*t)}: todavía no está publicado (HTTP {c.get('estado')}, zip: {c.get('zip')})")
        if a.plan:
            print(json.dumps({"trimestres": [inegi.etiqueta(*t) for t in trabajo]}))
            if salida:
                with open(salida, "a", encoding="utf-8") as f:
                    f.write(f"total={len(trabajo)}\n")
            return 0
    else:
        trabajo = [parse_trim(t) for t in a.trimestres]
        if not a.rehacer:
            trabajo = [t for t in trabajo if t not in hechos()]
    trabajo = trabajo[: a.max]
    inegi.log(f"Por procesar ({len(trabajo)}): {', '.join(inegi.etiqueta(*t) for t in trabajo) or 'nada'}")

    renglones = ["| Trimestre | Encuesta | MB | Descarga (s) | Proceso (s) | Nacional: informalidad | "
                 "36 ciudades: informalidad | Entidades | Estado |",
                 "|---|---|---|---|---|---|---|---|---|"]
    fallas = 0
    for anio, trim in trabajo:
        et = inegi.etiqueta(anio, trim)
        try:
            t0 = time.time()
            z = inegi.descargar(s, anio, trim)
            t_desc = time.time() - t0
            meta = procesa(anio, trim, z)
            ciudades = pd.read_csv(carpeta(anio, trim) / "ciudades.csv", dtype={"cd_a": str})
            nac = pd.read_csv(carpeta(anio, trim) / "nacional.csv", dtype={"clave": str})

            def txt(fila):
                return f"{fila['informalidad'].iloc[0]:.1f} ± {fila['informalidad_ic90'].iloc[0]:.1f}" if len(fila) else "—"
            t_nac = txt(nac[nac["dominio"] == "nacional"])
            t_36 = txt(ciudades[ciudades["cd_a"] == "36 ciudades"])
            renglones.append(f"| {et} | {meta['encuesta']} | {meta['bytes'] / 1e6:,.1f} | {t_desc:,.0f} | "
                             f"{meta['segundos']:,.0f} | {t_nac} | {t_36} | {meta['entidades']} | ok |")
            inegi.log(f"{et}: ok (nacional {t_nac}; 36 ciudades {t_36}; {meta['entidades']} entidades)")
            if a.borrar_crudo:
                z.unlink(missing_ok=True)
        except Exception as e:                                # noqa: BLE001
            fallas += 1
            motivo = " ".join(str(e).split()).replace("|", "/")[:200]
            renglones.append(f"| {et} | — | — | — | — | — | — | — | falla: {type(e).__name__}: {motivo} |")
            inegi.log(f"{et}: FALLA\n{traceback.format_exc()}")
    inegi.resumen_github("### Extracción ENOE\n\n" + "\n".join(renglones) + "\n")
    if salida:
        with open(salida, "a", encoding="utf-8") as f:
            f.write(f"nuevos={len(trabajo) - fallas}\n")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
