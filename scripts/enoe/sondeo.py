"""
Cifra Pública | Folio 003 | Sondeo de los microdatos de la ENOE (INEGI).

Antes de construir la serie, responde:
- ¿El INEGI deja descargar desde GitHub Actions? ¿Qué trimestres hay de 2019 a hoy?
- ¿Los tres formatos de archivo (2019, ENOE Nueva Edición, 2023+) traen lo que necesitamos?
- ¿Mi cálculo de informalidad, desocupación y participación por ciudad reproduce lo que
  publica el INEGI? ¿De qué tamaño es el margen de error por ciudad?

Escribe data/fuentes/enoe/sondeo/ (reporte.md, columnas.json, indicadores_*.csv) y copia el
reporte al resumen de la corrida.

Uso:
    python scripts/enoe/sondeo.py
    python scripts/enoe/sondeo.py --trimestres 2026-2 2021-4 2019-4
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inegi  # noqa: E402

import pandas as pd  # noqa: E402

SALIDA = inegi.FUENTES / "sondeo"


class Reporte:
    def __init__(self):
        self.partes: list[str] = []

    def __call__(self, texto: str = ""):
        self.partes.append(texto)
        print(texto, flush=True)

    def tabla(self, enc, filas):
        self("| " + " | ".join(enc) + " |")
        self("|" + "|".join([" --- "] * len(enc)) + "|")
        for f in filas:
            self("| " + " | ".join(str(x) for x in f) + " |")
        self()

    def guarda(self):
        SALIDA.mkdir(parents=True, exist_ok=True)
        t = "\n".join(self.partes) + "\n"
        (SALIDA / "reporte.md").write_text(t, encoding="utf-8")
        inegi.resumen_github(t)


def lee_ciudades() -> dict[int, dict]:
    archivo = inegi.FUENTES / "ciudades.csv"
    return {int(f["cd_a"]): f for f in csv.DictReader(archivo.open(encoding="utf-8"))}


def lee_publicados() -> dict:
    archivo = inegi.FUENTES / "publicados.csv"
    out = {}
    if archivo.exists():
        for f in csv.DictReader(archivo.open(encoding="utf-8")):
            out[(int(f["anio"]), int(f["trim"]), f["cd_a"], f["indicador"])] = (float(f["valor"]), f["nota"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trimestres", nargs="*", default=[],
                    help="AAAA-T a revisar; por omisión: el más reciente, 2021-4 (ENOE N) y 2019-4")
    ap.add_argument("--conservar", action="store_true", help="no borrar los zips")
    a = ap.parse_args()

    rep = Reporte()
    rep(f"# Sondeo de la ENOE (INEGI) | {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}")
    rep()
    rep(f"Origen: {inegi.URL_BASE}")
    rep()
    codigo, zips = 0, []
    s = inegi.sesion()
    ciudades = lee_ciudades()
    elegidas = {c for c, f in ciudades.items() if f.get("papel") in ("foco", "comparable")}
    publicados = lee_publicados()
    try:
        # 1. Qué hay
        rep("## 1. Qué hay en el INEGI")
        rep()
        filas, disponibles = [], []
        for an, tr in inegi.trimestres((2019, 1)):
            c = inegi.consulta(s, inegi.url_trimestre(an, tr))
            if inegi.disponible(c):
                disponibles.append((an, tr))
            filas.append([inegi.etiqueta(an, tr), inegi.archivo_trimestre(an, tr),
                          c.get("estado") or c.get("error", "—"),
                          "sí" if c.get("zip") else "**no**", c.get("tipo") or "—",
                          f"{c['bytes'] / 1e6:,.1f}" if c.get("bytes") else "—"])
        rep.tabla(["Trimestre", "Archivo", "HTTP", "¿Es zip?", "Tipo", "MB"], filas)
        if not disponibles:
            raise RuntimeError("Ningún trimestre trae un zip. Revisa la tabla: puede ser bloqueo o cambio de direcciones.")
        rep(f"Disponibles: {len(disponibles)} trimestres, de {inegi.etiqueta(*disponibles[0])} "
            f"a {inegi.etiqueta(*disponibles[-1])}. (2020-T2 no existe: fue la ETOE.)")
        rep()

        # 2. Trimestres de prueba
        if a.trimestres:
            prueba = [tuple(map(int, t.split("-"))) for t in a.trimestres]
        else:
            prueba = [disponibles[-1]] + [t for t in ((2021, 4), (2019, 4)) if t in disponibles]
        for an, tr in prueba:
            et = inegi.etiqueta(an, tr)
            rep(f"## 2. {et}")
            rep()
            t0 = time.time()
            z = inegi.descargar(s, an, tr)
            zips.append(z)
            rep(f"- Archivo: `{z.name}`, {z.stat().st_size / 1e6:,.1f} MB, descarga en {time.time() - t0:,.0f} s")
            rep(f"- Contenido: {', '.join(inegi.contenido(z))}")
            df, info = inegi.lee_sdem(z)
            rep(f"- Tabla: `{info['tabla']}` | {info['codificacion']} | separador `{info['separador']}` | "
                f"{info['filas']:,} filas")
            rep(f"- Factor de expansión: `{info['peso']}` | estrato: `{info['estrato']}` | UPM: `{info['upm']}`")
            rep(f"- Faltan: {', '.join(info['faltan']) if info['faltan'] else 'nada'}")
            rep(f"<details><summary>Columnas de la tabla ({len(info['columnas_archivo'])})</summary>")
            rep()
            rep(", ".join(f"`{c}`" for c in info["columnas_archivo"]))
            rep("</details>")
            rep()
            inegi.escribe_json(SALIDA / f"columnas_{an}_t{tr}.json", info)
            if info["faltan"]:
                rep("**No se pueden calcular indicadores: faltan columnas.**")
                rep()
                continue
            ind = inegi.indicadores(df, info, elegidas)
            ind.to_csv(SALIDA / f"indicadores_{an}_t{tr}.csv", index=False)
            filas = []
            for _, r in ind.iterrows():
                cd = r["cd_a"]
                nombre = cd if isinstance(cd, str) else ciudades.get(int(cd), {}).get("ciudad", f"cd_a {cd}")
                clave = cd if isinstance(cd, str) else f"{int(cd):02d}"
                pub = publicados.get((an, tr, clave, "informalidad"))
                dif = f"{r['informalidad'] - pub[0]:+.1f}" if pub else "—"
                ic = lambda k: f" ± {r[k + '_ic90']:.1f}" if r.get(k + "_ic90") is not None else ""  # noqa: E731
                filas.append([nombre, f"{r['muestra']:,}", f"{r['ocupados'] / 1e3:,.0f}",
                              f"{r['informalidad']:.1f}{ic('informalidad')}",
                              f"{pub[0]:.1f}" if pub else "—", dif,
                              f"{r['desocupacion']:.1f}{ic('desocupacion')}",
                              f"{r['participacion']:.1f}{ic('participacion')}",
                              f"{r['sector_informal']:.1f}"])
            rep.tabla(["Ciudad", "Muestra", "Ocupados (miles)", "Informalidad %", "INEGI publicó",
                       "Diferencia", "Desocupación %", "Participación %", "Sector informal %"], filas)
            rep("Los ± son el intervalo de 90% (estratos y UPM del diseño muestral). «INEGI publicó» sale de "
                "`data/fuentes/enoe/publicados.csv`.")
            rep()
        rep("## 3. Qué sigue")
        rep()
        rep("1. Si las diferencias contra lo publicado son de décimas: el método reproduce al INEGI y se puede llenar la serie.")
        rep("2. Si son de puntos: revisar filtros (R_DEF, C_RES, EDA) y la definición de cada tasa antes de seguir.")
        rep("3. Revisar el tamaño de los ± por ciudad: define qué cambios de un trimestre a otro se pueden contar como cambio.")
    except Exception as e:                                # noqa: BLE001
        codigo = 1
        rep()
        rep("## Error")
        rep()
        rep("```")
        rep(f"{type(e).__name__}: {e}")
        rep(traceback.format_exc()[-3000:])
        rep("```")
    finally:
        rep.guarda()
        if not a.conservar:
            for z in zips:
                z.unlink(missing_ok=True)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
