"""Compara el acento de tres formas de narrar las mismas escenas (por defecto, la 1 y la 3).

    .venv\\Scripts\\python pruebas_acento.py [--escenas 1 3]

    (a) VoxCPM2 con tu grabación completa como referencia de voz y como inicio (con su transcripción)
    (b) Qwen3-TTS 1.7B con tu grabación completa y su transcripción
    (c) la versión actual (Qwen3-TTS 0.6B), para comparar

Guarda en salidas/pruebas_acento/: escena_N_a_voxcpm2.wav, escena_N_b_qwen17b.wav, escena_N_c_actual.wav y calidad.csv.
Mide la similitud con tu grabación, con las escenas aprobadas 2 y 4 (que no se prueban aquí) y el WER.
"""
import argparse
import csv
import gc
import json
import shutil
import time

import soundfile as sf

import reel

p = argparse.ArgumentParser()
p.add_argument("--voz", default=str(reel.AQUI / "mi_voz.m4a"))
p.add_argument("--escenas", type=int, nargs="+", default=[1, 3])
p.add_argument("--buenas", type=int, nargs="+", default=[2, 4])
p.add_argument("--semilla", type=int, default=1234)
a = p.parse_args()

t0 = time.time()
ESCENAS = reel.AQUI / "salidas" / "escenas"
SALIDA = reel.AQUI / "salidas" / "pruebas_acento"
SALIDA.mkdir(parents=True, exist_ok=True)
guion = json.loads((reel.AQUI / "guion.json").read_text(encoding="utf-8"))
sim = reel.Similitud(a.voz, *[ESCENAS / f"escena_{n}.wav" for n in a.buenas])
filas = []


def medir(variante, n, w, sr, seg=None):
    s = sim(w, sr)
    f = dict(escena=n, variante=variante, sim_mi_voz=round(s[0], 3), sim_buenas=round(sum(s[1:]) / len(s[1:]), 3),
             wer=round(reel._wer(guion["escenas"][n - 1]["frase"], reel._a16k(w, sr)), 3),
             duracion_s=round(len(w) / sr, 2), seg_calculo=seg)
    filas.append(f)
    reel._reloj(f"escena {n}, {variante}: similitud {f['sim_mi_voz']:.3f} (tu voz) / {f['sim_buenas']:.3f} (escenas "
                f"{a.buenas}), WER {f['wer']:.2f}", t0)


# (c) versión actual
for n in a.escenas:
    shutil.copy(ESCENAS / f"escena_{n}.wav", SALIDA / f"escena_{n}_c_actual.wav")
    w, sr = sf.read(SALIDA / f"escena_{n}_c_actual.wav", dtype="float32")
    medir("c) actual: Qwen3-TTS 0.6B", n, w, sr)

# (b) Qwen3-TTS 1.7B, misma preparación que la actual (referencia completa a 24 kHz + transcripción)
voz = reel.Voz(a.voz, modelo="Qwen/Qwen3-TTS-12Hz-1.7B-Base")
reel._reloj(f"Qwen3-TTS 1.7B cargado; texto de referencia: «{voz.texto_ref}»", t0)
for n in a.escenas:
    t = time.time()
    w = voz.decir([guion["escenas"][n - 1]["frase"]], semilla=a.semilla)[0]
    sf.write(SALIDA / f"escena_{n}_b_qwen17b.wav", w, voz.sr)
    medir("b) Qwen3-TTS 1.7B", n, w, voz.sr, round(time.time() - t, 1))
del voz
gc.collect()

# (a) VoxCPM2: grabación completa como referencia de timbre y como inicio con su transcripción
import tempfile
import torch
from voxcpm import VoxCPM

audio = reel.cargar_audio(a.voz)
ref = reel.Path(tempfile.mkdtemp()) / "referencia.wav"
sf.write(ref, audio, 16000)
texto_ref = reel._transcribir(audio)
tts = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False, optimize=False, device="cpu")
reel._reloj("VoxCPM2 cargado", t0)
for n in a.escenas:
    t = time.time()
    torch.manual_seed(a.semilla)
    w = tts.generate(text=guion["escenas"][n - 1]["frase"], reference_wav_path=str(ref),
                     prompt_wav_path=str(ref), prompt_text=texto_ref, cfg_value=2.0, inference_timesteps=10)
    sr = tts.tts_model.sample_rate
    sf.write(SALIDA / f"escena_{n}_a_voxcpm2.wav", w, sr)
    medir("a) VoxCPM2", n, w, sr, round(time.time() - t, 1))

filas.sort(key=lambda f: (f["escena"], f["variante"]))
with open(SALIDA / "calidad.csv", "w", newline="", encoding="utf-8") as fh:
    wr = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
    wr.writeheader()
    wr.writerows(filas)
reel._reloj(f"listo: {SALIDA / 'calidad.csv'}", t0)
