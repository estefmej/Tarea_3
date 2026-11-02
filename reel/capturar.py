"""Capturas del dashboard publicado para el reel (una por escena) y clips de las burbujas.

    .venv\\Scripts\\python capturar.py [--url URL] [--claro]

Guarda en recursos/: escena_1.png ... escena_7.png y escena_3.mp4, escena_4.mp4 (botón Reproducir).
"""
import argparse
import subprocess
import time
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

AQUI = Path(__file__).parent
RECURSOS = AQUI / "recursos"
URL = "https://estefmej.github.io/Tarea_3/web/"
# Vista móvil del dashboard (menos de 860 px CSS) a 3x. Con 480 px los gráficos quedan apaisados (~1.4:1),
# como el espacio libre del video, y pueden ocupar todo el ancho sin achicar las letras para caber en alto.
ANCHO_CSS = 480
ESCALA = 3

# escena: (elementos a capturar juntos, estado del dashboard); el estado usa las funciones del propio dashboard.
# Solo el gráfico o el mapa con su leyenda: sin títulos, textos explicativos ni botones.
EVO = ["#evolucion .legend", "#c-evo"]
ESCENAS = {
    1: (["#levels .lvl"],                              dict(anio=2025, area="Total", ind="ods", ambito="Nacional")),
    2: (["#kpis .kpi:nth-child(1)", "#kpis .kpi:nth-child(2)"], dict(anio=2025, area="Total", ind="ods", ambito="Nacional")),
    3: (EVO,                                           dict(anio=2025, area="Total", ind="ods", ambito="Nacional")),
    4: (EVO,                                           dict(anio=2025, area="Urbano", ind="ods", ambito="Nacional")),
    5: (["#c-map"],                                    dict(anio=2025, area="Rural", ind="cloro", ambito="Nacional")),
    6: (["#departamentos .two > div:first-child .legend", "#c-sc"], dict(anio=2025, area="Total", ind="ods", ambito="Nacional")),
}
CLIPS = (3, 4)
# En modo oscuro los valores bajos del mapa se pintan casi del color del fondo; el mapa de cloro rural
# (casi todo cerca de 0 %) se lee mejor en modo claro.
CLARAS = (5,)
# Escenas que unen dos capturas lado a lado: la principal y esta columna a la derecha
# (selectores, ancho CSS de la vista o None): la leyenda se captura en una vista angosta para que sus números
# queden grandes en proporción al ancho de la imagen
COLUMNA = {5: [(["#circles"], None), (["#mleg"], 320)]}
FONDO_CLARO = "#F3F6F5"   # --paper del tema claro

# Resaltar lo que dice la voz. Magenta: no se confunde con los colores del dashboard (azul, naranja, turquesa, gris).
RESALTE = "#FF5FA2"
# Se envuelve la función que dibuja cada gráfico para que el resaltado sobreviva a cada redibujo (p. ej., el clip
# que recorre los años); DESPUES restaura la función original.
_ENVOLVER = """([nombre, cuerpo]) => {
    window._orig = window._orig || {};
    if (!window._orig[nombre]) window._orig[nombre] = window[nombre];
    const extra = new Function('RES', cuerpo);
    window[nombre] = function () { window._orig[nombre].apply(this, arguments); extra('%s'); };
    render();
}""" % RESALTE
_RESTAURAR = """nombre => { if (window._orig && window._orig[nombre]) { window[nombre] = window._orig[nombre]; render(); } }"""
RESALTES = {
    # escena 4: la serie del cloro (urbano); las demás series se atenúan
    4: ("evolucion", """
        const s = d3.select('#c-evo svg');
        s.selectAll('circle').filter(p => p && p.k && p.k !== 'cloro')
         .attr('fill-opacity', function () { return +this.getAttribute('fill-opacity') * 0.25; });
        s.selectAll('circle').filter(p => p && p.k === 'cloro' && p.a <= S.anio).attr('stroke', RES).attr('stroke-width', 3);"""),
    # escena 5: el círculo rural
    5: ("mapa", """
        document.querySelectorAll('#circles .circ').forEach(c => {
            if (c.querySelector('.t').textContent.trim() !== 'Rural') return;
            c.querySelector('.c').style.boxShadow = `0 0 0 5px ${RES}`;
            c.querySelector('.t').style.color = RES; c.querySelector('.t').style.fontWeight = 700;
        });"""),
    # escena 6: Arequipa y el Callao, con un anillo y su nombre
    6: ("dispersion", """
        // Tacna está junto al Callao y la voz no la menciona: sin etiqueta, para que no se monten
        d3.select('#c-sc svg').selectAll('g').filter(p => p && p.d === 'Tacna').selectAll('text').remove();
        d3.select('#c-sc svg').selectAll('g').filter(p => p && (p.d === 'Arequipa' || p.d === 'Callao')).each(function (p) {
            const g = d3.select(this).raise(), r = +g.select('circle').attr('r');
            g.selectAll('text').remove();
            g.append('circle').attr('r', r + 6).attr('fill', 'none').attr('stroke', RES).attr('stroke-width', 3.5);
            g.append('text').attr('y', -r - 12).attr('text-anchor', 'middle').attr('font-size', 15)
             .attr('font-weight', 800).attr('fill', RES).text(p.d);
        });"""),
}
# Antes de las burbujas de la escena 4: las barras del inicio con la del cloro resaltada (enlaza con la escena 1)
PREVIAS = {4: (["#levels .lvl"], """() => document.querySelectorAll('#levels .lvl').forEach(l => {
        const cloro = l.querySelector('.lab').textContent.includes('cloro');
        l.style.opacity = cloro ? 1 : 0.3;
        l.querySelector('.tube').style.outline = cloro ? '4px solid %s' : '';
        l.querySelector('.tube').style.outlineOffset = '4px';
        l.querySelector('.lab').style.color = cloro ? '%s' : '';
    })""" % (RESALTE, RESALTE),
    """() => document.querySelectorAll('#levels .lvl').forEach(l => {
        l.style.opacity = ''; l.querySelector('.tube').style.outline = ''; l.querySelector('.lab').style.color = ''; })""")}


def _recortar(img, fondo, margen=12):
    """Quita el fondo sobrante alrededor del contenido (umbral bajo: los departamentos pálidos no son fondo)."""
    from PIL import Image, ImageChops
    dif = ImageChops.difference(img, Image.new("RGB", img.size, fondo)).convert("L")
    caja = dif.point(lambda v: 255 if v > 3 else 0).getbbox()
    if not caja:
        return img
    x0, y0, x1, y1 = caja
    return img.crop((max(0, x0 - margen), max(0, y0 - margen), min(img.width, x1 + margen), min(img.height, y1 + margen)))


def lado_a_lado(izq, partes, destino, proporcion=1.39, sep=60):
    """Compone una imagen con la proporción del espacio libre del video: arriba, la captura principal (el mapa) y a
    su derecha la primera parte (los círculos), agrandada; abajo, a todo el ancho, la última parte (la leyenda)."""
    from PIL import Image
    a = _recortar(Image.open(izq).convert("RGB"), FONDO_CLARO)
    col0, ley0 = [_recortar(Image.open(x).convert("RGB"), FONDO_CLARO) for x in partes]
    H_arriba = a.height
    W = round(H_arriba * proporcion)
    for _ in range(5):   # el alto de la leyenda depende del ancho total: se ajusta hasta que la proporción cuadre
        alto_ley = round(ley0.height * W / ley0.width)
        W = max(a.width + 400, round((H_arriba + sep + alto_ley) * proporcion))
    ancho_col = W - a.width - sep
    col = col0.resize((ancho_col, round(col0.height * ancho_col / col0.width)), Image.LANCZOS)
    if col.height > H_arriba:
        col = col.resize((round(col.width * H_arriba / col.height), H_arriba), Image.LANCZOS)
    ley = ley0.resize((W, round(ley0.height * W / ley0.width)), Image.LANCZOS)
    img = Image.new("RGB", (W, H_arriba + sep + ley.height), FONDO_CLARO)
    img.paste(a, (0, 0))
    img.paste(col, (a.width + sep + (ancho_col - col.width) // 2, (H_arriba - col.height) // 2))
    img.paste(ley, (0, H_arriba + sep))
    img.save(destino)


def fijar(page, anio, area, ind, ambito):
    page.evaluate("""([anio, area, ind, ambito]) => {
        document.querySelectorAll('#f-area button').forEach(b => b.setAttribute('aria-pressed', b.dataset.v === area));
        S.area = area; S.ind = ind; document.getElementById('f-ind').value = ind;
        setAmbito(ambito); setAnio(anio);
    }""", [anio, area, ind, ambito])
    page.wait_for_timeout(1200)     # transiciones de barras y colores


def caja(page, selectores, ancho=ANCHO_CSS, margen=8):
    """Rectángulo que cubre todos los elementos (todas las coincidencias de cada selector), en coordenadas de la página."""
    page.locator(selectores[0]).first.scroll_into_view_if_needed()
    page.wait_for_timeout(400)
    r = page.evaluate("""sels => { const bs = sels.flatMap(s => [...document.querySelectorAll(s)])
            .map(e => e.getBoundingClientRect()).filter(b => b.width && b.height);
        const x0 = Math.min(...bs.map(b => b.left)), y0 = Math.min(...bs.map(b => b.top));
        const x1 = Math.max(...bs.map(b => b.right)), y1 = Math.max(...bs.map(b => b.bottom));
        return {x: x0 + scrollX, y: y0 + scrollY, width: x1 - x0, height: y1 - y0}; }""", selectores)
    return {"x": max(0, r["x"] - margen), "y": max(0, r["y"] - margen),
            "width": min(ancho, r["width"] + 2 * margen), "height": r["height"] + 2 * margen}


def clip(page, selectores, destino, segundos=7.0):
    """Pulsa ▶ Reproducir y toma cuadros del gráfico; ffmpeg los une respetando el tiempo real de cada uno."""
    tmp = RECURSOS / f"_cuadros_{destino.stem}"
    tmp.mkdir(exist_ok=True)
    rect = caja(page, selectores)
    page.click("#play-evo")
    t0, tiempos = time.time(), []
    while time.time() - t0 < segundos:
        page.screenshot(path=str(tmp / f"{len(tiempos):04}.png"), full_page=True, clip=rect)
        tiempos.append(time.time() - t0)
    lista = tmp / "lista.txt"
    with lista.open("w") as f:
        for k, t in enumerate(tiempos):
            dur = (tiempos[k + 1] if k + 1 < len(tiempos) else segundos) - t
            f.write(f"file '{k:04}.png'\nduration {dur:.3f}\n")
        f.write(f"file '{len(tiempos) - 1:04}.png'\n")
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lista),
                    "-vf", "fps=30,scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "18", str(destino)], check=True)
    for p in tmp.iterdir():
        p.unlink()
    tmp.rmdir()
    print(f"   {destino.name}: {len(tiempos)} cuadros en {segundos:.0f} s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=URL)
    ap.add_argument("--claro", action="store_true", help="tema claro en todas las escenas (por defecto, oscuro salvo CLARAS)")
    ap.add_argument("--solo", type=int, nargs="*", help="capturar solo estas escenas")
    a = ap.parse_args()
    RECURSOS.mkdir(exist_ok=True)
    errores = []
    with sync_playwright() as p:
        nav = p.chromium.launch()
        ctx = nav.new_context(viewport={"width": ANCHO_CSS, "height": 915}, device_scale_factor=ESCALA,
                              is_mobile=True, has_touch=True, color_scheme="light" if a.claro else "dark",
                              locale="es-PE")
        page = ctx.new_page()
        page.on("console", lambda m: errores.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errores.append(str(e)))
        page.goto(a.url, wait_until="networkidle")
        page.wait_for_selector("#kpis .kpi")
        # la barra de filtros es fija: se oculta para que no tape las secciones
        # (y la nota bajo las barras del inicio, que la narración ya dice)
        page.add_style_tag(content=".bar,.tt,#levels .note{display:none!important}")
        for n, (selectores, estado) in ESCENAS.items():
            if a.solo and n not in a.solo:
                continue
            page.emulate_media(color_scheme="light" if a.claro or n in CLARAS else "dark")
            fijar(page, **estado)
            if n in PREVIAS:
                sels, activar, desactivar = PREVIAS[n]
                page.evaluate(activar)
                page.wait_for_timeout(400)
                page.screenshot(path=str(RECURSOS / f"escena_{n}_previa.png"), full_page=True, clip=caja(page, sels))
                page.evaluate(desactivar)
                print(f"   escena_{n}_previa.png: {' + '.join(sels)}")
            if n in RESALTES:
                page.evaluate(_ENVOLVER, list(RESALTES[n]))
                page.wait_for_timeout(1200)
            rect = caja(page, selectores)
            page.screenshot(path=str(RECURSOS / f"escena_{n}.png"), full_page=True, clip=rect)
            if n in COLUMNA:
                partes = []
                for k, (sels, ancho) in enumerate(COLUMNA[n]):
                    if ancho:
                        page.set_viewport_size({"width": ancho, "height": 915})
                        page.wait_for_timeout(1000)
                    partes.append(RECURSOS / f"_columna_{n}_{k}.png")
                    page.screenshot(path=str(partes[-1]), full_page=True, clip=caja(page, sels, ancho or ANCHO_CSS))
                    if ancho:
                        page.set_viewport_size({"width": ANCHO_CSS, "height": 915})
                        page.wait_for_timeout(1000)
                lado_a_lado(RECURSOS / f"escena_{n}.png", partes, RECURSOS / f"escena_{n}.png")
                for x in partes:
                    x.unlink()
            print(f"   escena_{n}.png: {' + '.join(selectores)} ({rect['width']:.0f}x{rect['height']:.0f} px CSS)")
            if n in CLIPS:
                clip(page, selectores, RECURSOS / f"escena_{n}.mp4")
            if n in RESALTES:
                page.evaluate(_RESTAURAR, RESALTES[n][0])
        nav.close()
    print("Errores de consola:", errores or "ninguno")


if __name__ == "__main__":
    main()
