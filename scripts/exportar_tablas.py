"""4) TABLAS DE REVISIÓN EN EXCEL

Lee las salidas de datos/procesados/ y escribe datos/procesados/tablas_revision.xlsx
con una hoja por tabla. Los valores se copian de los CSV (no se recalculan aquí) y se
redondean a un decimal; la significancia se decide con los valores sin redondear.

Uso:
  python scripts/exportar_tablas.py --base 2019 --final 2025
"""
import argparse

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from comun import RAIZ

PROC = RAIZ / "datos" / "procesados"
NOMBRES = {"red_publica": "Acceso a red pública", "disp_24h": "Continuidad 24 h",
           "cal_cloro_adecuado": "Cloro adecuado", "ods611_minimo": "ODS 6.1.1",
           "distinto en urbano y rural": "Distinto en urbano y rural"}
SI_NO = {True: "Sí", False: "No"}
NARANJA = PatternFill("solid", fgColor="FCE4D6")


def nacional(comp, a0, a1):
    d = comp[(comp.dominio == "Nacional") & comp.indicador.isin(list(NOMBRES)[:4])].copy()
    d["orden_i"] = d.indicador.map({k: i for i, k in enumerate(NOMBRES)})
    d["orden_a"] = d.area.map({"Total": 0, "Urbano": 1, "Rural": 2})
    d = d.sort_values(["orden_i", "orden_a"])
    return pd.DataFrame({
        "Criterio": d.indicador.map(NOMBRES), "Área": d.area,
        f"{a0} (%)": d[f"valor_{a0}"], f"CV {a0} (%)": d[f"cv_{a0}"],
        f"{a1} (%)": d[f"valor_{a1}"], f"CV {a1} (%)": d[f"cv_{a1}"],
        "Diferencia (pp)": d["dif_pp"], "Error estándar dif. (pp)": d["ee_dif"],
        "Significativa al 95%": d["significativo_95"].map(SI_NO)})


def departamentos(comp, a0, a1):
    d = comp[(comp.dominio != "Nacional") & (comp.area == "Total") & (comp.indicador == "ods611_minimo")]
    d = d.sort_values(f"dif_pp")
    alto = (d[f"cv_{a0}"] > 15) | (d[f"cv_{a1}"] > 15)
    return pd.DataFrame({
        "Departamento": d.dominio,
        f"6.1.1 {a0} (%)": d[f"valor_{a0}"], f"CV {a0} (%)": d[f"cv_{a0}"],
        f"Limitante {a0}": d[f"criterio_limitante_{a0}"].map(lambda x: NOMBRES.get(x, x)),
        f"6.1.1 {a1} (%)": d[f"valor_{a1}"], f"CV {a1} (%)": d[f"cv_{a1}"],
        f"Limitante {a1}": d[f"criterio_limitante_{a1}"].map(lambda x: NOMBRES.get(x, x)),
        "Diferencia (pp)": d["dif_pp"], "Significativa al 95%": d["significativo_95"].map(SI_NO),
        "CV > 15% (referencial)": alto.map({True: "Sí", False: ""})})


def robustez(rob, a1):
    d = rob[(rob.area == "Urbano") & rob.indicador.isin(["cal_cloro_adecuado", "ods611_minimo"])]
    t = d.pivot_table(index="indicador", columns="variante", values=["valor", "cv"])
    sin, con = "sin código 9 (definición del proyecto)", "contando código 9 como red"
    return pd.DataFrame({
        "Indicador (urbano, " + str(a1) + ")": [NOMBRES[i] for i in t.index],
        "Sin contar código 9 (%)": t[("valor", sin)].values, "CV sin código 9 (%)": t[("cv", sin)].values,
        "Contando código 9 (%)": t[("valor", con)].values, "CV con código 9 (%)": t[("cv", con)].values,
        "Diferencia (pp)": (t[("valor", con)] - t[("valor", sin)]).values})


def series_departamentos(res, deps, anios):
    d = res[res.dominio.isin(deps) & res.area.isin(["Total", "Urbano"])
            & res.indicador.isin(["cal_cloro_adecuado", "disp_24h", "ods611_minimo"])]
    filas = []
    for (dep, area, ind), g in d.groupby(["dominio", "area", "indicador"], sort=False):
        g = g.set_index("anio")
        fila = {"Departamento": dep, "Área": area, "Indicador": NOMBRES[ind]}
        for a in anios:
            fila[f"{a} (%)"] = g.valor.get(a)
            fila[f"CV {a}"] = g.cv.get(a)
        if ind == "ods611_minimo":
            fila["Limitante (todos los años)"] = ", ".join(sorted({NOMBRES.get(x, x) for x in g.criterio_limitante}))
        filas.append(fila)
    out = pd.DataFrame(filas)
    out["o"] = out.Indicador.map({"ODS 6.1.1": 0, "Cloro adecuado": 1, "Continuidad 24 h": 2})
    return out.sort_values(["Departamento", "Área", "o"]).drop(columns="o")


def cloro_vs_inei(val):
    d = val[(val.dominio != "Nacional") & (val.indicador == "cloro_adecuado_hogares")]
    return pd.DataFrame({"Departamento": d.dominio, "Año": d.anio, "INEI (% hogares)": d.valor_ref,
                         "Propio (% hogares)": d.valor, "Diferencia (pp)": d.dif_pp,
                         "Estado": d.estado, "Fuente": d.fuente}).sort_values(["Departamento", "Año"])


def poblacion(pob, a0, a1):
    p = pob.set_index("area").loc[["Total", "Urbano", "Rural"]].reset_index()
    return pd.DataFrame({
        "Área": p.area,
        f"Población {a0} (millones)": p[f"poblacion_millones_{a0}"], f"6.1.1 {a0} (%)": p[f"ods611_{a0}"],
        f"Sin agua segura {a0} (millones)": p[f"sin_agua_segura_millones_{a0}"], f"EE {a0} (millones)": p[f"ee_millones_{a0}"],
        f"Población {a1} (millones)": p[f"poblacion_millones_{a1}"], f"6.1.1 {a1} (%)": p[f"ods611_{a1}"],
        f"Sin agua segura {a1} (millones)": p[f"sin_agua_segura_millones_{a1}"], f"EE {a1} (millones)": p[f"ee_millones_{a1}"],
        "Diferencia (millones)": p["dif_millones"], "EE diferencia (millones)": p["ee_dif_millones"],
        "Significativa al 95%": p["significativo_95"].map(SI_NO)})


def descomposicion(d, a0, a1):
    return pd.DataFrame({
        "Departamento": d.departamento,
        f"Peso poblacional {a0} (%)": 100 * d[f"peso_pob_{a0}"], f"Peso poblacional {a1} (%)": 100 * d[f"peso_pob_{a1}"],
        f"Cloro adecuado {a0} (%)": d[f"tasa_{a0}"], f"Cloro adecuado {a1} (%)": d[f"tasa_{a1}"],
        "Efecto tasa (pp)": d["efecto_tasa_pp"], "Efecto composición (pp)": d["efecto_composicion_pp"],
        "Contribución total (pp)": d["contribucion_total_pp"],
        "% de la caída (efecto tasa)": d["pct_del_cambio_por_tasa"]}).sort_values("Contribución total (pp)")


def formato(ws, nota, n_cols, marcar_col=None):
    ws.insert_rows(1, 2)
    ws["A1"] = nota
    ws["A1"].font = Font(name="Arial", italic=True, size=9)
    for fila in ws.iter_rows():
        for c in fila:
            if c.row != 1:
                c.font = Font(name="Arial", size=10, bold=(c.row == 3))
            if isinstance(c.value, float):
                c.number_format = "0.0"
    for c in ws[3]:
        c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A4"
    for i in range(1, n_cols + 1):
        letra = ws.cell(row=3, column=i).column_letter
        largo = max(len(str(ws.cell(row=r, column=i).value or "")) for r in range(3, ws.max_row + 1))
        ws.column_dimensions[letra].width = min(max(10, largo + 2), 45)
    if marcar_col:
        for r in range(4, ws.max_row + 1):
            if ws.cell(row=r, column=marcar_col).value == "Sí":
                for c in ws[r]:
                    c.fill = NARANJA


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=int, default=2019)
    ap.add_argument("--final", type=int, default=2025)
    a = ap.parse_args()
    a0, a1 = a.base, a.final
    comp = pd.read_csv(PROC / f"comparacion_{a0}_{a1}.csv")
    val = pd.read_csv(PROC / "validacion.csv")
    rob = pd.read_csv(PROC / f"robustez_codigo9_{a1}.csv")
    res = pd.read_csv(PROC / "indicadores.csv")
    rec = pd.read_csv(PROC / f"comparacion_2023_{a1}.csv")
    pob = pd.read_csv(PROC / f"poblacion_sin_agua_segura_{a0}_{a1}.csv")
    dsc = pd.read_csv(PROC / f"descomposicion_ods611_{a0}_{a1}.csv")
    anios = sorted(res.anio.unique())
    hojas = {
        "Nacional": (nacional(comp, a0, a1), None,
                     f"% de población. Fuente: comparacion_{a0}_{a1}.csv (INEI-ENAPRES, cálculo propio). "
                     "Significancia al 95% con los valores sin redondear; CV > 15% = referencial."),
        "Departamentos": (departamentos(comp, a0, a1), 10,
                          f"ODS 6.1.1 total por departamento, ordenado de mayor caída a mayor mejora. Fuente: "
                          f"comparacion_{a0}_{a1}.csv. Filas en naranja: CV > 15% en algún año (cifras referenciales)."),
        "Validación": (val, None, "Copia de validacion.csv. OK/REVISAR solo para réplicas; contraste = otra definición o período."),
        "Robustez código 9": (robustez(rob, a1), None,
                              f"Fuente: robustez_codigo9_{a1}.csv. Código 9 = 'red pública casa del vecino' (2024+). "
                              "A esos hogares no se les pregunta la continuidad, que no cambia. "
                              "La definición del proyecto no cuenta el código 9."),
        "Arequipa y Callao": (series_departamentos(res, ["Arequipa", "Callao"], anios), None,
                              "% de población (CV). Fuente: indicadores.csv. El Callao es 100% urbano (Total = Urbano). "
                              "Limitante del 6.1.1: Arequipa = cloro; Callao = continuidad 24 h."),
        "Cloro dept. vs INEI": (cloro_vs_inei(val), None,
                                "% de HOGARES con cloro adecuado entre hogares con prueba. Fuente: validacion.csv "
                                "(cifras INEI en references/valores_referencia.csv)."),
        "Población sin agua segura": (poblacion(pob, a0, a1), None,
                                      f"(100 - 6.1.1) x población expandida. Fuente: poblacion_sin_agua_segura_{a0}_{a1}.csv. "
                                      "La población se trata como fija (calibrada a proyecciones INEI). El total es la suma de urbano y rural. "
                                      "Ojo: la baja rural se explica sobre todo por la menor población rural, no por una mejora del 6.1.1."),
        "Recuperación 2023-2025": (nacional(rec, 2023, a1), None,
                                   f"% de población. Fuente: comparacion_2023_{a1}.csv. Significancia al 95% con valores sin redondear."),
        "Descomposición 6.1.1": (descomposicion(dsc, a0, a1), None,
                                 f"Cambio del 6.1.1 nacional {a0}-{a1} repartido por departamento. Como el cloro limita en urbano y rural "
                                 f"en ambos años, el 6.1.1 nacional = cloro adecuado nacional; se usa la tasa de cloro de cada departamento. "
                                 f"Efecto tasa = peso medio x cambio de la tasa; composición = tasa media x cambio del peso. "
                                 f"Fuente: descomposicion_ods611_{a0}_{a1}.csv."),
    }
    out = PROC / "tablas_revision.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        for nombre, (df, _, _) in hojas.items():
            df.round(1).to_excel(xw, sheet_name=nombre, index=False)
    wb = load_workbook(out)
    for nombre, (df, marcar, nota) in hojas.items():
        formato(wb[nombre], nota, df.shape[1], marcar)
    wb.save(out)
    print(f"Listo: {out}")


if __name__ == "__main__":
    main()
