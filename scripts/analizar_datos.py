"""3) INDICADORES Y ANÁLISIS

- Estima cada indicador (% de población) por año, nacional, urbano/rural,
  departamento y departamento x área, con error estándar (linealización de
  Taylor con estratos y conglomerados), CV y marca de confiabilidad (CV > 15% =
  referencial, criterio MVCS/INEI).
- ODS 6.1.1 (metodología MVCS): mínimo de tres criterios —acceso a red pública
  (códigos 1, 2 y 3), continuidad 24 h y cloro adecuado— calculado en urbano y
  en rural; el total es su promedio ponderado por población. El acceso dentro
  de la vivienda (acc_en_vivienda) se reporta solo como indicador descriptivo.
  Se guarda también el mínimo directo sobre el total (ods611_minimo_directo)
  para ver cuál reproduce mejor la cifra del MVCS. También el indicador conjunto
  y la sensibilidad con 20 h y 12 h de continuidad.
- Compara el año base (2019) con el último año: diferencia en pp, error estándar
  de la diferencia y significancia al 95%.
- Valida contra cifras oficiales (references/valores_referencia.csv).
- Genera un borrador de hallazgos con cifras y los datos para el dashboard.

Uso:
  python scripts/analizar_datos.py --base 2019
"""
import argparse
import glob
import json

import numpy as np
import pandas as pd

from comun import RAIZ

PROC = RAIZ / "datos" / "procesados"
WEB = RAIZ / "web" / "data"
CRITERIOS = {"red_publica": "Acceso a red pública",
             "disp_24h": "Disponible 24 h todos los días",
             "cal_cloro_adecuado": "Cloro residual adecuado"}
SIMPLES = [("red_publica", "uno"), ("acc_en_vivienda", "uno"), ("disp_24h", "uno"),
           ("disp_20h", "uno"), ("disp_12h", "uno"), ("cal_cloro_adecuado", "uno"),
           ("ods611_conjunto", "uno"), ("cloro_adecuado_en_red", "den_red_medido"),
           ("cloro_inadecuado_en_red", "den_red_medido"), ("sin_cloro_en_red", "den_red_medido"),
           ("red_vecino", "uno"), ("brecha_disp24_menos_cloro", "uno")]


def razon(d, y, x):
    if x != "uno":
        d = d[d[x] > 0]
        xs = d[x]
    else:
        xs = pd.Series(1.0, index=d.index)
    sx = (d["peso"] * xs).sum()
    if len(d) == 0 or sx == 0:
        return np.nan, np.nan, 0
    r = (d["peso"] * d[y]).sum() / sx
    z = d["peso"] * (d[y] - r * xs) / sx
    t = z.groupby([d["estrato"], d["psu"]]).sum().reset_index(name="z")
    var = 0.0
    for _, g in t.groupby("estrato"):
        n = len(g)
        if n > 1:
            var += n / (n - 1) * ((g["z"] - g["z"].mean()) ** 2).sum()
    return r, np.sqrt(var), len(d)


def dominios(b):
    yield "Nacional", "Total", b
    for a, g in b.groupby("area"):
        yield "Nacional", a, g
    for dep, g in b.groupby("departamento"):
        yield dep, "Total", g
        for a, ga in g.groupby("area"):
            yield dep, a, ga


# Indicadores en % de HOGARES (peso = factor del hogar), para replicar al INEI
HOGARES = [("red_publica", "uno", "red_publica_hogares"),
           ("cloro_adecuado_hogar", "den_medido_hogar", "cloro_adecuado_hogares")]


def estimar_hogares(h, anio):
    filas = []
    for dom, area, g in dominios(h):
        for y, x, nombre in HOGARES:
            r, se, n = razon(g, y, x)
            filas.append(dict(anio=anio, dominio=dom, area=area, indicador=nombre,
                              valor=100 * r, ee=100 * se, n_muestra=n))
    res = pd.DataFrame(filas)
    res["cv"] = res["ee"] / res["valor"] * 100
    res["confiabilidad"] = np.where(res["cv"] > 15, "referencial (CV>15%)", "aceptable")
    return res


def estimar(b, anio):
    # Distancia entre continuidad y cloro dentro de la misma muestra: se estima como
    # la media de la diferencia por persona, así su error estándar ya incluye la
    # covarianza entre ambos criterios.
    b = b.assign(brecha_disp24_menos_cloro=b["disp_24h"] - b["cal_cloro_adecuado"])
    filas, mins = [], {}
    for dom, area, g in dominios(b):
        est = {}
        for y, x in SIMPLES:
            if y not in g:
                continue
            r, se, n = razon(g, y, x)
            est[y] = (100 * r, 100 * se)
            filas.append(dict(anio=anio, dominio=dom, area=area, indicador=y,
                              valor=100 * r, ee=100 * se, n_muestra=n))
        for sufijo, disp in [("", "disp_24h"), ("_20h", "disp_20h"), ("_12h", "disp_12h")]:
            if disp not in est:
                continue
            crit = {"red_publica": est["red_publica"], disp: est[disp],
                    "cal_cloro_adecuado": est["cal_cloro_adecuado"]}
            lim = min(crit, key=lambda k: crit[k][0])
            mins[(dom, area, sufijo)] = (crit[lim][0], crit[lim][1], lim, g["peso"].sum(), len(g))
    # ODS 6.1.1 (método JMP): mínimo de los 3 criterios en urbano y en rural por
    # separado; el total es el promedio ponderado por población de ambos.
    for (dom, area, suf), (val, se, lim, pob, n) in mins.items():
        if area != "Total":
            filas.append(dict(anio=anio, dominio=dom, area=area, indicador=f"ods611_minimo{suf}",
                              valor=val, ee=se, n_muestra=n, criterio_limitante=lim))
            continue
        filas.append(dict(anio=anio, dominio=dom, area=area, indicador=f"ods611_minimo_directo{suf}",
                          valor=val, ee=se, n_muestra=n, criterio_limitante=lim))
        partes = [mins.get((dom, a, suf)) for a in ("Urbano", "Rural")]
        partes = [x for x in partes if x is not None]
        tot = sum(x[3] for x in partes)
        v = sum(x[0] * x[3] for x in partes) / tot
        e = np.sqrt(sum((x[3] / tot) ** 2 * x[1] ** 2 for x in partes))
        lims = {x[2] for x in partes}
        filas.append(dict(anio=anio, dominio=dom, area=area, indicador=f"ods611_minimo{suf}",
                          valor=v, ee=e, n_muestra=n,
                          criterio_limitante=lims.pop() if len(lims) == 1 else "distinto en urbano y rural"))
    res = pd.DataFrame(filas)
    res["cv"] = res["ee"] / res["valor"] * 100
    res["confiabilidad"] = np.where(res["cv"] > 15, "referencial (CV>15%)", "aceptable")
    res["significativo_vs_0"] = res["valor"].abs() > 1.96 * res["ee"]  # útil para las brechas
    return res


def descomponer(a0, a1, indicador="red_publica", area="Urbano"):
    """Reparte el cambio nacional del indicador en el área (area=None: todas) entre departamentos:
    efecto tasa = peso poblacional medio x cambio de la tasa del departamento;
    efecto composición = tasa media x cambio del peso poblacional."""
    filas = []
    for anio in (a0, a1):
        b = pd.read_csv(PROC / f"base_{anio}.csv.gz", usecols=["departamento", "area", "peso", indicador])
        if area:
            b = b[b["area"] == area]
        g = b.groupby("departamento").apply(
            lambda d: pd.Series({"pob": d["peso"].sum(), "tasa": 100 * (d["peso"] * d[indicador]).sum() / d["peso"].sum()}),
            include_groups=False)
        g["peso_pob"] = g["pob"] / g["pob"].sum()
        filas.append(g.add_suffix(f"_{anio}"))
    d = pd.concat(filas, axis=1)
    d["efecto_tasa_pp"] = (d[f"peso_pob_{a0}"] + d[f"peso_pob_{a1}"]) / 2 * (d[f"tasa_{a1}"] - d[f"tasa_{a0}"])
    d["efecto_composicion_pp"] = (d[f"tasa_{a0}"] + d[f"tasa_{a1}"]) / 2 * (d[f"peso_pob_{a1}"] - d[f"peso_pob_{a0}"])
    d["contribucion_total_pp"] = d["efecto_tasa_pp"] + d["efecto_composicion_pp"]
    d["pct_del_cambio_por_tasa"] = 100 * d["efecto_tasa_pp"] / d["efecto_tasa_pp"].sum()
    return d.reset_index().sort_values("efecto_tasa_pp")


def robustez_codigo9(anio):
    """6.1.1 y sus criterios sin contar (definición del proyecto) y contando el
    código 9 "red pública casa del vecino" como red. Metodología MVCS: mínimo por área;
    el total es el promedio de urbano y rural ponderado por población."""
    b = pd.read_csv(PROC / f"base_{anio}.csv.gz", low_memory=False)
    variantes = {"sin código 9 (definición del proyecto)": ("red_publica", "cal_cloro_adecuado"),
                 "contando código 9 como red": ("red_publica_con_vecino", "cal_cloro_adecuado_con_vecino")}
    filas = []
    for nombre, (red, cloro) in variantes.items():
        mins = {}
        for area in ("Urbano", "Rural"):
            g = b[b["area"] == area]
            est = {k: razon(g, v, "uno") for k, v in
                   [("red_publica", red), ("disp_24h", "disp_24h"), ("cal_cloro_adecuado", cloro)]}
            lim = min(est, key=lambda k: est[k][0])
            mins[area] = (est[lim][0], est[lim][1], g["peso"].sum())
            for k, (r, se, n) in est.items():
                filas.append(dict(anio=anio, variante=nombre, area=area, indicador=k, valor=100 * r, ee=100 * se))
            filas.append(dict(anio=anio, variante=nombre, area=area, indicador="ods611_minimo",
                              valor=100 * est[lim][0], ee=100 * est[lim][1], criterio_limitante=lim))
        tot = sum(m[2] for m in mins.values())
        filas.append(dict(anio=anio, variante=nombre, area="Total", indicador="ods611_minimo",
                          valor=100 * sum(m[0] * m[2] for m in mins.values()) / tot,
                          ee=100 * np.sqrt(sum((m[2] / tot) ** 2 * m[1] ** 2 for m in mins.values()))))
    out = pd.DataFrame(filas)
    out["cv"] = out["ee"] / out["valor"] * 100
    return out


def poblacion_sin_agua_segura(res, anios):
    """Personas sin agua gestionada de forma segura = (100 - 6.1.1) % x población.
    La población expandida está calibrada a las proyecciones del INEI, por lo que se
    trata como fija: error estándar = población x error estándar del 6.1.1."""
    filas = []
    for anio in anios:
        b = pd.read_csv(PROC / f"base_{anio}.csv.gz", usecols=["area", "peso"])
        pob = {"Total": b["peso"].sum(), **b.groupby("area")["peso"].sum().to_dict()}
        for area, n in pob.items():
            x = res[(res.anio == anio) & (res.dominio == "Nacional") & (res.area == area)
                    & (res.indicador == "ods611_minimo")].iloc[0]
            filas.append(dict(anio=anio, area=area, poblacion_millones=n / 1e6,
                              ods611=x.valor, sin_agua_segura_pct=100 - x.valor,
                              sin_agua_segura_millones=(100 - x.valor) / 100 * n / 1e6,
                              ee_millones=x.ee / 100 * n / 1e6))
    out = pd.DataFrame(filas)
    # diferencia entre años (muestras independientes)
    a0, a1 = anios
    m = out[out.anio == a0].merge(out[out.anio == a1], on="area", suffixes=(f"_{a0}", f"_{a1}"))
    m["dif_millones"] = m[f"sin_agua_segura_millones_{a1}"] - m[f"sin_agua_segura_millones_{a0}"]
    m["ee_dif_millones"] = np.sqrt(m[f"ee_millones_{a0}"] ** 2 + m[f"ee_millones_{a1}"] ** 2)
    m["significativo_95"] = m["dif_millones"].abs() > 1.96 * m["ee_dif_millones"]
    return m


def comparar(res, a0, a1):
    k = ["dominio", "area", "indicador"]
    m = res[res.anio == a0].merge(res[res.anio == a1], on=k, suffixes=(f"_{a0}", f"_{a1}"))
    m["dif_pp"] = m[f"valor_{a1}"] - m[f"valor_{a0}"]
    m["ee_dif"] = np.sqrt(m[f"ee_{a0}"] ** 2 + m[f"ee_{a1}"] ** 2)
    m["significativo_95"] = (m["dif_pp"].abs() > 1.96 * m["ee_dif"])
    return m


def validar(res):
    f = RAIZ / "references" / "valores_referencia.csv"
    ref = pd.read_csv(f, comment="#")
    m = ref.merge(res[["anio", "dominio", "area", "indicador", "valor", "ee"]],
                  on=["anio", "dominio", "area", "indicador"], how="left")
    m["dif_pp"] = m["valor"] - m["valor_ref"]
    m["estado"] = np.select(
        [m["valor"].isna() & (m["tipo"] == "replica"), m["valor"].isna(), (m["tipo"] == "replica") & (m["dif_pp"].abs() <= m["tolerancia_pp"]),
         m["tipo"] == "replica"],
        ["sin estimación (año no procesado)", "contraste (sin estimación comparable)", "OK", "REVISAR"], default="contraste")
    return m


def borrador_hallazgos(res, comp, val, a0, a1):
    def v(dom, area, ind, anio):
        s = res[(res.dominio == dom) & (res.area == area) & (res.indicador == ind) & (res.anio == anio)]
        return s.iloc[0] if len(s) else None

    L = [f"# Borrador cuantitativo de hallazgos ({a0} vs {a1})",
         "", "Generado automáticamente. Verifica cada cifra e interprétala antes de usarla.", ""]
    L.append("## 1. ODS 6.1.1 (aproximación con ENAPRES)")
    for area in ["Total", "Urbano", "Rural"]:
        x0, x1 = v("Nacional", area, "ods611_minimo", a0), v("Nacional", area, "ods611_minimo", a1)
        c = comp[(comp.dominio == "Nacional") & (comp.area == area) & (comp.indicador == "ods611_minimo")]
        if x0 is not None and x1 is not None and len(c):
            c = c.iloc[0]
            L.append(f"- {area}: {x0.valor:.1f}% ({a0}) → {x1.valor:.1f}% ({a1}); "
                     f"{c.dif_pp:+.1f} pp ({'significativo' if c.significativo_95 else 'no significativo'} al 95%). "
                     f"Limitante {a0}: {CRITERIOS.get(x0.criterio_limitante, x0.criterio_limitante)}; "
                     f"{a1}: {CRITERIOS.get(x1.criterio_limitante, x1.criterio_limitante)}.")
    L += ["", "## 2. Los tres criterios por área"]
    for area in ["Urbano", "Rural"]:
        partes = []
        for ind, nom in CRITERIOS.items():
            x0, x1 = v("Nacional", area, ind, a0), v("Nacional", area, ind, a1)
            if x0 is not None and x1 is not None:
                partes.append(f"{nom} {x0.valor:.1f}→{x1.valor:.1f}")
        L.append(f"- {area}: " + "; ".join(partes))
    L += ["", "## 3. Departamentos (total, solo estimaciones con CV ≤ 15% en ambos años)"]
    d = comp[(comp.dominio != "Nacional") & (comp.area == "Total") & (comp.indicador == "ods611_minimo")]
    d = d[(d[f"ee_{a0}"] / d[f"valor_{a0}"] <= .15) & (d[f"ee_{a1}"] / d[f"valor_{a1}"] <= .15)]
    for titulo, sub in [("Mayores caídas", d.nsmallest(5, "dif_pp")), ("Mayores mejoras", d.nlargest(5, "dif_pp"))]:
        L.append(f"- {titulo}: " + "; ".join(
            f"{r.dominio} {r.dif_pp:+.1f} pp{'*' if r.significativo_95 else ''}" for r in sub.itertuples()))
    lim = res[(res.anio == a1) & (res.dominio != "Nacional") & (res.area == "Total") & (res.indicador == "ods611_minimo")]
    L.append(f"- Criterio limitante en {a1} (n.º de departamentos): " + ", ".join(
        f"{CRITERIOS.get(k, k)} {n}" for k, n in lim["criterio_limitante"].value_counts().items()))
    L.append("  (* = diferencia significativa al 95%)")
    L += ["", "## 4. Mínimo (método JMP) vs conjunto (los tres a la vez en el hogar)"]
    for area in ["Total", "Urbano", "Rural"]:
        x, y = v("Nacional", area, "ods611_minimo", a1), v("Nacional", area, "ods611_conjunto", a1)
        if x is not None and y is not None:
            L.append(f"- {area} {a1}: mínimo {x.valor:.1f}% vs conjunto {y.valor:.1f}%")
    z = v("Nacional", "Total", "ods611_minimo_directo", a1)
    if z is not None:
        L.append(f"- Mínimo directo sobre el total nacional {a1}: {z.valor:.1f}% (comparar con el MVCS)")
    L += ["", "## 5. Sensibilidad al umbral de continuidad (nacional, total)"]
    for suf, nom in [("", "24 h"), ("_20h", "20 h"), ("_12h", "12 h")]:
        x = v("Nacional", "Total", f"ods611_minimo{suf}", a1)
        if x is not None:
            L.append(f"- {nom}: {x.valor:.1f}% (limitante: {x.criterio_limitante})")
    L += ["", "## 6. Validación con cifras oficiales"]
    for r in val.itertuples():
        if not pd.isna(r.valor):
            L.append(f"- {r.fuente} {r.anio} {r.area} {r.indicador}: oficial {r.valor_ref} vs propio "
                     f"{r.valor:.1f} ({r.dif_pp:+.1f} pp) → {r.estado}")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=int, default=2019, help="año base de la comparación")
    ap.add_argument("--final", type=int, default=None, help="por defecto, el último procesado")
    a = ap.parse_args()

    bases = sorted(glob.glob(str(PROC / "base_*.csv.gz")))
    if not bases:
        raise SystemExit("No hay bases procesadas. Corre primero scripts/procesar_datos.py")
    res = pd.concat([estimar(pd.read_csv(f, low_memory=False), int(f.split("_")[-1][:4]))
                     for f in bases], ignore_index=True)
    hog = sorted(glob.glob(str(PROC / "hogares_*.csv.gz")))
    if hog:
        res = pd.concat([res] + [estimar_hogares(pd.read_csv(f, low_memory=False), int(f.split("_")[-1][:4]))
                                 for f in hog], ignore_index=True)
    # Población expandida (personas) del dominio, área y año: la usa el dashboard para el
    # tamaño de las burbujas y para el KPI de personas sin agua segura. Se asigna también a
    # las filas de indicadores en hogares (es la población, no el número de hogares).
    pob = pd.DataFrame([dict(anio=int(f.split("_")[-1][:4]), dominio=dom, area=area, poblacion=g["peso"].sum())
                        for f in bases
                        for dom, area, g in dominios(pd.read_csv(f, usecols=["departamento", "area", "peso"]))])
    res = res.merge(pob, on=["anio", "dominio", "area"], how="left")
    a1 = a.final or int(res.anio.max())
    comp = comparar(res, a.base, a1)
    val = validar(res)

    res.round(3).to_csv(PROC / "indicadores.csv", index=False)
    comp.round(3).to_csv(PROC / f"comparacion_{a.base}_{a1}.csv", index=False)
    robustez_codigo9(a1).round(3).to_csv(PROC / f"robustez_codigo9_{a1}.csv", index=False)
    if 2023 in set(res.anio) and a1 != 2023:
        comparar(res, 2023, a1).round(3).to_csv(PROC / f"comparacion_2023_{a1}.csv", index=False)
    poblacion_sin_agua_segura(res, [a.base, a1]).round(4).to_csv(
        PROC / f"poblacion_sin_agua_segura_{a.base}_{a1}.csv", index=False)
    # Descomposición del 6.1.1 nacional: es exacta solo si el cloro es el criterio limitante
    # en urbano y rural en ambos años (entonces 6.1.1 nacional = cloro adecuado nacional).
    lim = res[(res.dominio == "Nacional") & (res.area.isin(["Urbano", "Rural"])) &
              (res.indicador == "ods611_minimo") & (res.anio.isin([a.base, a1]))]["criterio_limitante"]
    if set(lim) == {"cal_cloro_adecuado"}:
        descomponer(a.base, a1, "cal_cloro_adecuado", None).round(3).to_csv(
            PROC / f"descomposicion_ods611_{a.base}_{a1}.csv", index=False)
    else:
        print("Aviso: el criterio limitante no es el cloro en todas las áreas; no se descompone el 6.1.1")
    descomponer(a.base, a1).round(3).to_csv(PROC / f"descomposicion_red_urbana_{a.base}_{a1}.csv", index=False)
    val.round(3).to_csv(PROC / "validacion.csv", index=False)
    (PROC / "hallazgos_borrador.md").write_text(borrador_hallazgos(res, comp, val, a.base, a1), encoding="utf-8")

    WEB.mkdir(parents=True, exist_ok=True)
    res.round(2).replace({np.nan: None}).to_json(WEB / "indicadores.json", orient="records", force_ascii=False)
    meta = {"anios": sorted(res.anio.unique().tolist()), "anio_base": a.base, "anio_final": a1,
            "fuente": "INEI - ENAPRES (microdatos); cálculo propio con factor de expansión",
            "criterios": CRITERIOS}
    (WEB / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print((PROC / "hallazgos_borrador.md").read_text(encoding="utf-8"))
    print(f"\nSalidas en {PROC} y {WEB}")


if __name__ == "__main__":
    main()
