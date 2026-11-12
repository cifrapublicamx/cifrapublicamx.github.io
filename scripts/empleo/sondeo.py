"""
Cifra Pública | Folio 003 | Sondeo del portal de datos abiertos del IMSS.

Antes de llenar la serie completa, revisa un mes y responde:
- ¿El portal deja descargar (desde GitHub Actions)? ¿Por API o por página?
- ¿Qué meses hay de 2019 a hoy?
- ¿Qué columnas trae el archivo, con qué codificación y separador?
- ¿Cómo vienen las claves de entidad y municipio (INEGI o propias del IMSS)?
- ¿Qué códigos de sector tiene el calzado en León?
- ¿Hay alguna señal de los puestos de plataformas digitales?
- ¿Cuadra el total nacional con el boletín del IMSS?

Escribe todo en data/fuentes/empleo/sondeo/ (reporte.md, columnas.json, valores.json,
muestra.csv y los catálogos del IMSS) y copia el reporte al resumen del job.

Uso:
    python scripts/empleo/sondeo.py                 # el mes más reciente
    python scripts/empleo/sondeo.py --mes 2026-08
    python scripts/empleo/sondeo.py --sin-descarga  # solo qué hay en el portal y catálogos
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import imss  # noqa: E402

import pandas as pd  # noqa: E402

SALIDA = imss.FUENTES / "sondeo"
CATALOGOS = SALIDA / "catalogos"
PALABRAS = ["calzado", "cuero", "curtid", "plataforma", "leon", "guanajuato", "municipio"]
PAQUETES_APOYO = [  # diccionario, catálogo y glosario del conjunto de asegurados
    "catálogo-de-archivos-asegurados",
    "catalogo-de-archivos-asegurados",
    "diccionario-de-datos-puestos-de-trabajo-afiliados-y-asegurados-sin-un-empleo-asociado",
    "glosario-datos-abiertos-puestos-de-trabajo-afiliados-y-asegurados-sin-un-empleo-asociado",
    "guia-de-diseno-de-cubo-de-informacion-puestos-de-trabajo-afiliados-y-asegurados-sin-un-empleo-asociado",
]
EXTENSIONES = (".csv", ".xlsx", ".xls", ".pdf", ".txt", ".zip", ".json")
TOPE_CATALOGO = 30 * 1024 * 1024


class Reporte:
    def __init__(self):
        self.partes: list[str] = []

    def __call__(self, texto: str = ""):
        self.partes.append(texto)
        print(texto, flush=True)

    def tabla(self, encabezado: list[str], filas: list[list]):
        self("| " + " | ".join(encabezado) + " |")
        self("|" + "|".join([" --- "] * len(encabezado)) + "|")
        for f in filas:
            self("| " + " | ".join(str(x).replace("|", "\\|") for x in f) + " |")
        self()

    def guarda(self):
        SALIDA.mkdir(parents=True, exist_ok=True)
        texto = "\n".join(self.partes) + "\n"
        (SALIDA / "reporte.md").write_text(texto, encoding="utf-8")
        imss.resumen_github(texto)


def fmt(n) -> str:
    try:
        return f"{float(n):,.0f}"
    except (TypeError, ValueError):
        return str(n)


# ---------------------------------------------------------------- catálogos

def recursos_de_paquete(s, base, slug) -> list[tuple[str, str]]:
    """[(url, nombre)] de los archivos de un conjunto, por API o por página."""
    out = []
    paquete = imss._paquete_api(s, base, slug)
    if paquete:
        for rec in paquete.get("resources") or []:
            url = rec.get("url") or ""
            if url:
                out.append((url, rec.get("name") or Path(url).name))
    if not out:
        try:
            pagina = imss._get(s, f"{base}/dataset/{slug}")
        except Exception:                                  # noqa: BLE001
            return []
        cand = imss.enlaces(pagina.text, pagina.url)
        out = [(u, t) for u, t in cand if u.lower().split("?")[0].endswith(EXTENSIONES)]
        for u, t in cand:
            if "/resource/" in u and not out:
                try:
                    sub = imss._get(s, u)
                except Exception:                          # noqa: BLE001
                    continue
                out += [(u2, t2 or t) for u2, t2 in imss.enlaces(sub.text, sub.url)
                        if u2.lower().split("?")[0].endswith(EXTENSIONES)]
    return out


def paquetes_del_grupo(s, base) -> list[str]:
    try:
        pagina = imss._get(s, f"{base}/group/asegurados")
    except Exception:                                      # noqa: BLE001
        return []
    slugs = []
    for u, _ in imss.enlaces(pagina.text, pagina.url):
        m = re.search(r"/dataset/([^/?#]+)$", u)
        if m and not re.fullmatch(r"asg-?\d{4}", m.group(1)):
            slugs.append(m.group(1))
    return list(dict.fromkeys(slugs))


def baja_catalogos(s, rep: Reporte) -> list[Path]:
    CATALOGOS.mkdir(parents=True, exist_ok=True)
    guardados: list[Path] = []
    for base in imss.bases_vivas():
        slugs = list(dict.fromkeys(PAQUETES_APOYO + paquetes_del_grupo(s, base)))
        for slug in slugs:
            for url, nombre in recursos_de_paquete(s, base, slug):
                nombre_archivo = re.sub(r"[^\w.\-]+", "_", Path(url.split("?")[0]).name)[:120]
                if not nombre_archivo.lower().endswith(EXTENSIONES):
                    continue
                destino = CATALOGOS / nombre_archivo
                if destino.exists():
                    continue
                try:
                    with s.get(imss.a_http(url), stream=True, timeout=(30, 120)) as r:
                        r.raise_for_status()
                        total, datos = 0, io.BytesIO()
                        for b in r.iter_content(1 << 20):
                            total += len(b)
                            if total > TOPE_CATALOGO:
                                raise ValueError("más de 30 MB, no se guarda")
                            datos.write(b)
                    destino.write_bytes(datos.getvalue())
                    guardados.append(destino)
                except Exception as e:                     # noqa: BLE001
                    rep(f"- No se pudo bajar `{nombre_archivo}` ({slug}): {e}")
        if guardados:
            break
    return guardados


def texto_de(ruta: Path) -> str:
    suf = ruta.suffix.lower()
    try:
        if suf in (".csv", ".txt", ".json"):
            crudo = ruta.read_bytes()
            try:
                return crudo.decode("utf-8-sig")
            except UnicodeDecodeError:
                return crudo.decode("latin-1")
        if suf == ".xlsx":
            from openpyxl import load_workbook
            wb = load_workbook(ruta, read_only=True, data_only=True)
            lineas = []
            for ws in wb.worksheets:
                for fila in ws.iter_rows(values_only=True):
                    celdas = [str(c) for c in fila if c is not None]
                    if celdas:
                        lineas.append(f"[{ws.title}] " + " | ".join(celdas))
            return "\n".join(lineas)
        if suf == ".pdf":
            from pypdf import PdfReader
            return "\n".join((p.extract_text() or "") for p in PdfReader(str(ruta)).pages)
    except Exception as e:                                 # noqa: BLE001
        return f"(no se pudo leer: {e})"
    return ""


def sin_acentos(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()


# ---------------------------------------------------------------- análisis del archivo

def analiza(ruta: Path, fmt_: imss.Formato, rep: Reporte, mes: str):
    dims = [c for c in imss.DIMENSIONES if c in fmt_.columnas]
    meds = [c for c in imss.MEDIDAS if c in fmt_.columnas]
    nuevas = [c for c in fmt_.columnas if c not in imss.DIMENSIONES + imss.MEDIDAS]
    # Las columnas nuevas se leen como texto para ver qué traen.
    usar = dims + meds + nuevas
    conteo_filas = 0
    medida_ref = "ta" if "ta" in meds else (meds[0] if meds else None)
    valores: dict[str, dict] = {c: defaultdict(lambda: [0, 0.0]) for c in dims + nuevas}
    sumas = defaultdict(float)
    ent_mun = defaultdict(float)
    leon_cand = []           # se llena después de conocer Guanajuato
    por_ent_mun_s2 = defaultdict(float)
    por_ent_mun_s4 = defaultdict(float)
    por_ent_mun_tam = defaultdict(float)
    for parte in imss.lee_por_partes(ruta, fmt_, usar):
        conteo_filas += len(parte)
        ref = parte[medida_ref] if medida_ref else pd.Series(1.0, index=parte.index)
        for c in meds:
            sumas[c] += float(parte[c].sum())
        for c in dims + nuevas:
            g = pd.DataFrame({"v": parte[c], "r": ref}).groupby("v", sort=False)["r"].agg(["size", "sum"])
            for v, (n, t) in g.iterrows():
                acc = valores[c][v]
                acc[0] += int(n); acc[1] += float(t)
        if {"cve_entidad", "cve_municipio"} <= set(parte.columns):
            for (e, m), t in pd.DataFrame({"e": parte["cve_entidad"], "m": parte["cve_municipio"],
                                           "r": ref}).groupby(["e", "m"])["r"].sum().items():
                ent_mun[(e, m)] += float(t)
            for col, destino in (("sector_economico_2", por_ent_mun_s2),
                                 ("sector_economico_4", por_ent_mun_s4),
                                 ("tamano_patron", por_ent_mun_tam)):
                if col in parte.columns:
                    for k, t in pd.DataFrame({"e": parte["cve_entidad"], "m": parte["cve_municipio"],
                                              "s": parte[col], "r": ref}).groupby(
                                                  ["e", "m", "s"])["r"].sum().items():
                        destino[k] += float(t)
    return dict(conteo_filas=conteo_filas, medida_ref=medida_ref, valores=valores, sumas=sumas,
                ent_mun=ent_mun, s2=por_ent_mun_s2, s4=por_ent_mun_s4, tam=por_ent_mun_tam,
                nuevas=nuevas, dims=dims, meds=meds)


def es_numerica(serie_valores) -> bool:
    vals = [v for v in serie_valores if v != ""]
    return bool(vals) and all(re.fullmatch(r"\d+", v) for v in vals)


def norm(c: str) -> str:
    c = (c or "").strip()
    return str(int(c)) if c.isdigit() else c.upper()


# ---------------------------------------------------------------- principal

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mes", default="", help="AAAA-MM; vacío = el más reciente")
    ap.add_argument("--desde", type=int, default=2019, help="primer año a listar")
    ap.add_argument("--sin-descarga", action="store_true")
    ap.add_argument("--conservar", action="store_true", help="no borrar el CSV crudo al final")
    a = ap.parse_args()

    rep = Reporte()
    hoy = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    rep(f"# Sondeo del portal de datos abiertos del IMSS | {hoy}")
    rep()
    rep(f"Espejos probados: {', '.join(imss.BASES)}")
    rep()
    s = imss.sesion()
    codigo = 0
    ruta = None
    try:
        # 1. Qué hay
        bit: list[str] = []
        anios = list(range(a.desde, imss.anio_actual() + 1))
        t0 = time.time()
        recursos = imss.descubrir(anios, s=s, bitacora=bit)
        rep("## 1. Qué hay en el portal")
        rep()
        por_anio = defaultdict(list)
        for mes, r in recursos.items():
            por_anio[mes[:4]].append(r)
        filas = []
        for anio in map(str, anios):
            rs = por_anio.get(anio, [])
            if rs:
                meses = [r.mes[5:] for r in rs]
                origenes = sorted({r.origen for r in rs})
                espejo = sorted({imss.urlsplit(r.url).hostname for r in rs})
                filas.append([anio, len(rs), f"{meses[0]} a {meses[-1]}", ", ".join(origenes), ", ".join(espejo)])
            else:
                filas.append([anio, 0, "—", "—", "—"])
        rep.tabla(["Año", "Meses", "De / a", "Cómo se encontró", "Servidor"], filas)
        faltan = [m for m in imss.rango_meses(f"{a.desde}-01", max(recursos) if recursos else f"{a.desde}-01")
                  if m not in recursos]
        rep(f"Meses que faltan dentro del rango: {', '.join(faltan) if faltan else 'ninguno'}.")
        rep(f"Búsqueda: {time.time() - t0:.0f} s.")
        rep()
        rep("<details><summary>Bitácora de la búsqueda</summary>")
        rep()
        rep("```")
        for linea in bit:
            rep(linea)
        rep("```")
        rep("</details>")
        rep()
        imss.escribe_json(SALIDA / "recursos.json", {m: imss.recurso_a_dict(r) for m, r in recursos.items()})
        if not recursos:
            raise RuntimeError("No se encontró ningún archivo mensual. Revisa la bitácora: "
                               "puede ser bloqueo del portal a GitHub o cambio de direcciones.")

        # 2. Catálogos
        rep("## 2. Catálogos y diccionario del IMSS")
        rep()
        catalogos = baja_catalogos(s, rep)
        if catalogos:
            rep(f"Guardados en `data/fuentes/empleo/sondeo/catalogos/`: "
                + ", ".join(f"`{p.name}`" for p in catalogos))
        else:
            rep("No se pudo bajar ningún catálogo.")
        rep()
        coincidencias = defaultdict(list)
        for p in sorted(CATALOGOS.glob("*")):
            for linea in texto_de(p).splitlines():
                l = sin_acentos(linea)
                for pal in PALABRAS:
                    if pal in l and len(coincidencias[pal]) < 40:
                        coincidencias[pal].append(f"{p.name}: {linea.strip()[:220]}")
        for pal in PALABRAS:
            if coincidencias[pal]:
                rep(f"<details><summary>«{pal}» en los catálogos ({len(coincidencias[pal])})</summary>")
                rep()
                rep("```")
                for c in coincidencias[pal]:
                    rep(c)
                rep("```")
                rep("</details>")
                rep()

        if a.sin_descarga:
            rep("Sin descarga del archivo mensual (--sin-descarga).")
            return 0

        # 3. Descarga
        mes = a.mes or max(recursos)
        if mes not in recursos:
            raise RuntimeError(f"El mes {mes} no está en el portal. Hay: {', '.join(recursos)}")
        rec = recursos[mes]
        rep(f"## 3. Archivo revisado: {mes}")
        rep()
        t0 = time.time()
        ruta = imss.descargar(rec, s=s)
        segundos = time.time() - t0
        tam = ruta.stat().st_size
        fmt_ = imss.detecta_formato(ruta)
        rep(f"- URL: {rec.url}")
        rep(f"- Tamaño: {tam:,} bytes ({tam / 1e6:,.0f} MB); descarga en {segundos:,.0f} s "
            f"({tam / 1e6 / max(segundos, 1):,.1f} MB/s)")
        rep(f"- SHA-256: `{imss.sha256(ruta)}`")
        rep(f"- Codificación: {fmt_.codificacion} | separador: `{fmt_.separador}`")
        rep()

        # 4. Columnas
        rep("## 4. Columnas")
        rep()
        esperadas = imss.DIMENSIONES + imss.MEDIDAS
        rep.tabla(["Cruda", "Normalizada", "¿Esperada?"],
                  [[c, n, "sí" if n in esperadas else "**nueva**"] for c, n in zip(fmt_.columnas_crudas, fmt_.columnas)])
        faltan_req = [c for c in imss.REQUERIDAS if c not in fmt_.columnas]
        faltan_esp = [c for c in esperadas if c not in fmt_.columnas]
        rep(f"Faltan de las requeridas para extraer: {', '.join(faltan_req) if faltan_req else 'ninguna'}.")
        rep(f"Faltan de las esperadas: {', '.join(faltan_esp) if faltan_esp else 'ninguna'}.")
        rep()
        imss.escribe_json(SALIDA / "columnas.json", {"mes": mes, "codificacion": fmt_.codificacion,
                                                     "separador": fmt_.separador,
                                                     "crudas": fmt_.columnas_crudas,
                                                     "normalizadas": fmt_.columnas,
                                                     "faltan_requeridas": faltan_req})
        # muestra legible (UTF-8)
        with open(ruta, "r", encoding=fmt_.codificacion, newline="") as f:
            muestra = [next(f, "") for _ in range(2001)]
        (SALIDA / "muestra.csv").write_text("".join(muestra), encoding="utf-8")

        # 5. Valores
        t0 = time.time()
        res = analiza(ruta, fmt_, rep, mes)
        ref = res["medida_ref"]
        rep(f"## 5. Valores ({res['conteo_filas']:,} filas; peso = `{ref}`; {time.time() - t0:,.0f} s)")
        rep()
        rep.tabla(["Medida", "Suma"], [[c, fmt(res["sumas"][c])] for c in res["meds"]])
        valores_json = {}
        for c in res["dims"] + res["nuevas"]:
            vals = res["valores"][c]
            orden = sorted(vals.items(), key=lambda kv: -kv[1][1])
            vacios = vals.get("", [0, 0.0])
            ejemplo = [v for v, _ in orden[:8]]
            valores_json[c] = {"distintos": len(vals), "vacios_filas": vacios[0], "vacios_peso": vacios[1],
                               "numerica": es_numerica(vals.keys()),
                               "top": [[v, n, t] for v, (n, t) in orden[:60]]}
            rep(f"<details><summary><code>{c}</code>: {len(vals):,} valores distintos; "
                f"vacíos en {vacios[0]:,} filas ({fmt(vacios[1])} de {ref}); "
                f"{'solo dígitos' if es_numerica(vals.keys()) else 'con letras'}; p. ej. {', '.join(map(repr, ejemplo))}"
                f"</summary>")
            rep()
            rep.tabla(["Valor", "Filas", ref], [[repr(v), f"{n:,}", fmt(t)] for v, (n, t) in orden[:30]])
            rep("</details>")
            rep()
        imss.escribe_json(SALIDA / "valores.json", valores_json)

        # 6. Control nacional
        rep("## 6. Control nacional")
        rep()
        boletines = {}
        archivo_b = imss.FUENTES / "boletines.csv"
        if archivo_b.exists():
            for fila in csv.DictReader(archivo_b.open(encoding="utf-8")):
                boletines[fila["fecha_corte"][:7]] = fila
        total = res["sumas"].get("ta", 0)
        sin_mun = sum(t for (e, m), t in res["ent_mun"].items() if m == "")
        rep(f"- Suma de `ta` en el archivo: {fmt(total)} (sin municipio: {fmt(sin_mun)})")
        if mes in boletines:
            b = float(boletines[mes]["puestos"])
            rep(f"- Boletín del IMSS ({boletines[mes]['fecha_corte']}): {fmt(b)} | diferencia "
                f"{fmt(total - b)} ({(total - b) / b * 100:+.2f}%) | fuente: {boletines[mes]['fuente']}")
        else:
            rep("- No hay cifra de boletín cargada para este mes en `data/fuentes/empleo/boletines.csv`.")
        rep()

        # 7. Entidades y municipios
        por_ent = defaultdict(float)
        for (e, m), t in res["ent_mun"].items():
            por_ent[e] += t
        rep("## 7. Entidades (clave tal como viene)")
        rep()
        rep.tabla(["cve_entidad", ref], [[repr(e), fmt(t)] for e, t in sorted(por_ent.items(), key=lambda kv: -kv[1])[:40]])
        mun_vals = res["valores"].get("cve_municipio", {})
        numerica = es_numerica(mun_vals.keys())
        rep(f"Las claves de municipio {'son solo dígitos: pueden ser las del INEGI' if numerica else 'traen letras: son propias del IMSS y hace falta la tabla de equivalencias'}.")
        rep()

        # Guanajuato: entidad '11' si las claves son numéricas
        gto = [e for e in por_ent if norm(e) == "11"]
        if gto:
            e_gto = gto[0]
            muns = sorted(((m, t) for (e, m), t in res["ent_mun"].items() if e == e_gto), key=lambda kv: -kv[1])
            rep(f"## 8. Municipios de la entidad {e_gto!r} (Guanajuato si la clave es del INEGI)")
            rep()
            rep.tabla(["cve_municipio", ref], [[repr(m), fmt(t)] for m, t in muns[:50]])
            if muns:
                e_leon, m_leon = e_gto, muns[0][0]
                rep(f"El municipio más grande de la entidad es {m_leon!r}: se toma como León para lo que sigue "
                    f"({'coincide con la clave INEGI 020' if norm(m_leon) == '20' else 'confirmar que sea León'}).")
                rep()
                for titulo, dic, n in (("Grupos (sector_economico_2)", res["s2"], 40),
                                       ("Fracciones (sector_economico_4)", res["s4"], 60),
                                       ("Tamaño de patrón", res["tam"], 20)):
                    filas = sorted(((s_, t) for (e, m, s_), t in dic.items() if e == e_leon and m == m_leon),
                                   key=lambda kv: -kv[1])
                    rep(f"<details><summary>León | {titulo}</summary>")
                    rep()
                    rep.tabla(["Clave", ref], [[repr(s_), fmt(t)] for s_, t in filas[:n]])
                    rep("</details>")
                    rep()
        else:
            rep("## 8. Guanajuato")
            rep()
            rep("No hay una entidad con clave 11: las claves no son las del INEGI. "
                "Usa el catálogo (sección 2) para ubicar Guanajuato y León.")
            rep()

        # 9. Municipios del archivo de configuración
        conf = imss.FUENTES / "municipios.csv"
        if conf.exists():
            rep("## 9. Municipios elegidos (data/fuentes/empleo/municipios.csv)")
            rep()
            filas = []
            for fila in csv.DictReader(conf.open(encoding="utf-8")):
                e_i, m_i = fila.get("cve_entidad_imss", ""), fila.get("cve_municipio_imss", "")
                if e_i and m_i:
                    clave = (norm(e_i), norm(m_i)); via = "clave IMSS"
                elif numerica:
                    clave = (norm(fila["clave_inegi"][:2]), norm(fila["clave_inegi"][2:])); via = "clave INEGI"
                else:
                    clave = None; via = "sin clave IMSS"
                t = sum(v for (e, m), v in res["ent_mun"].items() if clave and (norm(e), norm(m)) == clave)
                filas.append([fila["municipio"], fila["clave_inegi"], via, fmt(t) if clave else "—"])
            rep.tabla(["Municipio", "INEGI", "Cómo se buscó", ref], filas)

        # 10. Plataformas
        rep("## 10. Señales de plataformas digitales")
        rep()
        sospechosas = [c for c in fmt_.columnas if any(p in c for p in ("plataforma", "modalidad", "tipo"))]
        rep(f"- Columnas con «plataforma», «modalidad» o «tipo» en el nombre: {', '.join(sospechosas) if sospechosas else 'ninguna'}.")
        if res["nuevas"]:
            rep(f"- Columnas nuevas (no están en el diccionario que conocíamos): {', '.join(res['nuevas'])}. Revisar sus valores en la sección 5.")
        for c in ("sector_economico_1", "sector_economico_2", "sector_economico_4", "tamano_patron"):
            v = res["valores"].get(c, {}).get("")
            if v and v[1]:
                rep(f"- Hay {fmt(v[1])} de `{ref}` con `{c}` vacío.")
        mayores = sorted(res["ent_mun"].items(), key=lambda kv: -kv[1])[:10]
        rep("- Los 10 pares entidad-municipio con más puestos (un salto raro aquí delata registros masivos):")
        rep()
        rep.tabla(["cve_entidad", "cve_municipio", ref], [[repr(e), repr(m), fmt(t)] for (e, m), t in mayores])

        rep("## 11. Qué sigue")
        rep()
        rep("1. Si faltan columnas requeridas o cambiaron de nombre: ajustar `imss.py` antes del llenado.")
        rep("2. Si las claves de municipio no son del INEGI: llenar `cve_entidad_imss` y `cve_municipio_imss` "
            "en `data/fuentes/empleo/municipios.csv` con el catálogo.")
        rep("3. Anotar en `data/fuentes/empleo/sectores.csv` los grupos o fracciones del calzado (sección 8) "
            "para seguirlos en todo el país.")
        rep("4. Correr «Empleo IMSS | llenado» desde 2019-01.")
    except Exception as e:                                 # noqa: BLE001
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
        if ruta is not None and not a.conservar:
            ruta.unlink(missing_ok=True)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
