"""Cifra Pública | Folio 004 | Amanecer, atardecer y primera luz (crepúsculo civil) con las ecuaciones de la NOAA, vectorizadas.
Precisión esperada: ~1 minuto en latitudes de México."""
import numpy as np
from datetime import date, datetime
from zoneinfo import ZoneInfo

def _ecuaciones(d: date):
    doy = d.timetuple().tm_yday
    n = 366 if (d.year % 4 == 0) else 365
    g = 2*np.pi/n*(doy-1)  # año fraccional a mediodía, suficiente para amanecer
    eqt = 229.18*(0.000075+0.001868*np.cos(g)-0.032077*np.sin(g)-0.014615*np.cos(2*g)-0.040849*np.sin(2*g))
    dec = (0.006918-0.399912*np.cos(g)+0.070257*np.sin(g)-0.006758*np.cos(2*g)+0.000907*np.sin(2*g)
           -0.002697*np.cos(3*g)+0.00148*np.sin(3*g))
    return eqt, dec

def evento_utc_min(d: date, lat, lon, cenit=90.833, salida=True):
    """Minutos UTC desde la medianoche del día d. lat, lon en grados (lon oeste negativa)."""
    eqt, dec = _ecuaciones(d)
    la = np.radians(lat)
    c = np.cos(np.radians(cenit))/(np.cos(la)*np.cos(dec)) - np.tan(la)*np.tan(dec)
    ha = np.degrees(np.arccos(np.clip(c, -1, 1)))
    if not salida: ha = -ha
    return 720 - 4*(lon + ha) - eqt

def offset_horas(zona: str, d: date):
    # offset a las 7:00 locales: lo que importa para la entrada a la escuela
    return datetime(d.year, d.month, d.day, 7, tzinfo=ZoneInfo(zona)).utcoffset().total_seconds()/3600
