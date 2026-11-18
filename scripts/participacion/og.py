"""Análisis 006 | Toma la imagen para redes (assets/og/participacion.png) con Chrome sin ventana.

Uso: python scripts/participacion/og.py   (requiere playwright y Chrome)
"""
import json
import urllib.parse
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parents[2]
D = json.loads((BASE / "data/processed/participacion/resultados.json").read_text())
ESC = json.loads((BASE / "data/processed/participacion/pagina_datos.json").read_text())["escalera"]


def main():
    v = lambda m: round(100 * m["precision_top10"])  # noqa: E731
    filas = [
        {"n": "Al azar", "v": round(100 * D["tasa_base"]), "c": "#cfced4"},
        {"n": "Solo el estado", "v": v(ESC["solo_estado"]), "c": "#9a9aa3"},
        {"n": "Censo y estado, gradient boosting", "v": v(D["A_municipios"]["boosting"]), "c": "#c06100", "mejor": True},
    ]
    datos = {"titulo": f"De 100 secciones que el modelo señaló, en {filas[-1]['v']} votó menos de la mitad",
             "filas": filas}
    url = (Path(__file__).parent / "og.html").resolve().as_uri() + "#" + urllib.parse.quote(json.dumps(datos))
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
        pg = b.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
        pg.goto(url)
        pg.wait_for_timeout(600)
        salida = BASE / "assets/og/participacion.png"
        pg.screenshot(path=str(salida))
        b.close()
    print(salida)


if __name__ == "__main__":
    main()
