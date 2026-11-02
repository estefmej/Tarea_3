"""Arma el reel con las escenas ya narradas por voces.py (no vuelve a generar la voz).

    .venv\\Scripts\\python voces.py           # 1. narración por escena + control de calidad (escúchenla)
    .venv\\Scripts\\python capturar.py        # 2. capturas y clips del dashboard
    .venv\\Scripts\\python hacer_reel.py --musica-titulo "..." --musica-autor "..."   # 3. este script

Guarda en salidas/: reel.mp4, reel.wav (narración), reel_audio.wav (mezcla), reel.srt y portada.png;
y copia a reel/ el resultado final: reel.mp4 y subtitulos.srt (guion.json ya está ahí).
"""
import argparse
import csv
import json
import shutil
import subprocess
import time

import soundfile as sf

import reel

p = argparse.ArgumentParser()
p.add_argument("--escenas", default=str(reel.AQUI / "salidas" / "escenas"), help="carpeta con escena_N.wav de voces.py")
p.add_argument("--recursos", default=str(reel.AQUI / "recursos"), help="capturas y clips de capturar.py")
p.add_argument("--musica", default=str(reel.AQUI / "recursos" / "musica.mp3"))
p.add_argument("--musica-titulo", default="Science Documentary")
p.add_argument("--musica-autor", default="Lexin_Music")
p.add_argument("--foto-autor", default="JonasKIM")
# Foto: Pixabay, licencia de contenido de Pixabay: https://pixabay.com/photos/faucet-sink-tap-tap-water-flow-3240211/
p.add_argument("--repositorio", default="github.com/estefmej/Tarea_3")
# Pixabay Music, licencia de contenido de Pixabay: https://pixabay.com/music/build-up-scenes-science-documentary-169621/
p.add_argument("--db-musica", type=float, default=-14, help="volumen de la música respecto a la voz, en dB (LUFS)")
p.add_argument("--fuente", default="INEI, ENAPRES 2019–2025; cálculo propio")
p.add_argument("--salidas", default=str(reel.AQUI / "salidas"))
a = p.parse_args()

t0 = time.time()
salidas, escenas = reel.Path(a.salidas), reel.Path(a.escenas)
archivo_guion = reel.AQUI / "guion.json"
guion = json.loads(archivo_guion.read_text(encoding="utf-8"))
n = len(guion["escenas"])

wavs, sr = [], None
for i in range(1, n + 1):
    w, sr = sf.read(escenas / f"escena_{i}.wav", dtype="float32")
    wavs.append(w)
narracion = reel.unir(wavs, sr)
reel._reloj(f"narración: {narracion.duracion:.1f} s con {n} escenas", t0)

# control de calidad de voces.py, para dejarlo anotado en guion.json
calidad = {int(r["escena"]): r for r in csv.DictReader(open(escenas / "calidad.csv", encoding="utf-8")) if r["elegido"] == "True"}
for i, e in enumerate(guion["escenas"], 1):
    if i in calidad:
        e["wer"] = float(calidad[i]["wer"])
        e["similitud_voz"] = float(calidad[i]["sim_mi_voz"])
archivo_guion.write_text(json.dumps(guion, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

reel.subtitulos(narracion, guion)
reel.a_srt(narracion, salidas / "reel.srt")
reel._reloj(f"subtítulos: {len(narracion.palabras)} palabras", t0)

musica = reel.Path(a.musica) if reel.Path(a.musica).exists() else None
if not musica:
    print(f"   ¡Ojo! No encontré {a.musica}: el video sale sin música.")
creditos = [f"Repositorio: {a.repositorio}",
            "Voz generada con IA a partir de la voz de la autora",
            f"Fuente: {a.fuente}",
            f"Música: «{a.musica_titulo}», {a.musica_autor} · Pixabay Music",
            f"Foto: {a.foto_autor} · Pixabay"]
reel.portada(guion, narracion, salidas / "portada.png", a.fuente, creditos, a.recursos)
reel.video(guion, narracion, salidas / "reel.mp4", a.fuente, creditos, a.recursos, musica, a.db_musica)
reel._reloj(f"video: {salidas / 'reel.mp4'}", t0)

# verificación: duración y tamaño
info = subprocess.run([reel.FFMPEG, "-i", str(salidas / "reel.mp4")], capture_output=True, text=True).stderr
dur = next(l for l in info.splitlines() if "Duration" in l).split(",")[0].strip()
vid = next(l for l in info.splitlines() if "Video:" in l)
print(f"   {dur}; {'1080x1920' if '1080x1920' in vid else 'TAMAÑO DISTINTO A 1080x1920'}")
segundos = narracion.duracion
print(f"   duración {'OK' if 45 <= segundos <= 75 else 'FUERA DEL RANGO 45–75 s'}: {segundos:.1f} s")

shutil.copy(salidas / "reel.mp4", reel.AQUI / "reel.mp4")
shutil.copy(salidas / "reel.srt", reel.AQUI / "subtitulos.srt")
reel._reloj("copiados reel.mp4 y subtitulos.srt a reel/", t0)
