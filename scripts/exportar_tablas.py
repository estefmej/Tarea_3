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
