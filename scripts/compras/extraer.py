"""
Cifra Pública | Folio 005 | Paso 1. De los microdatos de la ENIGH a una tabla por hogar.

Lee, para 2020, 2022 y 2024, las tablas `concentradohogar` (ingreso, factor, diseño muestral)
y `gastoshogar` (cada compra, con su lugar y su forma de pago) y escribe, por año,
`data/processed/compras/hogares_<año>.csv.gz`: un renglón por hogar con

- folio, entidad, est_dis, upm, factor, ing_cor (trimestral), decil nacional de ingreso, urbano
- L00..L18  gasto trimestral por lugar de compra (solo gasto monetario del hogar, tipo G1)
- P00..P10  gasto trimestral por forma de pago principal, solo de las compras con lugar de compra
- F01..F18  gasto trimestral en comida y bebida para la casa por lugar de compra
- T00..T10  gasto en la tiendita (lugar 04) por forma de pago

Uso:
    python scripts/compras/extraer.py RUTA_A_LA_CARPETA_ENIGH

La carpeta debe tener los CSV de datos abiertos del INEGI tal como se descomprimen
(ver scripts/compras/LEEME.md).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[2]
SALIDA = BASE / "data/processed/compras"

RUTAS = {
    2020: ("conjunto_de_datos_gastoshogar_enigh_2020_ns/conjunto_de_datos/conjunto_de_datos_gastoshogar_enigh_2020_ns.csv",
           "conjunto_de_datos_concentradohogar_enigh_2020_ns/conjunto_de_datos/conjunto_de_datos_concentradohogar_enigh_2020_ns.csv"),
    2022: ("conjunto_de_datos_gastoshogar_enigh2022_ns/conjunto_de_datos/conjunto_de_datos_gastoshogar_enigh2022_ns.csv",
           "conjunto_de_datos_concentradohogar_enigh2022_ns/conjunto_de_datos/conjunto_de_datos_concentradohogar_enigh2022_ns.csv"),
    2024: ("conjunto_de_datos_enigh2024_ns_csv/conjunto_de_datos_gastoshogar_enigh2024_ns/conjunto_de_datos/conjunto_de_datos_gastoshogar_enigh2024_ns.csv",
           "conjunto_de_datos_enigh2024_ns_csv/conjunto_de_datos_concentradohogar_enigh2024_ns/conjunto_de_datos/conjunto_de_datos_concentradohogar_enigh2024_ns.csv"),
}


def es_comida_casa(clave: str) -> bool:
    """Alimentos y bebidas sin alcohol para consumir en casa, con criterios equivalentes en las dos claves.

    2020 y 2022 (claves de 4 caracteres): A001–A222, sin A212 (despensa regalada), A213–A214 (alimento
    para animales) ni A198–A202 (comida preparada: pizza, carnitas, pollo rostizado, barbacoa, antojitos).
    2024 (claves de 6 dígitos, CCIF/COICOP 2018): 011, 012 y 013, más la sección 1811 (alimentos que el
    INEGI capta aparte) sin 181111–181112 (despensas regaladas). La comida preparada para llevar de 2024
    está en 11112x y queda fuera, igual que A198–A202.
    """
    c = str(clave).strip()
    if c[:1].isalpha():
        if c[0] != "A":
            return False
        n = int(c[1:])
        return n <= 222 and n not in (212, 213, 214) and not (198 <= n <= 202)
    return c[:3] in ("011", "012", "013") or (c[:4] == "1811" and c not in ("181111", "181112"))


def hogares(ruta_c: Path) -> pd.DataFrame:
    ch = pd.read_csv(ruta_c, usecols=["folioviv", "foliohog", "tam_loc", "est_dis", "upm", "factor", "ing_cor"],
                     dtype={"folioviv": str, "upm": str, "est_dis": str}, encoding="utf-8-sig")
    ch["folioviv"] = ch.folioviv.str.zfill(10)
    ch["ent"] = ch.folioviv.str[:2]
    ch["urb"] = (ch.tam_loc.astype(int) <= 3).astype(int)  # localidades de 2,500 habitantes o más
    # Deciles de hogares por ingreso corriente, como los publica el INEGI: se ordenan por ingreso y se
    # cortan en diez grupos con el mismo número de hogares (expandidos).
    ch = ch.sort_values(["ing_cor", "folioviv", "foliohog"]).reset_index(drop=True)
    acum = ch.factor.cumsum() / ch.factor.sum()
    ch["decil"] = np.clip(np.ceil(acum * 10 - 1e-12), 1, 10).astype(int)
    ch["key"] = ch.folioviv + "_" + ch.foliohog.astype(str)
    return ch


def gastos(ruta_g: Path, llaves: set[str]) -> pd.DataFrame:
    partes = []
    for k in pd.read_csv(ruta_g, usecols=["folioviv", "foliohog", "clave", "tipo_gasto", "forma_pag1", "lugar_comp", "gasto_tri"],
                         dtype=str, encoding="utf-8-sig", chunksize=1_000_000):
        k = k[k.tipo_gasto.str.strip() == "G1"]
        k = k.assign(
            key=k.folioviv.str.zfill(10) + "_" + k.foliohog.str.strip(),
            g=pd.to_numeric(k.gasto_tri, errors="coerce").fillna(0.0),
            lug=pd.to_numeric(k.lugar_comp, errors="coerce").fillna(0).astype(int),
            pag=pd.to_numeric(k.forma_pag1, errors="coerce").fillna(0).astype(int),
            com=k.clave.map(es_comida_casa),
        )
        faltan = set(k.key) - llaves
        if faltan:
            raise SystemExit(f"{len(faltan)} hogares de gastoshogar no están en concentradohogar")
        partes.append(k[["key", "g", "lug", "pag", "com"]])
    return pd.concat(partes, ignore_index=True)


def ancho(df: pd.DataFrame, col: str, pref: str, rango: range) -> pd.DataFrame:
    t = df.pivot_table(index="key", columns=col, values="g", aggfunc="sum", fill_value=0.0)
    t = t.reindex(columns=list(rango), fill_value=0.0)
    t.columns = [f"{pref}{c:02d}" for c in t.columns]
    return t


def main(carpeta: Path) -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    for anio, (rg, rc) in RUTAS.items():
        ch = hogares(carpeta / rc)
        g = gastos(carpeta / rg, set(ch.key))
        compra = g[g.lug > 0]
        t = pd.concat([
            ancho(g, "lug", "L", range(0, 19)),
            ancho(compra, "pag", "P", range(0, 11)),
            ancho(compra[compra.com], "lug", "F", range(1, 19)),
            ancho(compra[compra.lug == 4], "pag", "T", range(0, 11)),
        ], axis=1)
        out = ch.drop(columns="tam_loc").join(t, on="key").fillna(0.0)
        out = out.drop(columns="key")
        num = [c for c in out.columns if c[:1] in "LPFT" and c[1:].isdigit()]
        out[num] = out[num].round(2)
        destino = SALIDA / f"hogares_{anio}.csv.gz"
        out.to_csv(destino, index=False)
        print(f"{anio}: {len(out):,} hogares, {len(g):,} gastos G1 -> {destino.relative_to(BASE)}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]))
