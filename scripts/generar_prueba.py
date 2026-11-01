"""Genera datos FALSOS (2019 y 2025) con la estructura del config para probar el
flujo completo sin descargar nada. Los resultados no significan nada.

  python scripts/generar_prueba.py
  python scripts/procesar_datos.py --config-dir datos/prueba/config
  python scripts/analizar_datos.py --base 2019
(Borra datos/procesados/ antes de usar los datos reales.)
"""
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parents[1]
cfg = json.loads((R / "config/base.json").read_text(encoding="utf-8"))
dst = R / "datos/prueba"
(dst / "config/anios").mkdir(parents=True, exist_ok=True)
shutil.copy(R / "config/base.json", dst / "config/base.json")

for anio, shock in [(2019, 0.0), (2025, -0.06)]:
    rng = np.random.default_rng(anio)
    nc, k = 1500, 8
    n = nc * k
    cong = np.repeat(np.arange(nc), k)
    dep = np.repeat(rng.integers(1, 26, nc), k)
    rural = np.repeat(rng.random(nc) < 0.3, k)
    red = rng.random(n) < np.where(rural, 0.78, 0.95)
    dentro = red & (rng.random(n) < np.where(rural, 0.75, 0.93))
    otra = rng.choice(["6A", "6B", "7"] if anio == 2019 else ["6", "7", "9"], n)
    fuente = np.where(dentro, "1", np.where(red, rng.choice(["2", "3"], n), otra)).astype(object)
    fuente[rng.random(n) < 0.002] = ""
    todos = np.where(red, np.where(rng.random(n) < 0.75, 1, 2), np.nan)
    p24 = np.where(rural, 0.55, 0.62 + shock)
    horas = np.where(red, np.where(rng.random(n) < p24, 24, rng.integers(2, 24, n)), np.nan)
    horas[rng.random(n) < 0.001] = 99
    u = rng.random(n)
    cl = np.where(rural, np.select([u < 0.04, u < 0.11], [0.8, 0.2], 0.0),
                  np.select([u < 0.55 + shock / 2, u < 0.75], [0.8, 0.2], 0.0))
    medido = rng.random(n) > 0.02
    cl = np.where(medido, cl, np.nan)
    ent, dec = np.floor(cl), np.round((cl - np.floor(cl)) * 10)
    fa, co, clo, per = cfg["fuente_agua"], cfg["continuidad"], cfg["cloro"], cfg["personas"]
    df = pd.DataFrame({
        "CONGLOMERADO": cong, "NSELV": np.tile(np.arange(k), nc), "VIVIENDA": np.tile(np.arange(k), nc), "HOGAR": 1,
        cfg["factor_hogar"]: rng.uniform(80, 400, n).round(2),
        "MIEPERHO": rng.integers(1, 8, n),
        cfg["area"]["variable"]: np.where(rural, 2, 1),
        cfg["ubigeo"]: [f"{d:02d}" for d in dep],
        fa["variable"]: fuente, co["todos_los_dias"]: todos, co["horas_dia"]: horas,
        clo["variable_entero"]: ent, clo["variable_decimal"]: dec,
        clo["no_realizada"]: np.where(medido, 0, 1)})
    dup = df.iloc[:2].copy()
    dup[cfg["factor_hogar"]] += 1  # pares con llaves repetidas y datos distintos
    df = pd.concat([df, dup])
    f = dst / f"enapres_falso_{anio}.csv"
    df.to_csv(f, index=False)
    (dst / f"config/anios/{anio}.json").write_text(json.dumps(
        {"anio": anio, "archivo_hogar": str(f.relative_to(R)), "miembros_hogar": "MIEPERHO",
         "personas": {"archivo": None}, "fuente_agua": {"red_vecino": [9]},
         "continuidad": {"todos_los_dias": co["todos_los_dias"], "horas_dia": co["horas_dia"]}}), encoding="utf-8")
    print(f"{anio}: {len(df):,} registros falsos -> {f}")
