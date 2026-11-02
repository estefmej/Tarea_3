"""Regenera algunas escenas con varias semillas y sugiere la que más se parece a las escenas que ya suenan bien.

    .venv\\Scripts\\python regenerar.py --buenas 2 3 4 --escenas 1 5 6 7 --semillas 101 202 303
    .venv\\Scripts\\python regenerar.py --elegir 1:202 5:101 6:303 7:101     # copia las elegidas a salidas/escenas/

Guarda en salidas/pruebas/: escena_N_semilla_S.wav (todas las versiones), escena_N_original.wav (la anterior,
para comparar) y calidad.csv. La referencia de clonación sigue siendo tu grabación original; las escenas buenas
solo se usan para medir el parecido:
  - sim_buenas: similitud media con las escenas buenas (criterio de elección)
  - sim_mi_voz: similitud con tu grabación
  - wer: palabras que Whisper entiende mal (se descartan las versiones con WER > --max-wer)
"""
import argparse
import csv
import json
import shutil
import time

import soundfile as sf

import reel

p = argparse.ArgumentParser()
p.add_argument("--voz", default=str(reel.AQUI / "mi_voz.m4a"))
p.add_argument("--tts", default="Qwen/Qwen3-TTS-12Hz-0.6B-Base")
p.add_argument("--buenas", type=int, nargs="+", default=[2, 3, 4])
p.add_argument("--escenas", type=int, nargs="+", default=[1, 5, 6, 7])
p.add_argument("--semillas", type=int, nargs="+", default=[101, 202, 303])
p.add_argument("--max-wer", type=float, default=0.15)
p.add_argument("--carpeta", default=str(reel.AQUI / "salidas" / "pruebas"), help="dónde guardar las versiones")
p.add_argument("--elegir", nargs="+", help="escena:semilla, p. ej. 1:202; copia esas versiones a salidas/escenas/")
a = p.parse_args()

ESCENAS = reel.AQUI / "salidas" / "escenas"
PRUEBAS = reel.Path(a.carpeta)
PRUEBAS.mkdir(parents=True, exist_ok=True)

if a.elegir:
    for par in a.elegir:
        n, s = par.split(":")
        origen = PRUEBAS / (f"escena_{n}_original.wav" if s == "original" else f"escena_{n}_semilla_{s}.wav")
        shutil.copy(origen, ESCENAS / f"escena_{n}.wav")
        print(f"   escena {n}: {origen.name}")
    raise SystemExit

t0 = time.time()
guion = json.loads((reel.AQUI / "guion.json").read_text(encoding="utf-8"))
buenas = [ESCENAS / f"escena_{n}.wav" for n in a.buenas]
sim = reel.Similitud(a.voz, *buenas)
reel._reloj(f"referencias de parecido: tu grabación y las escenas {a.buenas}", t0)


def medir(w, sr, frase):
    s = sim(w, sr)
    return dict(sim_buenas=round(sum(s[1:]) / len(s[1:]), 3), sim_mi_voz=round(s[0], 3),
                wer=round(reel._wer(frase, reel._a16k(w, sr)), 3), duracion_s=round(len(w) / sr, 2))


filas = []
for n in a.escenas:   # la versión anterior, como punto de comparación (el texto de 6 y 7 cambió)
    original = PRUEBAS / f"escena_{n}_original.wav"
    if not original.exists():
        shutil.copy(ESCENAS / f"escena_{n}.wav", original)
    w, sr = sf.read(original, dtype="float32")
    filas.append(dict(escena=n, version="original", semilla=1234, **medir(w, sr, guion["escenas"][n - 1]["frase"])))

voz = reel.Voz(a.voz, modelo=a.tts)
reel._reloj(f"voz cargada; referencia: «{voz.texto_ref}»", t0)
for n in a.escenas:
    frase = guion["escenas"][n - 1]["frase"]
    for s in a.semillas:
        w = voz.decir([frase], semilla=s)[0]
        sf.write(PRUEBAS / f"escena_{n}_semilla_{s}.wav", w, voz.sr)
        f = dict(escena=n, version=f"semilla {s}", semilla=s, **medir(w, voz.sr, frase))
        filas.append(f)
        reel._reloj(f"escena {n}, semilla {s}: parecido con las buenas {f['sim_buenas']:.3f}, "
                    f"con tu voz {f['sim_mi_voz']:.3f}, WER {f['wer']:.2f}", t0)

# sugerencia: entre las nuevas con WER aceptable, la más parecida a las escenas buenas
for n in a.escenas:
    nuevas = [f for f in filas if f["escena"] == n and f["version"] != "original"]
    validas = [f for f in nuevas if f["wer"] <= a.max_wer] or nuevas
    mejor = max(validas, key=lambda f: f["sim_buenas"])
    for f in filas:
        if f["escena"] == n:
            f["sugerida"] = f is mejor
with open(PRUEBAS / "calidad.csv", "w", newline="", encoding="utf-8") as fh:
    wr = csv.DictWriter(fh, fieldnames=list(filas[-1].keys()))
    wr.writeheader()
    wr.writerows(filas)
reel._reloj(f"listo: {PRUEBAS / 'calidad.csv'}", t0)
