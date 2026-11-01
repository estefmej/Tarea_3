"""1) OBTENCIÓN DE DATOS

Descarga los módulos de la ENAPRES (INEI) de cada año configurado y deja
registro de URL, fecha y archivos en datos/originales/registro_descargas.csv.
Opcionalmente descarga el ODS 6.1.1 del JMP (API del Banco Mundial) como contraste.

El código de encuesta de cada año se obtiene del portal de microdatos del INEI
(https://proyectos.inei.gob.pe/microdatos/): clic derecho en el ícono de descarga
de un módulo -> copiar enlace; el número antes de "-Modulo" es el código.
Se anota en config/anios/<año>.json junto con la lista de módulos.

Uso:
  python scripts/obtener_datos.py --anios 2019 2025 --dry-run
  python scripts/obtener_datos.py --anios 2019 2022 2023 2024 2025
  python scripts/obtener_datos.py --jmp
"""
import argparse
import datetime as dt
import json
import time
import zipfile

import pandas as pd
import requests

from comun import RAIZ, anios_configurados, cargar_config

URL_INEI = "https://proyectos.inei.gob.pe/iinei/srienaho/descarga/{fmt}/{cod}-Modulo{mod}.zip"
URL_WB = "https://api.worldbank.org/v2/country/PER/indicator/{cod}?format=json&per_page=200"
WB = {"SH.H2O.SMDW.ZS": "Total", "SH.H2O.SMDW.UR.ZS": "Urbano", "SH.H2O.SMDW.RU.ZS": "Rural"}
ORIG = RAIZ / "datos" / "originales"


def registrar(fuente, anio, url, archivo, n_archivos=""):
    log = ORIG / "registro_descargas.csv"
    pd.DataFrame([dict(fecha_descarga=dt.datetime.now().isoformat(timespec="seconds"),
                       fuente=fuente, anio=anio, url=url, archivo=str(archivo),
                       contenido=n_archivos)]).to_csv(
        log, mode="a", header=not log.exists(), index=False)


def get(url, intentos=4):
    """El servidor del INEI a veces deja de responder; se reintenta con espera."""
    verify = True
    for i in range(1, intentos + 1):
        try:
            return requests.get(url, timeout=(30, 600), verify=verify)
        except requests.exceptions.SSLError:
            print("  Aviso: certificado SSL del INEI falló; reintentando sin verificación")
            verify = False
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if i == intentos:
                raise
            print(f"  Sin respuesta del INEI (intento {i}/{intentos}); reintento en {20 * i} s")
            time.sleep(20 * i)
    return requests.get(url, timeout=(30, 600), verify=verify)


def enapres(anio, formato, dry):
    cfg = cargar_config(anio)
    cod, mods = cfg.get("codigo_encuesta"), cfg.get("modulos") or []
    if not cod or not mods:
        print(f"[{anio}] Falta codigo_encuesta o modulos en config/anios/{anio}.json")
        return
    destino_dir = ORIG / str(anio)
    destino_dir.mkdir(parents=True, exist_ok=True)
    for m in mods:
        url = URL_INEI.format(fmt=formato, cod=cod, mod=str(m).zfill(2))
        print(f"[{anio}] {url}")
        if dry:
            continue
        zpath = destino_dir / f"{cod}-Modulo{str(m).zfill(2)}.zip"
        if zpath.exists() and zipfile.is_zipfile(zpath):
            print("   ya descargado, se omite")
            continue
        r = get(url)
        r.raise_for_status()
        zpath = destino_dir / f"{cod}-Modulo{str(m).zfill(2)}.zip"
        zpath.write_bytes(r.content)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(destino_dir)
            nombres = z.namelist()
        registrar("INEI - ENAPRES", anio, url, zpath, "; ".join(nombres))
        print("   ->", *nombres, sep="\n      ")


def jmp():
    filas = []
    for cod, area in WB.items():
        url = URL_WB.format(cod=cod)
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        datos = r.json()[1] or []
        f = ORIG / f"jmp_wb_{cod}.json"
        f.write_text(json.dumps(datos), encoding="utf-8")
        registrar("JMP OMS/UNICEF vía Banco Mundial", "2000-", url, f)
        filas += [dict(anio=int(d["date"]), area=area, valor=d["value"])
                  for d in datos if d["value"] is not None]
    df = pd.DataFrame(filas).sort_values(["area", "anio"])
    out = RAIZ / "datos" / "procesados" / "jmp_ods611_peru.csv"
    df.to_csv(out, index=False)
    print(f"JMP: {len(df)} filas -> {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--anios", nargs="*", type=int, help="por defecto, todos los de config/anios")
    ap.add_argument("--formato", default="SPSS", choices=["STATA", "SPSS", "CSV"],
                    help="SPSS tiene la mayor cobertura de módulos en el portal")
    ap.add_argument("--dry-run", action="store_true", help="solo muestra los enlaces")
    ap.add_argument("--jmp", action="store_true", help="descarga también la serie del JMP")
    a = ap.parse_args()
    ORIG.mkdir(parents=True, exist_ok=True)
    for anio in a.anios or anios_configurados():
        enapres(anio, a.formato, a.dry_run)
    if a.jmp:
        jmp()


if __name__ == "__main__":
    main()
