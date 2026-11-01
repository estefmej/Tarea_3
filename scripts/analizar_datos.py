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
           ("cloro_inadecuado_en_red", "den_red_medido"), ("sin_cloro_en_red", "den_red_medido")]


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


def estimar(b, anio):
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
    return res


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
    a1 = a.final or int(res.anio.max())
    comp = comparar(res, a.base, a1)
    val = validar(res)

    res.round(3).to_csv(PROC / "indicadores.csv", index=False)
    comp.round(3).to_csv(PROC / f"comparacion_{a.base}_{a1}.csv", index=False)
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
