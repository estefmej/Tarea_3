"""Funciones compartidas por los scripts del proyecto."""
import copy
import difflib
import json
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]

# La consola de Windows usa cp1252 y falla con caracteres como "→".
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

DEPARTAMENTOS = {
    "01": "Amazonas", "02": "Áncash", "03": "Apurímac", "04": "Arequipa",
    "05": "Ayacucho", "06": "Cajamarca", "07": "Callao", "08": "Cusco",
    "09": "Huancavelica", "10": "Huánuco", "11": "Ica", "12": "Junín",
    "13": "La Libertad", "14": "Lambayeque", "15": "Lima", "16": "Loreto",
    "17": "Madre de Dios", "18": "Moquegua", "19": "Pasco", "20": "Piura",
    "21": "Puno", "22": "San Martín", "23": "Tacna", "24": "Tumbes",
    "25": "Ucayali",
}


def _fusionar(base, extra):
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _fusionar(out[k], v)
        else:
            out[k] = v
    return out


def cargar_config(anio, config_dir=None):
    """config/base.json + config/anios/{anio}.json (el del año sobrescribe)."""
    d = Path(config_dir) if config_dir else RAIZ / "config"
    base = json.loads((d / "base.json").read_text(encoding="utf-8"))
    f = d / "anios" / f"{anio}.json"
    if not f.exists():
        raise SystemExit(f"Falta {f}. Copia config/anios/plantilla.json y complétalo.")
    return _fusionar(base, json.loads(f.read_text(encoding="utf-8")))


def anios_configurados(config_dir=None):
    d = (Path(config_dir) if config_dir else RAIZ / "config") / "anios"
    return sorted(int(p.stem) for p in d.glob("*.json") if p.stem.isdigit())


def leer(ruta):
    ruta = Path(ruta)
    if not ruta.is_absolute():
        ruta = RAIZ / ruta
    ext = ruta.suffix.lower()
    if ext == ".dta":
        return pd.read_stata(ruta, convert_categoricals=False)
    if ext == ".sav":
        import pyreadstat
        df, _ = pyreadstat.read_sav(ruta)
        return df
    if ext in (".csv", ".gz"):
        return pd.read_csv(ruta, encoding="latin-1", low_memory=False)
    raise ValueError(f"Formato no soportado: {ruta}")


def columnas(df, nombres, contexto=""):
    """Devuelve {nombre_config: nombre_real} sin distinguir mayúsculas.
    Si falta alguna, se detiene y sugiere columnas parecidas."""
    cols = {c.upper(): c for c in df.columns}
    nombres = [n for n in nombres if n]
    faltan = [n for n in nombres if n.upper() not in cols]
    if faltan:
        msg = [f"[{contexto}] Variables del config que no están en el archivo:"]
        for f in faltan:
            sug = difflib.get_close_matches(f.upper(), cols.keys(), n=6, cutoff=0.3)
            msg.append(f"  - {f}  (parecidas: {', '.join(sug) or 'ninguna'})")
        msg.append("Revisa el diccionario de la ENAPRES de ese año y corrige config/anios/<año>.json")
        raise SystemExit("\n".join(msg))
    return {n: cols[n.upper()] for n in nombres}


def num(s):
    return pd.to_numeric(s, errors="coerce")
