"""Narra cada escena con tu voz clonada, mide su calidad y regenera las que se alejan.

    .venv\\Scripts\\python voces.py                    # Qwen3-TTS 0.6B
    .venv\\Scripts\\python voces.py --motor voxcpm     # para comparar
    .venv\\Scripts\\python voces.py --solo 3 5         # rehacer solo esas escenas

Guarda en salidas/escenas[_voxcpm]/: escena_1.wav ... escena_N.wav, narracion.wav y calidad.csv.
Por cada escena mide:
  - sim_mi_voz: similitud de hablante con tu grabación (la única referencia de clonación)
  - sim_ejemplo: similitud con el WAV de ejemplo (solo como modelo de cómo debe sonar)
  - wer: proporción de palabras que Whisper entiende mal
Una escena se regenera con otra semilla (hasta --intentos en total) si su similitud con tu voz
queda por debajo del umbral o si su WER pasa de --max-wer; se queda el mejor intento.
"""
import argparse
import csv
import json
import time

import numpy as np
import soundfile as sf

import reel

p = argparse.ArgumentParser()
p.add_argument("--voz", default=str(reel.AQUI / "mi_voz.m4a"))
p.add_argument("--ejemplo", default=str(reel.AQUI / "voz_buena_ejemplo.wav"))
p.add_argument("--guion", default=str(reel.AQUI / "guion.json"))
p.add_argument("--motor", default="qwen", choices=["qwen", "voxcpm"])
p.add_argument("--tts", default="Qwen/Qwen3-TTS-12Hz-0.6B-Base")
p.add_argument("--semilla", type=int, default=1234)
p.add_argument("--intentos", type=int, default=3)
p.add_argument("--max-wer", type=float, default=0.15)
p.add_argument("--margen", type=float, default=0.05,
               help="una escena se aleja si su similitud con tu voz cae más que esto bajo la mediana de las escenas")
p.add_argument("--solo", type=int, nargs="*", help="regenerar solo estas escenas (1 = primera)")
a = p.parse_args()

t0 = time.time()
salidas = reel.AQUI / "salidas" / ("escenas" if a.motor == "qwen" else "escenas_voxcpm")
salidas.mkdir(parents=True, exist_ok=True)
guion = json.loads(open(a.guion, encoding="utf-8").read())
frases = [e["frase"] for e in guion["escenas"]]

sim = reel.Similitud(a.voz, a.ejemplo)
sim_ej_mi = sim(reel.cargar_audio(a.ejemplo), 16000)[0]
reel._reloj(f"similitud del WAV de ejemplo con tu voz: {sim_ej_mi:.3f}", t0)

voz = reel.Voz(a.voz, modelo=a.tts) if a.motor == "qwen" else reel.VozExpresiva(a.voz, con_estilo=False)
reel._reloj(f"voz cargada ({a.motor}); referencia: «{voz.texto_ref}»", t0)


def generar(i, k):
    semilla = a.semilla + 1000 * k
    t = time.time()
    w = voz.decir([frases[i]], semilla=semilla)[0]
    s_mi, s_ej = sim(w, voz.sr)
    r = dict(escena=i + 1, intento=k + 1, semilla=semilla, duracion_s=round(len(w) / voz.sr, 2),
             sim_mi_voz=round(s_mi, 3), sim_ejemplo=round(s_ej, 3),
             wer=round(reel._wer(frases[i], reel._a16k(w, voz.sr)), 3), seg_calculo=round(time.time() - t, 1))
    reel._reloj(f"escena {i + 1}, intento {k + 1}: similitud {s_mi:.3f} (tu voz) / {s_ej:.3f} (ejemplo), "
                f"WER {r['wer']:.2f}, {r['duracion_s']} s de audio", t0)
    return w, r


archivo_calidad = salidas / "calidad.csv"
previas = []
if a.solo and archivo_calidad.exists():
    previas = [r for r in csv.DictReader(open(archivo_calidad, encoding="utf-8")) if int(r["escena"]) not in a.solo]
escenas = [i - 1 for i in a.solo] if a.solo else list(range(len(frases)))

mejores, filas = {}, []
for i in escenas:                                   # primera pasada: misma semilla para todas
    mejores[i] = generar(i, 0)
    filas.append(mejores[i][1])

# Umbral relativo: una escena se «aleja» si cae bajo la mediana de todas las escenas menos el margen
sims = [float(r["sim_mi_voz"]) for r in previas if r["elegido"] == "True"] + [r["sim_mi_voz"] for _, r in mejores.values()]
mediana = float(np.median(sims))
umbral = round(mediana - a.margen, 3)
reel._reloj(f"mediana de similitud con tu voz {mediana:.3f}; umbral para regenerar {umbral:.3f}", t0)


def malo(r):
    return r["sim_mi_voz"] < umbral or r["wer"] > a.max_wer


for i in escenas:
    k = 1
    while malo(mejores[i][1]) and k < a.intentos:
        w, r = generar(i, k)
        filas.append(r)
        # mejor intento: primero los que Whisper entiende bien; entre ellos, el más parecido a tu voz
        if (r["wer"] <= a.max_wer, r["sim_mi_voz"]) > (mejores[i][1]["wer"] <= a.max_wer, mejores[i][1]["sim_mi_voz"]):
            mejores[i] = (w, r)
        k += 1

for r in filas:
    r["elegido"] = mejores[r["escena"] - 1][1] is r
    r["umbral"] = umbral
    r["alejada"] = malo(r)
for i, (w, r) in mejores.items():
    sf.write(salidas / f"escena_{i + 1}.wav", w, voz.sr)

filas = previas + filas
filas.sort(key=lambda r: (int(r["escena"]), int(r["intento"])))
with open(archivo_calidad, "w", newline="", encoding="utf-8") as f:
    wr = csv.DictWriter(f, fieldnames=list(mejores[escenas[0]][1].keys()))
    wr.writeheader()
    wr.writerows(filas)

archivos = [salidas / f"escena_{i + 1}.wav" for i in range(len(frases))]
if all(x.exists() for x in archivos):
    n = reel.unir([sf.read(x, dtype="float32")[0] for x in archivos], voz.sr)
    sf.write(salidas / "narracion.wav", n.audio, n.sr)
    reel._reloj(f"narración completa: {n.duracion:.1f} s -> {salidas / 'narracion.wav'}", t0)
