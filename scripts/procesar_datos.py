"""2) PROCESAMIENTO: LIMPIEZA Y TRANSFORMACIÓN

Para cada año:
  - Conserva entrevistas completas (si se configura la variable de resultado).
  - Elimina hogares duplicados (según las llaves del hogar).
  - Excluye hogares sin dato de fuente de agua.
  - Anula valores imposibles: horas fuera de 0-24, cloro negativo o sobre el máximo.
  - Construye variables 0/1 por hogar (criterios ODS 6.1.1 según fichas MVCS):
      red_publica         P129G en {1,2,3} (2024+: P135; el código 9 "red pública
                          casa del vecino" NO cuenta, igual que en las fichas MVCS)
      acc_en_vivienda     P129G = 1                         (accesible)
      disp_24h/20h/12h    red y P130 = 1 y P130A >= umbral  (disponible)
      cal_cloro_adecuado  red y P129D >= 0,5 mg/L           (libre de contaminación, proxy)
      ods611_conjunto     cumple los tres a la vez (24 h)
      cloro_*_en_red      distribución del cloro entre hogares con red y prueba
  - Asigna el peso: factor de personas del capítulo 200 (método oficial) o,
    si no se configura, factor del hogar x miembros del hogar.
La fuente de agua se lee como texto (2019 usa códigos 6A/6B). Los hogares con llaves
repetidas se excluyen completos (no se sabe cuál registro es el bueno).
Salidas: datos/procesados/base_<año>.csv.gz y datos/procesados/reporte_limpieza.csv

Uso:
  python scripts/procesar_datos.py --anios 2019 2022 2023 2024 2025
"""
import argparse
import re

import numpy as np
import pandas as pd

from comun import DEPARTAMENTOS, RAIZ, anios_configurados, cargar_config, columnas, leer, num

PROC = RAIZ / "datos" / "procesados"


def _texto(s):
    """Códigos como texto sin '.0' ('1.0' -> '1', '6A' -> '6A'); vacío -> NaN."""
    t = s.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    return t.mask(t.isin(["", "nan", "None"]))


def _codigos(lista):
    return [str(x) for x in lista]


def _estrato(df, c, cfg):
    """Estrato de diseño: una variable, o la combinación de varias (p. ej. CCDD x AREA)."""
    e = cfg["estrato_diseno"]
    if isinstance(e, list):
        return df[[c[v] for v in e]].astype(str).apply(
            lambda r: "-".join(re.sub(r"\.0$", "", x) for x in r), axis=1).values
    return df[c[e]].values


def procesar(anio, config_dir=None):
    cfg = cargar_config(anio, config_dir)
    df = leer(cfg["archivo_hogar"])
    log = {"anio": anio, "registros_iniciales": len(df)}

    fa, co, cl = cfg["fuente_agua"], cfg["continuidad"], cfg["cloro"]
    fe = cfg.get("filtro_entrevista", {})
    est = cfg["estrato_diseno"]
    est = est if isinstance(est, list) else [est]
    cl_vars = [cl.get("variable"), cl.get("variable_entero"), cl.get("variable_decimal"), cl.get("no_realizada")]
    c = columnas(df, cfg["llaves_hogar"] + est + cl_vars + [
        cfg["factor_hogar"], cfg.get("miembros_hogar"),
        cfg["conglomerado"], cfg["area"]["variable"], cfg["ubigeo"], fe.get("variable"),
        fa["variable"], co["todos_los_dias"], co["horas_dia"]], f"hogar {anio}")

    # --- Limpieza ---------------------------------------------------------
    if fe.get("variable"):
        ok = num(df[c[fe["variable"]]]).isin(fe["valores_validos"])
        log["excluidos_entrevista_incompleta"] = int((~ok).sum())
        df = df[ok]
    llaves = [c[k] for k in cfg["llaves_hogar"]]
    dup = df.duplicated(subset=llaves, keep=False)
    claves_dup = ["-".join(map(str, r)) for r in df.loc[dup, llaves].drop_duplicates().itertuples(index=False)]
    log["duplicados_pares"] = int(len(claves_dup))
    log["duplicados_hogares_excluidos"] = int(dup.sum())
    log["duplicados_llaves"] = "; ".join(claves_dup) + (f" ({'-'.join(cfg['llaves_hogar'])})" if len(claves_dup) else "")
    df = df[~dup].copy()

    fuente = _texto(df[c[fa["variable"]]])
    sin_fuente = fuente.isna()
    log["excluidos_sin_fuente_agua"] = int(sin_fuente.sum())
    df, fuente = df[~sin_fuente].copy(), fuente[~sin_fuente]

    horas = num(df[c[co["horas_dia"]]])
    malas_h = (horas < 0) | (horas > 24)
    log["horas_invalidas_anuladas"] = int(malas_h.sum())
    horas = horas.mask(malas_h)

    # --- Construcción de variables ------------------------------------------
    out = pd.DataFrame({k: df[c[k]].values for k in cfg["llaves_hogar"]}, index=df.index)
    out["anio"] = anio
    w = num(df[c[cfg["factor_hogar"]]])
    out["factor_hogar"] = w
    out["miembros"] = num(df[c[cfg["miembros_hogar"]]]) if cfg.get("miembros_hogar") else 1
    out["estrato"] = _estrato(df, c, cfg)
    out["psu"] = df[c[cfg["conglomerado"]]].values
    a = num(df[c[cfg["area"]["variable"]]])
    out["area"] = np.select([a.isin(cfg["area"]["urbano"]), a.isin(cfg["area"]["rural"])],
                            ["Urbano", "Rural"], default=None)
    ubi = df[c[cfg["ubigeo"]]].astype(str).str.replace(r"\.0$", "", regex=True)
    # CCDD trae 2 dígitos; un UBIGEO completo trae 6
    dep = ubi.str.zfill(2).where(ubi.str.len() <= 2, ubi.str.zfill(6))
    out["departamento"] = dep.str[:2].map(DEPARTAMENTOS)

    dentro = fuente.isin(_codigos(fa["red_dentro_vivienda"]))
    red = fuente.isin(_codigos(fa["red_dentro_vivienda"] + fa["red_fuera_vivienda"] + fa["pilon_uso_publico"]))
    log["red_vecino_no_contada_como_red"] = int(fuente.isin(_codigos(fa.get("red_vecino", []))).sum())
    out["red_publica"] = red.astype(int)
    out["acc_en_vivienda"] = dentro.astype(int)
    # Código 9 (2024+): no cuenta como red; se guarda solo para análisis de sensibilidad
    out["red_vecino"] = fuente.isin(_codigos(fa.get("red_vecino", []))).astype(int)

    todos = num(df[c[co["todos_los_dias"]]]).isin(co["codigo_si"])
    for h in cfg["umbrales_horas"]:
        cond = (horas == 24) if h == 24 else (horas >= h)
        out[f"disp_{h}h"] = (red & todos & cond).astype(int)

    if cl.get("variable_entero"):
        # mg/L = parte entera + décimas (lectura del disco del comparador)
        v = num(df[c[cl["variable_entero"]]]) + num(df[c[cl["variable_decimal"]]]) / 10
        if cl.get("no_realizada"):
            v = v.mask(num(df[c[cl["no_realizada"]]]) == 1)
    else:
        v = num(df[c[cl["variable"]]])
    if cl["tipo"] == "numerica":
        malos_cl = (v < 0) | (v > cl.get("maximo_valido", 99))
        log["cloro_invalido_anulado"] = int(malos_cl.sum())
        v = v.mask(malos_cl)
        adec, inad, sin = v >= cl["umbral"], (v > 0) & (v < cl["umbral"]), v == 0
    else:
        adec, inad, sin = v.isin(cl["adecuado"]), v.isin(cl["inadecuado"]), v.isin(cl["sin_cloro"])
    medido = red & (adec | inad | sin)
    log["hogares_con_red_sin_prueba_cloro"] = int((red & ~medido).sum())
    out["cal_cloro_adecuado"] = (red & adec).astype(int)
    out["ods611_conjunto"] = (dentro & (out["disp_24h"] == 1) & adec).astype(int)
    out["den_red_medido"] = medido.astype(int)
    out["cloro_adecuado_en_red"] = (medido & adec).astype(int)
    out["cloro_inadecuado_en_red"] = (medido & inad).astype(int)
    out["sin_cloro_en_red"] = (medido & sin).astype(int)
    # Medida del INEI ("Acceso a los servicios básicos"): % de HOGARES con cloro
    # adecuado entre los hogares con prueba realizada, con cualquier fuente de agua.
    out["den_medido_hogar"] = (adec | inad | sin).astype(int)
    out["cloro_adecuado_hogar"] = adec.astype(int)

    sin_area = out["area"].isna() | out["departamento"].isna()
    log["excluidos_sin_area_o_ubigeo"] = int(sin_area.sum())
    out = out[~sin_area & (out["factor_hogar"] > 0)]

    # Base de hogares (sin pasar a personas) para replicar las cifras del INEI en hogares
    PROC.mkdir(parents=True, exist_ok=True)
    out.assign(peso=out["factor_hogar"]).to_csv(PROC / f"hogares_{anio}.csv.gz", index=False)

    # --- Peso de personas ------------------------------------------------------
    p = cfg.get("personas", {})
    if p.get("archivo"):
        per = leer(p["archivo"])
        fr = p.get("filtro_residente", {})
        regla = p.get("regla_residente")
        vars_regla = sorted(set(re.findall(r"[A-Za-z_]\w*", regla))) if regla else []
        cp = columnas(per, cfg["llaves_hogar"] + vars_regla + [p["factor"], fr.get("variable")], f"personas {anio}")
        log["personas_registros"] = len(per)
        if regla:
            # Residente habitual, p. ej. (P204 == 1 & P205 == 2) | (P204 == 2 & P206 == 1)
            tmp = pd.DataFrame({v: num(per[cp[v]]) for v in vars_regla})
            per = per[tmp.eval(regla).fillna(False).values]
        elif fr.get("variable"):
            per = per[num(per[cp[fr["variable"]]]).isin(fr["valores_validos"])]
        log["personas_residentes"] = len(per)
        per = pd.DataFrame({k: per[cp[k]].values for k in cfg["llaves_hogar"]}
                           | {"peso": num(per[cp[p["factor"]]]).values})
        out = out.merge(per, on=cfg["llaves_hogar"], how="inner")
        log["metodo_peso"] = "capitulo 200 (factor de personas)"
    else:
        out["peso"] = out["factor_hogar"] * out["miembros"]
        log["metodo_peso"] = "factor hogar x miembros"
    log["registros_finales"] = len(out)
    log["poblacion_expandida"] = round(float(out["peso"].sum()))

    PROC.mkdir(parents=True, exist_ok=True)
    out.to_csv(PROC / f"base_{anio}.csv.gz", index=False)
    return log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--anios", nargs="*", type=int)
    ap.add_argument("--config-dir", default=None)
    a = ap.parse_args()
    logs = []
    for anio in a.anios or anios_configurados(a.config_dir):
        print(f"Procesando {anio}...")
        logs.append(procesar(anio, a.config_dir))
    rep = pd.DataFrame(logs)
    rep.to_csv(PROC / "reporte_limpieza.csv", index=False)
    print("\nReporte de limpieza:\n", rep.T.to_string())


if __name__ == "__main__":
    main()
