"""Pasos 2 a 4: guion.json -> voz clonada -> reel vertical.

    Voz           Qwen3-TTS clona tu voz con 10 a 20 s de audio y narra cada escena
    VozExpresiva  VoxCPM2 clona tu voz y además acepta un estilo por escena (locutor, urgente, cálido)
    subtitulos()  Whisper transcribe la narración: subtítulos palabra por palabra y control de calidad
    video()       reel 1080x1920 con cifras, subtítulos y aviso de voz generada con IA

El paso 1 (texto largo -> guion.json) está en guion.py.
"""
import re
import subprocess
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import imageio_ffmpeg
import jiwer
import numpy as np
import soundfile as sf
from num2words import num2words
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

AQUI = Path(__file__).parent
FUENTES = AQUI / "fuentes"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

TTS = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
ASR = "large-v3-turbo"

ANCHO, ALTO, FPS = 1080, 1920, 30
MARGEN = 90
# Paleta del tema oscuro del dashboard, para que las capturas se fundan con el fondo
FONDO, TEXTO, SUAVE, ACENTO, CAJA = "#0F1B21", "#E4EDEF", "#AFC0C6", "#3CC2C2", "#1C2E36"
# Zonas verticales (px): cifra, captura, subtítulos y pie. [0] = escenas normales, [1] = última escena (con créditos)
# La captura ocupa todo el ancho y empieza 30 px debajo del texto de la escena (ver _medios).
ZONA_CIFRA = [(330, 560), (470, 580)]   # [1]: pantalla final, más abajo para centrar el título y los créditos
CAJA_MEDIO = [(0, 590, ANCHO, 1385), (0, 500, ANCHO, 1010)]
SUB_Y, PIE_Y = 1415, 1560
ZOOM = 1.05   # zoom lento de las capturas fijas a lo largo de la escena
# Capturas claras (el mapa en modo claro) como tarjeta sobre el fondo oscuro: margen lateral, margen interno,
# radio de las esquinas y sombra (desenfoque, desplazamiento hacia abajo y opacidad)
TARJETA_MARGEN, TARJETA_PAD, TARJETA_RADIO = 36, 20, 30
SOMBRA_BLUR, SOMBRA_DY, SOMBRA_ALFA = 24, 14, 170
BARRA_Y, TITULO_Y, AVISO_Y = 140, 205, 262   # barra de avance, título y aviso de IA
FUNDIDO, PREVIA_S = 0.4, 2.5   # fundido entre escenas y segundos de las barras previas en la escena 4
PAUSA, INICIO, FINAL = 0.3, 0.3, 1.5   # segundos de silencio entre escenas, al inicio y al final
# Estilos de VoxCPM2 por defecto; en inglés funcionan mejor que en español. Una escena puede traer su "estilo" en guion.json
ESTILOS = {"inicio": "urgent, dramatic news anchor, strong emphasis",
           "medio": "confident news anchor, energetic, clear emphasis on the numbers",
           "cierre": "warm, friendly, inviting tone"}


def _reloj(msg, t):
    print(f"[{time.time() - t:5.1f}s] {msg}", flush=True)


# Voz clonada ---------------------------------------------------------------

def cargar_audio(ruta, sr=16000):
    """Cualquier audio (wav, m4a, ogg de WhatsApp, mp3) a mono float32 con ffmpeg."""
    crudo = subprocess.run([FFMPEG, "-v", "error", "-i", str(ruta), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                           capture_output=True, check=True).stdout
    return np.frombuffer(crudo, np.float32)


def _local(repo):
    """Carpeta local del modelo si ya está descargado. transformers 4.57 consulta Hugging Face aunque el modelo
    esté en caché cuando recibe el nombre del repositorio; con la carpeta funciona sin conexión."""
    from huggingface_hub import snapshot_download
    try:
        return snapshot_download(repo, local_files_only=True)
    except Exception:
        return repo


class Voz:
    """Clona una voz a partir de 10 a 20 segundos de audio y su transcripción (la hace Whisper).

    Para que el timbre no cambie entre escenas: la referencia se prepara una sola vez (a 24 kHz, la
    frecuencia del modelo), cada escena se genera por separado con una semilla fija y la temperatura
    de muestreo baja de 0.9 a 0.7."""

    def __init__(self, referencia, modelo=TTS, device="cpu", temperatura=0.7):
        import torch
        from qwen_tts import Qwen3TTSModel

        self.torch = torch
        self.referencia = cargar_audio(referencia)                 # 16 kHz, para Whisper
        self.texto_ref = _transcribir(self.referencia)
        self.tts = Qwen3TTSModel.from_pretrained(_local(modelo), device_map=device, dtype=torch.float32)
        self.prompt = self.tts.create_voice_clone_prompt(ref_audio=(cargar_audio(referencia, 24000), 24000),
                                                         ref_text=self.texto_ref)
        self.temperatura = temperatura

    def decir(self, frases, estilos=None, semilla=1234):   # Qwen3-TTS no acepta estilo al clonar
        wavs = []
        for f in frases:
            self.torch.manual_seed(semilla)
            w, self.sr = self.tts.generate_voice_clone(text=[f], language=["Spanish"], voice_clone_prompt=self.prompt,
                                                       temperature=self.temperatura,
                                                       subtalker_temperature=self.temperatura)
            wavs.append(np.asarray(w[0], np.float32))
        return wavs


class VozExpresiva:
    """VoxCPM2 (OpenBMB, Apache 2.0): clona la voz y sigue un estilo escrito entre paréntesis antes de la frase."""

    def __init__(self, referencia, device="cpu", con_estilo=True):
        import tempfile
        from voxcpm import VoxCPM

        audio = cargar_audio(referencia)
        self.ref = Path(tempfile.mkdtemp()) / "referencia.wav"
        sf.write(self.ref, audio, 16000)
        self.texto_ref = _transcribir(audio)
        self.con_estilo = con_estilo
        self.tts = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False, optimize=False, device=device)
        self.sr = self.tts.tts_model.sample_rate

    def decir(self, frases, estilos=None, semilla=1234):
        import torch
        estilos = estilos if self.con_estilo and estilos else [None] * len(frases)
        wavs = []
        for f, e in zip(frases, estilos):
            torch.manual_seed(semilla)
            wavs.append(np.asarray(self.tts.generate(text=f"({e}){f}" if e else f, reference_wav_path=str(self.ref),
                                                     cfg_value=2.0, inference_timesteps=10),
                                   np.float32))
        return wavs


def _transcribir(audio16k):
    return " ".join(s.text.strip() for s in _whisper().transcribe(audio16k, language="es")[0])


def _acelerar(w, sr, factor):
    """Cambia el ritmo sin cambiar el tono (atempo de ffmpeg)."""
    crudo = subprocess.run([FFMPEG, "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-",
                            "-af", f"atempo={factor}", "-f", "f32le", "-"],
                           input=np.asarray(w, np.float32).tobytes(), capture_output=True, check=True).stdout
    return np.frombuffer(crudo, np.float32)


# Similitud de hablante ------------------------------------------------------

class Similitud:
    """Coseno entre embeddings de hablante de WavLM-SV (microsoft/wavlm-base-plus-sv).
    1 = misma voz; el modelo sugiere ~0.86 como umbral de «mismo hablante»."""

    def __init__(self, *referencias):
        import torch
        from transformers import AutoFeatureExtractor, WavLMForXVector
        self.torch = torch
        self.fe = AutoFeatureExtractor.from_pretrained("microsoft/wavlm-base-plus-sv")
        self.modelo = WavLMForXVector.from_pretrained("microsoft/wavlm-base-plus-sv").eval()
        self.refs = [self.embedding(cargar_audio(r)) for r in referencias]

    def embedding(self, audio16k):
        x = self.fe(audio16k, sampling_rate=16000, return_tensors="pt")
        with self.torch.no_grad():
            e = self.modelo(**x).embeddings[0]
        return self.torch.nn.functional.normalize(e, dim=-1)

    def __call__(self, w, sr):
        """Similitud del audio con cada referencia, en el orden en que se dieron."""
        e = self.embedding(_a16k(w, sr))
        return [float(e @ r) for r in self.refs]


# Subtítulos y control de calidad --------------------------------------------

_ASR = None


def _whisper():
    global _ASR
    if _ASR is None:
        from faster_whisper import WhisperModel
        _ASR = WhisperModel(ASR, device="cpu", compute_type="int8")
    return _ASR


@dataclass
class Narracion:
    audio: np.ndarray
    sr: int
    escenas: list            # (inicio, fin) en segundos de cada escena
    palabras: list = field(default_factory=list)   # (inicio, fin, palabra) de Whisper

    @property
    def duracion(self):
        return len(self.audio) / self.sr


def narrar(voz, guion, max_wer=0.25, reintentos=1, velocidad=1.0):
    """Narra cada escena; si Whisper no entiende bien una escena (WER alto), la vuelve a generar."""
    frases = [e["frase"] for e in guion["escenas"]]
    n = len(frases)
    estilos = [e.get("estilo") or ESTILOS["inicio" if i == 0 else "cierre" if i == n - 1 else "medio"]
               for i, e in enumerate(guion["escenas"])]
    wavs = voz.decir(frases, estilos)
    if velocidad != 1:
        wavs = [_acelerar(w, voz.sr, velocidad) for w in wavs]
    for intento in range(reintentos + 1):
        for e, w in zip(guion["escenas"], wavs):
            e["wer"] = _wer(e["frase"], _a16k(w, voz.sr))
        malas = [i for i, e in enumerate(guion["escenas"]) if e["wer"] > max_wer]
        if not malas or intento == reintentos:
            break
        for i, w in zip(malas, voz.decir([frases[i] for i in malas], [estilos[i] for i in malas])):
            wavs[i] = _acelerar(w, voz.sr, velocidad) if velocidad != 1 else w

    return unir(wavs, voz.sr)


def unir(wavs, sr):
    """Une los audios de las escenas con silencios al inicio, entre escenas y al final."""
    partes, escenas, t = [np.zeros(int(INICIO * sr), np.float32)], [], INICIO
    for w in wavs:
        w = np.asarray(w, np.float32)
        escenas.append((t, t + len(w) / sr))
        partes += [w, np.zeros(int(PAUSA * sr), np.float32)]
        t += len(w) / sr + PAUSA
    partes.append(np.zeros(int(FINAL * sr), np.float32))
    return Narracion(np.concatenate(partes), sr, escenas)


def _a16k(w, sr):
    w = np.asarray(w, np.float32)
    return np.interp(np.arange(0, len(w), sr / 16000), np.arange(len(w)), w).astype(np.float32)


# Lo que la voz lee distinto (o Whisper escribe distinto) -> cómo se escribe en subtítulos y en el WER
ESCRITURA = {"cayao": "Callao", "calao": "Callao", "callao": "Callao", "ini": "INEI", "inei": "INEI"}
SIGLAS = {"Instituto Nacional de Estadística": "INEI"}   # la voz lo dice completo; el subtítulo muestra la sigla


def _normalizar(s):
    """Para comparar lo escrito con lo que oyó Whisper: números en palabras, sin tildes ni puntuación."""
    s = s.lower().replace("%", " por ciento")
    s = re.sub(r"\b(" + "|".join(ESCRITURA) + r")\b", lambda m: ESCRITURA[m.group()].lower(), s)
    # Whisper escribe "2.700.000" o "21.700.000": se quitan los separadores de miles
    s = re.sub(r"(?<=\d)[.,](?=\d{3}(?:\D|$))", "", s)
    s = re.sub(r"\d+", lambda m: num2words(int(m.group()), lang="es"), s)
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()
    # num2words usa el masculino: "setecientas" = "setecientos", "veintiun" = "veintiuno", "un" = "uno"
    s = re.sub(r"ientas\b", "ientos", s)
    s = re.sub(r"\b(veintiun|un)\b", lambda m: m.group() + "o", s)
    return " ".join(re.sub(r"[^\w\s]", " ", s).split())


def _wer(referencia, audio16k):
    oido = " ".join(s.text for s in _whisper().transcribe(audio16k, language="es")[0])
    return jiwer.wer(_normalizar(referencia), _normalizar(oido)) if _normalizar(oido) else 1.0


def subtitulos(narracion, guion):
    """Palabras con tiempo; el guion va como contexto para que Whisper escriba bien los nombres propios."""
    contexto = " ".join(e.get("frase_subtitulos", e["frase"]) for e in guion["escenas"])
    segs, _ = _whisper().transcribe(_a16k(narracion.audio, narracion.sr), language="es",
                                    word_timestamps=True, initial_prompt=contexto)
    palabras = []
    for w in (w for s in segs for w in s.words if w.word.strip()):
        # Whisper a veces parte "8.7" o "126%" en dos palabras: se pegan a la anterior
        if palabras and re.match(r"^[.,%]", w.word.strip()):
            ini, _, prev = palabras.pop()
            palabras.append((ini, w.end, prev + w.word.strip()))
        else:
            palabras.append((w.start, w.end, w.word.strip()))
    # "Cayao" -> "Callao", "INI" -> "INEI", conservando la puntuación pegada a la palabra
    def escribir(x):
        m = re.match(r"^(\W*)(\w+)(\W*)$", x)
        return m.group(1) + ESCRITURA[m.group(2).lower()] + m.group(3) if m and m.group(2).lower() in ESCRITURA else x
    palabras = [(a, b, escribir(x)) for a, b, x in palabras]
    # Lo que la voz dice completo y el subtítulo muestra como sigla: las palabras se unen en una sola
    for largo, sigla in SIGLAS.items():
        n = len(largo.split())
        k = 0
        while k + n <= len(palabras):
            if _normalizar(" ".join(p[2] for p in palabras[k:k + n])) == _normalizar(largo):
                cola = re.search(r"\W*$", palabras[k + n - 1][2]).group()
                palabras[k:k + n] = [(palabras[k][0], palabras[k + n - 1][1], sigla + cola)]
            k += 1
    narracion.palabras = palabras = _como_el_guion(palabras, contexto)
    return palabras


def _como_el_guion(palabras, texto):
    """Whisper aporta los tiempos; la ortografía y la puntuación salen del guion («¿es agua segura?», «Calculé»,
    «cincuenta y dos» en vez de «52»). Se alinean palabra por palabra (sin tildes ni puntuación). Si en un tramo
    distinto el texto coincide pero no el número de palabras (Whisper escribe «52» y el guion «cincuenta y dos»),
    las palabras del guion se reparten en el tiempo de ese tramo. Lo demás queda como lo escribió Whisper."""
    import difflib
    guion = texto.split()
    a = [_normalizar(p[2]) for p in palabras]
    b = [_normalizar(x) for x in guion]
    salida = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal" or (op == "replace" and i2 - i1 == j2 - j1):
            salida += [(palabras[i][0], palabras[i][1], guion[j]) for i, j in zip(range(i1, i2), range(j1, j2))]
        elif op == "replace" and " ".join(a[i1:i2]).split() == " ".join(b[j1:j2]).split():
            ini, fin = palabras[i1][0], palabras[i2 - 1][1]
            pesos = [len(x) + 1 for x in guion[j1:j2]]
            t = ini
            for x, w in zip(guion[j1:j2], pesos):
                d = (fin - ini) * w / sum(pesos)
                salida.append((t, t + d, x))
                t += d
        elif op in ("replace", "delete"):
            salida += palabras[i1:i2]
    return salida


def _bloques(palabras, max_palabras=4, max_letras=24):
    """Agrupa palabras en bloques cortos para leer en el celular; corta en signos de puntuación."""
    bloques, actual = [], []
    for p in palabras:
        actual.append(p)
        largo = sum(len(x[2]) + 1 for x in actual)
        if len(actual) >= max_palabras or largo >= max_letras or p[2][-1] in ".,;:?!":
            bloques.append(actual)
            actual = []
    if actual:
        bloques.append(actual)
    return bloques


def a_srt(narracion, ruta):
    def hms(t):
        return f"{int(t // 3600):02}:{int(t % 3600 // 60):02}:{int(t % 60):02},{int(t % 1 * 1000):03}"
    lineas = []
    for i, b in enumerate(_bloques(narracion.palabras), 1):
        lineas += [str(i), f"{hms(b[0][0])} --> {hms(b[-1][1])}", " ".join(p[2] for p in b), ""]
    Path(ruta).write_text("\n".join(lineas), encoding="utf-8")


# Video ---------------------------------------------------------------------

def _fuente(nombre, tam, peso):
    ruta = FUENTES / f"{nombre}.ttf"
    if not ruta.exists():   # Oswald y Public Sans, de Google Fonts (licencia OFL)
        import urllib.request
        FUENTES.mkdir(exist_ok=True)
        urllib.request.urlretrieve(f"https://github.com/google/fonts/raw/main/ofl/{nombre.lower()}/{nombre}%5Bwght%5D.ttf", ruta)
    f = ImageFont.truetype(str(ruta), tam)
    f.set_variation_by_axes([peso])
    return f


def _envolver(draw, texto, fuente, ancho):
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if draw.textlength(prueba, font=fuente) <= ancho:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    return lineas + [actual]


def _ajustar(draw, texto, nombre, peso, ancho, maximo, minimo=80):
    for tam in range(maximo, minimo, -10):
        f = _fuente(nombre, tam, peso)
        if draw.textlength(texto, font=f) <= ancho:
            return f
    return _fuente(nombre, minimo, peso)


def _base(titulo):
    """Lo que no cambia en todo el video: título y aviso de IA."""
    img = Image.new("RGB", (ANCHO, ALTO), FONDO)
    d = ImageDraw.Draw(img)
    d.text((MARGEN, TITULO_Y), titulo.upper(), font=_fuente("PublicSans", 40, 800), fill=ACENTO)
    aviso = "VOZ GENERADA CON IA"
    f = _fuente("PublicSans", 28, 700)
    x1 = MARGEN + d.textlength(aviso, font=f) + 36
    d.rounded_rectangle((MARGEN, AVISO_Y, x1, AVISO_Y + 50), radius=25, outline=SUAVE, width=2)
    d.text((MARGEN + 18, AVISO_Y + 25), aviso, font=f, fill=SUAVE, anchor="lm")
    return img


def _texto(d, xy, texto, f, color):
    """Escribe el texto; la flecha (→), que no está en Oswald ni en Public Sans, se dibuja como figura."""
    x, y = xy
    for parte in re.split("(→)", texto):
        if parte == "→":
            alto_x = -d.textbbox((0, 0), "0", font=f, anchor="ls")[1]
            ym, ancho, grosor = y - alto_x / 2, f.size * 0.62, max(4, f.size // 14)
            x0, x1 = x + f.size * 0.08, x + f.size * 0.08 + ancho
            d.line((x0, ym, x1 - grosor, ym), fill=color, width=grosor)
            d.polygon([(x1, ym), (x1 - ancho * 0.42, ym - ancho * 0.32), (x1 - ancho * 0.42, ym + ancho * 0.32)], fill=color)
            x = x1 + f.size * 0.08
        elif parte:
            d.text((x, y), parte, font=f, fill=color, anchor="ls")
            x += d.textlength(parte, font=f)


def _escena(e, ultima, fuente_datos, creditos):
    """Capa transparente con la cifra grande, su etiqueta y el pie (o los créditos, en la última escena)."""
    capa = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    ancho = ANCHO - 2 * MARGEN
    def alto(texto, f):   # altura sobre la línea base
        return -d.textbbox((0, 0), texto, font=f, anchor="ls")[1]

    # (texto, fuente, color, alto, espacio después); el bloque se centra entre el aviso de IA y la captura
    lineas = []
    if e.get("cifra"):
        f = _ajustar(d, e["cifra"], "Oswald", 700, ancho, 210)
        lineas.append((e["cifra"], f, TEXTO, alto(e["cifra"], f), 50))
        fe, color = _fuente("PublicSans", 52, 600), SUAVE
    else:
        fe, color = _fuente("Oswald", 84, 600), TEXTO
    lineas += [(x, fe, color, alto("H", fe), int(fe.size * 0.45)) for x in _envolver(d, e["etiqueta"], fe, ancho)]
    arriba, abajo = ZONA_CIFRA[1] if ultima else ZONA_CIFRA[0]
    # centrado en su zona, pero sin subir por encima de ella (si la etiqueta ocupa dos líneas, baja la captura)
    y = max(arriba, (arriba + abajo - sum(h + g for *_, h, g in lineas) + lineas[-1][4]) / 2)
    for texto, f, color, h, g in lineas:
        y += h
        _texto(d, (MARGEN, y), texto, f, color)
        y += g
    capa.info["fin_texto"] = y - lineas[-1][4]   # para que la captura empiece debajo del texto

    if ultima:   # créditos en lugar del pie, justo debajo del título; la primera línea (repositorio) en color
        fc = _fuente("PublicSans", 44, 600)
        y = capa.info["fin_texto"] + 80
        for i, linea in enumerate(creditos):
            for parte in _envolver(d, linea, fc, ancho):
                d.text((MARGEN, y), parte, font=fc, fill=ACENTO if i == 0 else TEXTO if i == 1 else SUAVE)
                y += 58
            y += 30
        capa.info["fin_texto"] = y
    else:
        pie = _fuente("PublicSans", 32, 500)
        for i, linea in enumerate(_envolver(d, f"Fuente: {fuente_datos}", pie, ancho)):
            d.text((MARGEN, PIE_Y + i * 44), linea, font=pie, fill=SUAVE)
    return capa


class _Medio:
    """Captura (con zoom lento) o clip del dashboard, ajustado a su caja entre la cifra y los subtítulos."""

    def __init__(self, ruta, caja, zoom=ZOOM):
        x0, y0, x1, y1 = caja
        self.zoom = zoom
        if Path(ruta).suffix == ".mp4":
            lector = imageio_ffmpeg.read_frames(str(ruta))
            meta = next(lector)
            w, h = meta["size"]
            crudos = [Image.frombytes("RGB", (w, h), c) for c in lector]
        else:
            img = Image.open(ruta).convert("RGB")
            # margen del color del fondo de la captura: el zoom lento recorta ese margen y no el contenido
            m = round(max(img.size) * (zoom - 1) / 2) + 4
            crudos = [ImageOps.expand(img, border=m, fill=img.getpixel((0, 0)))]
            w, h = crudos[0].size
        color = crudos[0].getpixel((0, 0))
        claro = sum(color[:3]) > 3 * 160
        if claro:   # deja sitio para el margen lateral y el margen interno de la tarjeta
            x0, x1 = x0 + TARJETA_MARGEN + TARJETA_PAD, x1 - TARJETA_MARGEN - TARJETA_PAD
            y0, y1 = y0 + TARJETA_PAD, y1 - TARJETA_PAD - 30   # y 30 px libres sobre los subtítulos
        s = min((x1 - x0) / w, (y1 - y0) / h)
        self.tam = (round(w * s), round(h * s))
        self.pos = (x0 + (x1 - x0 - self.tam[0]) // 2, y0 + (y1 - y0 - self.tam[1]) // 2)
        self.original = crudos[0] if len(crudos) == 1 else None
        self.cuadros = None if self.original else [c.resize(self.tam, Image.LANCZOS) for c in crudos]
        self.mascara = Image.new("L", self.tam, 0)
        radio = 0 if claro or self.tam[0] >= ANCHO else 22   # en la tarjeta, el redondeo lo pone la tarjeta
        ImageDraw.Draw(self.mascara).rounded_rectangle((0, 0, *self.tam), radius=radio, fill=255)
        self.tarjeta = self._tarjeta(color) if claro else None

    def _tarjeta(self, color):
        """Tarjeta del color claro de la captura, con esquinas redondeadas y sombra suave; se pega debajo de la captura."""
        e = SOMBRA_BLUR * 2 + SOMBRA_DY                       # espacio alrededor para que la sombra no se corte
        cw, ch = self.tam[0] + 2 * TARJETA_PAD, self.tam[1] + 2 * TARJETA_PAD
        sombra = Image.new("L", (cw + 2 * e, ch + 2 * e), 0)
        ImageDraw.Draw(sombra).rounded_rectangle((e, e + SOMBRA_DY, e + cw, e + ch + SOMBRA_DY),
                                                 radius=TARJETA_RADIO, fill=SOMBRA_ALFA)
        sombra = sombra.filter(ImageFilter.GaussianBlur(SOMBRA_BLUR))
        capa = Image.new("RGBA", sombra.size, (0, 0, 0, 0))
        capa.putalpha(sombra)
        ImageDraw.Draw(capa).rounded_rectangle((e, e, e + cw, e + ch), radius=TARJETA_RADIO, fill=(*color[:3], 255))
        self.pos_tarjeta = (self.pos[0] - TARJETA_PAD - e, self.pos[1] - TARJETA_PAD - e)
        return capa

    def imagen(self, t, dur):
        """Cuadro en el segundo t de la escena (dur = duración de la escena)."""
        if self.cuadros:    # clip: se reproduce una vez y se queda en el último cuadro
            return self.cuadros[min(int(t * FPS), len(self.cuadros) - 1)]
        z = 1 + (self.zoom - 1) * min(1.0, max(0.0, t / max(dur, 0.1)))   # zoom lento hacia el centro
        W, H = self.original.size
        cw, ch = W / z, H / z
        return self.original.resize(self.tam, Image.BILINEAR, box=((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2))


def _medios(guion, recursos, capas=None, sufijo=""):
    """Para cada escena, su clip (escena_N.mp4) o su captura (escena_N.png), si existen; con sufijo="_previa",
    la imagen que se muestra antes (escena_N_previa.png). Con las capas, la caja de la captura empieza al menos
    30 px debajo del texto de la escena."""
    medios = []
    for n in range(1, len(guion["escenas"]) + 1):
        caja = CAJA_MEDIO[1] if n == len(guion["escenas"]) else CAJA_MEDIO[0]
        if capas:
            caja = (caja[0], max(caja[1], round(capas[n - 1].info["fin_texto"]) + 30), caja[2], caja[3])
        nombres = [f"escena_{n}{sufijo}.png"] if sufijo else [f"escena_{n}.mp4", f"escena_{n}.png"]
        ruta = next((Path(recursos) / x for x in nombres if (Path(recursos) / x).exists()), None)
        medios.append(_Medio(ruta, caja) if ruta else None)
    return medios


class _Foto:
    """Foto horizontal recortada a vertical alrededor de foco_x (0 = borde izquierdo, 1 = derecho), con zoom lento
    y una capa oscura para que la cifra se lea."""

    def __init__(self, ruta, foco_x=0.5, zoom=1.08, oscuro=0.55):
        img = Image.open(ruta).convert("RGB")
        alto = round(ALTO * zoom)
        img = img.resize((round(img.width * alto / img.height), alto), Image.LANCZOS)
        ancho = round(ANCHO * zoom)
        x0 = min(max(0, round(img.width * foco_x - ancho / 2)), img.width - ancho)
        self.img = img.crop((x0, 0, x0 + ancho, alto))
        self.zoom = zoom
        # capa oscura pareja, más densa arriba (título) y abajo (subtítulos y pie)
        velo = Image.new("L", (1, ALTO))
        for y in range(ALTO):
            borde = max(0.0, 1 - y / 700) * 0.25 + max(0.0, (y - 1200) / 720) * 0.35
            velo.putpixel((0, y), round(255 * min(0.92, oscuro + borde)))
        self.velo = Image.merge("RGBA", [*Image.new("RGB", (ANCHO, ALTO), FONDO).split(), velo.resize((ANCHO, ALTO))])

    def cuadro(self, t, dur):
        z = 1 + (self.zoom - 1) * min(1.0, max(0.0, t / max(dur, 0.1)))   # de lo más abierto al zoom máximo
        W, H = self.img.size
        cw, ch = W / z, H / z   # en z = 1 se ve la foto entera (ya recortada a 9:16)
        cx, cy = W / 2, H / 2
        img = self.img.resize((ANCHO, ALTO), Image.BILINEAR, box=(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2))
        img.paste(self.velo, (0, 0), self.velo)
        return img


class _Montaje:
    """Arma cada cuadro: escenas con fundidos cortos entre ellas, la foto de la escena 1, las barras previas de la
    escena 4, la barra de avance y los subtítulos."""

    def __init__(self, guion, narracion, fuente_datos, creditos, recursos=None):
        self.n = n = len(guion["escenas"])
        self.narracion = narracion
        self.cabecera = _base(guion["titulo"])
        self.capas = [_escena(e, k == n - 1, fuente_datos, creditos) for k, e in enumerate(guion["escenas"])]
        self.medios = _medios(guion, recursos, self.capas) if recursos else [None] * n
        self.previas = _medios(guion, recursos, self.capas, "_previa") if recursos else [None] * n
        self.fotos = [None] * n
        for k, e in enumerate(guion["escenas"]):
            if e.get("foto") and recursos and (Path(recursos) / e["foto"]["archivo"]).exists():
                self.fotos[k] = (_Foto(Path(recursos) / e["foto"]["archivo"], e["foto"].get("foco_x", 0.5)),
                                 e["foto"].get("hasta", 0.5))
        self.bloques = _bloques(narracion.palabras)
        self.fuente_sub = _fuente("PublicSans", 62, 800)
        # cada escena empieza cuando termina la voz de la anterior (el fundido ocurre en la pausa)
        esc = narracion.escenas
        self.inicios = [0.0] + [esc[k - 1][1] for k in range(1, n)]
        self.finales = self.inicios[1:] + [narracion.duracion]

    def _con_medio(self, i, m, t, dur, fondo=None):
        img = (fondo or self.cabecera).copy()
        if m:
            cuadro = m.imagen(t, dur)
            if m.tarjeta:   # tarjeta y captura juntas
                capa_t = m.tarjeta.copy()
                capa_t.paste(cuadro, (m.pos[0] - m.pos_tarjeta[0], m.pos[1] - m.pos_tarjeta[1]))
                img.paste(capa_t, m.pos_tarjeta, capa_t.getchannel("A"))
            else:
                img.paste(cuadro, m.pos, m.mascara)
        img.paste(self.capas[i], (0, 0), self.capas[i])
        return img

    def escena(self, i, t):
        """Cuadro de la escena i en el segundo t del video, sin barra de avance ni subtítulos."""
        tl, dur = t - self.inicios[i], self.finales[i] - self.inicios[i]
        foto, previa, m = self.fotos[i], self.previas[i], self.medios[i]
        if foto:   # escena 1: foto a pantalla completa con la cifra; luego, las barras
            f, hasta = foto
            hasta *= dur
            if tl < hasta + FUNDIDO:
                fondo = f.cuadro(tl, hasta + FUNDIDO)
                fondo.paste(self.cabecera.crop((0, 0, ANCHO, AVISO_Y + 60)), (0, 0), self._mascara_cabecera())
                img_foto = fondo.copy()
                img_foto.paste(self.capas[i], (0, 0), self.capas[i])
                if tl < hasta:
                    return img_foto
                normal = self._con_medio(i, m, tl - hasta, dur - hasta)
                return Image.blend(img_foto, normal, (tl - hasta) / FUNDIDO)
            return self._con_medio(i, m, tl - hasta, dur - hasta)
        if previa:   # escena 4: primero las barras del inicio con el cloro resaltado
            if tl < PREVIA_S:
                return self._con_medio(i, previa, tl, PREVIA_S)
            normal = self._con_medio(i, m, tl - PREVIA_S, dur - PREVIA_S)
            if tl < PREVIA_S + FUNDIDO:
                return Image.blend(self._con_medio(i, previa, tl, PREVIA_S), normal, (tl - PREVIA_S) / FUNDIDO)
            return normal
        return self._con_medio(i, m, tl, dur)

    def _mascara_cabecera(self):
        """Solo el texto del título y el aviso de IA (sin el fondo), para ponerlos sobre la foto."""
        if not hasattr(self, "_mc"):
            fondo = Image.new("RGB", (ANCHO, AVISO_Y + 60), FONDO)
            dif = ImageChops.difference(self.cabecera.crop((0, 0, ANCHO, AVISO_Y + 60)), fondo).convert("L")
            self._mc = dif.point(lambda v: 255 if v > 10 else 0)
        return self._mc

    def cuadro(self, t):
        i = max(k for k in range(self.n) if self.inicios[k] <= t)
        img = self.escena(i, t)
        a = (t - self.inicios[i]) / FUNDIDO
        if a < 1:   # fundido corto pasando por el fondo: sale la escena anterior y entra la nueva, sin encimarse
            if i == 0:
                img = Image.blend(Image.new("RGB", (ANCHO, ALTO), "black"), img, max(0.0, a))
            elif a < 0.5:
                img = Image.blend(self.escena(i - 1, t), self.cabecera, a * 2)
            else:
                img = Image.blend(self.cabecera, img, (a - 0.5) * 2)

        d = ImageDraw.Draw(img)
        dur = self.narracion.duracion
        d.rounded_rectangle((MARGEN, BARRA_Y, ANCHO - MARGEN, BARRA_Y + 8), radius=4, fill=CAJA)
        d.rounded_rectangle((MARGEN, BARRA_Y, MARGEN + (ANCHO - 2 * MARGEN) * t / dur, BARRA_Y + 8), radius=4, fill=ACENTO)
        b = next((b for b in self.bloques if b[0][0] - 0.1 <= t <= b[-1][1] + 0.25), None)
        if b:   # el bloque que se está diciendo, con la palabra actual resaltada
            fs = self.fuente_sub
            texto = " ".join(p[2] for p in b)
            w = d.textlength(texto, font=fs)
            x, y = (ANCHO - w) / 2, SUB_Y
            d.rounded_rectangle((x - 36, y - 26, x + w + 36, y + fs.size + 34), radius=28, fill=CAJA)
            for ini_p, fin_p, palabra in b:
                d.text((x, y), palabra, font=fs, fill=ACENTO if ini_p <= t <= fin_p + 0.05 else TEXTO)
                x += d.textlength(palabra + " ", font=fs)
        return img


def _lufs(entradas, filtro="anull"):
    """Sonoridad integrada (LUFS) según EBU R128."""
    r = subprocess.run([FFMPEG, "-v", "info", *entradas, "-af", f"{filtro},ebur128", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r)[-1])


def _mezcla(wav, musica, duracion, salida, db_musica=-14, fundido=(1.5, 3.0)):
    """Audio final: narración a -14 LUFS y música db_musica dB por debajo de la voz (medido en LUFS sobre el
    tramo que se usa), continua de principio a fin con fundido al inicio y al final.
    Devuelve (ruta, LUFS voz, LUFS música)."""
    voz = Path(salida).with_name("_voz_norm.wav")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(wav), "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-ar", "48000", str(voz)], check=True)
    l_voz = _lufs(["-i", str(voz)])
    if not musica:
        subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(voz), "-ac", "2", str(salida)], check=True)
        voz.unlink()
        return salida, l_voz, None
    tramo = f"atrim=0:{duracion:.2f},asetpts=PTS-STARTPTS"
    ganancia = l_voz + db_musica - _lufs(["-stream_loop", "-1", "-i", str(musica)], tramo)
    fi, fo = fundido
    filtro = (f"[1:a]{tramo},volume={ganancia:.2f}dB,aresample=48000,"
              f"afade=t=in:d={fi},afade=t=out:st={duracion - fo:.2f}:d={fo}[m];"
              "[0:a][m]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.89[a]")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(voz), "-stream_loop", "-1", "-i", str(musica),
                    "-filter_complex", filtro, "-map", "[a]", "-ar", "48000", "-ac", "2", str(salida)], check=True)
    # nivel real de la música en la mezcla (con fundidos), para verificar
    l_mus = _lufs(["-stream_loop", "-1", "-i", str(musica)],
                  f"{tramo},volume={ganancia:.2f}dB,afade=t=in:d={fi},afade=t=out:st={duracion - fo:.2f}:d={fo}")
    voz.unlink()
    return salida, l_voz, l_mus


def video(guion, narracion, ruta, fuente_datos, creditos, recursos=None, musica=None, db_musica=-14):
    """Dibuja cada cuadro con Pillow y se los pasa a ffmpeg junto con la narración y la música de fondo."""
    ruta = Path(ruta)
    wav = ruta.with_suffix(".wav")
    sf.write(wav, narracion.audio, narracion.sr)
    audio, l_voz, l_mus = _mezcla(wav, musica, narracion.duracion, ruta.with_name(ruta.stem + "_audio.wav"), db_musica)
    print(f"   audio: voz {l_voz:.1f} LUFS" + (f", música {l_mus:.1f} LUFS ({l_mus - l_voz:+.1f} dB)" if l_mus else ", sin música"))
    montaje = _Montaje(guion, narracion, fuente_datos, creditos, recursos)
    cmd = [FFMPEG, "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{ANCHO}x{ALTO}", "-r", str(FPS), "-i", "-",
           "-i", str(audio),
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
           "-shortest", "-movflags", "+faststart", str(ruta)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for k in range(int(narracion.duracion * FPS)):
        proc.stdin.write(montaje.cuadro(k / FPS).tobytes())
    proc.stdin.close()
    proc.wait()
    return ruta


def portada(guion, narracion, ruta, fuente_datos, creditos, recursos=None, escena=1, segundo=1.0):
    """Un cuadro fijo para revisar el diseño o usar como miniatura (segundo = tiempo desde el inicio de la voz)."""
    montaje = _Montaje(guion, narracion, fuente_datos, creditos, recursos)
    montaje.cuadro(narracion.escenas[escena][0] + segundo).save(ruta)
    return ruta


def posts(guion, ruta):
    h = " ".join("#" + x.lstrip("#") for x in guion.get("hashtags", []))
    p = guion["posts"]
    Path(ruta).write_text(
        f"# {guion['titulo']}\n\n## LinkedIn\n\n{p['linkedin']}\n\n{h}\n\n"
        f"## X ({len(p['x'])} caracteres)\n\n{p['x']}\n\n## Facebook\n\n{p['facebook']}\n\n{h}\n",
        encoding="utf-8")
    return ruta
