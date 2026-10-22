#!/usr/bin/env python3
"""Montaje de una pieza de la fábrica (plantilla «ilustraciones»).

Ilustraciones del cuento + voz de Don Bigotes + subtítulos por palabra, en
1080×1920 a 30 fps. Generaliza el montaje de «existe» aprobado por Xavi el
22-oct-2026: con la pieza fabrica/cola/2026-11/2026-11-03_existe.json tiene que
salir, fotograma a fotograma, el mismo vídeo que lote-2026-11-02/existe-419.mp4.

Uso:  python fabrica/montar.py <pieza.json> <salida.mp4>
      python fabrica/montar.py <pieza.json> preview:0.8,4.5,18 <hoja.jpg>
"""
import json
import math
import pathlib
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

RAIZ = pathlib.Path(__file__).resolve().parent.parent
REC = RAIZ / 'fabrica' / 'recursos'
W, H, FPS = 1080, 1920, 30
CREMA = (255, 236, 200)
AMARILLO = (255, 213, 74)
BORDE = (20, 14, 30)
FG_Y, FG_H = 560, 820
XF = 0.35  # fundido entre planos (s)
COLA_FINAL = 3.0  # segundos de cierre tras la voz


def fuente(path, size, wght=None):
    f = ImageFont.truetype(str(path), size)
    if wght:
        try:
            f.set_variation_by_axes([wght])
        except Exception:
            pass
    return f


F_GANCHO = fuente(REC / 'fuentes/Baloo2.ttf', 92, 800)
F_SUB = fuente(REC / 'fuentes/Nunito.ttf', 62, 900)
F_MARCA = fuente(REC / 'fuentes/Baloo2.ttf', 54, 700)
F_TITULO = fuente(REC / 'fuentes/Baloo2.ttf', 132, 800)


def duracion(ruta):
    return float(subprocess.check_output(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(ruta)]))


def partir_en_frases(palabras, n_frases):
    """Corta la lista de palabras por fin de frase (. ? … !). Si no salen
    exactamente n_frases, reparte por número de palabras del guion."""
    frases, cur = [], []
    for w in palabras:
        cur.append(w)
        if w['w'].rstrip('»"\'').endswith(('.', '?', '…', '!')):
            frases.append(cur)
            cur = []
    if cur:
        frases.append(cur)
    return frases if len(frases) == n_frases else None


def partir_por_guion(palabras, guion):
    cuentas = [len(f.split()) for f in guion]
    if sum(cuentas) != len(palabras):
        raise SystemExit(f'PARADA: la transcripción tiene {len(palabras)} palabras y el guion {sum(cuentas)}')
    out, i = [], 0
    for c in cuentas:
        out.append(palabras[i:i + c])
        i += c
    return out


def limpia(p):
    return p[:-1] if p.endswith('.') else p


class Montaje:
    def __init__(self, pieza):
        self.p = pieza
        voz = pieza['voz']
        self.audio = RAIZ / voz['audio']
        palabras = json.loads((RAIZ / voz['palabras']).read_text('utf-8'))
        guion = pieza['frases']
        self.frases = partir_en_frases(palabras, len(guion)) or partir_por_guion(palabras, guion)
        self.dur_voz = duracion(self.audio)
        self.t_fin = self.dur_voz + COLA_FINAL
        if len(pieza['planos']) != len(guion) - 1:
            raise SystemExit('PARADA: hace falta un plano por frase salvo la última (la del cierre)')
        cortes = [0.0] + [self.corte(i) for i in range(len(guion) - 1)]
        self.planos = []
        for k, pl in enumerate(pieza['planos']):
            self.planos.append(('ilustraciones/' + pl['archivo'], pl.get('cx', 0.5), pl.get('deriva', 0.03),
                                cortes[k], cortes[k + 1]))
        self.planos.append(('CIERRE', 0, 0, cortes[-1], self.t_fin))
        self.i_cierre = len(self.planos) - 1
        self.cache = {}
        self._trozos()

    def corte(self, i):
        return (self.frases[i][-1]['fin'] + self.frases[i + 1][0]['t']) / 2

    def _trozos(self):
        trozos = []
        for fr in self.frases:
            act = []
            for w in fr:
                act.append(w)
                txt = ' '.join(x['w'] for x in act)
                if len(act) >= 4 or len(txt) >= 22 or w['w'].endswith(','):
                    trozos.append(act)
                    act = []
            if act:
                trozos.append(act)
        res = []
        for k, tr in enumerate(trozos):
            fin = trozos[k + 1][0]['t'] if k + 1 < len(trozos) else self.t_fin
            if k + 1 < len(trozos) and trozos[k + 1][0]['t'] - tr[-1]['fin'] > 0.5:
                fin = tr[-1]['fin'] + 0.45
            res.append((tr, tr[0]['t'], fin))
        self.trozos = res
        # cierre: la última frase en dos líneas equilibradas
        ult = self.frases[-1]
        mejor, corte = None, 1
        for k in range(1, len(ult)):
            a = len(' '.join(limpia(w['w']) for w in ult[:k]))
            b = len(' '.join(limpia(w['w']) for w in ult[k:]))
            if mejor is None or max(a, b) < mejor:
                mejor, corte = max(a, b), k
        self.lineas_cierre = (ult[:corte], ult[corte:])

    # --- imagen -------------------------------------------------------------
    @staticmethod
    def redondear(im, r):
        m = Image.new('L', im.size, 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, im.size[0] - 1, im.size[1] - 1], r, fill=255)
        return m

    @staticmethod
    def fondo_de(src):
        s = max(W / src.width, H / src.height)
        bg = src.resize((math.ceil(src.width * s), math.ceil(src.height * s)), Image.LANCZOS)
        x = (bg.width - W) // 2
        y = (bg.height - H) // 2
        bg = bg.crop((x, y, x + W, y + H)).filter(ImageFilter.GaussianBlur(40))
        return Image.blend(bg, Image.new('RGB', (W, H), (8, 10, 24)), 0.55)

    def base_plano(self, i):
        if i not in self.cache:
            arch = self.planos[i][0]
            ruta = REC / 'personaje/saludando.webp' if arch == 'CIERRE' else REC / arch
            src = Image.open(ruta).convert('RGB')
            self.cache[i] = (src, self.fondo_de(src))
        return self.cache[i]

    def cuadro_plano(self, i, t):
        arch, cx, deriva, t0, t1 = self.planos[i]
        src, bg = self.base_plano(i)
        frame = bg.copy()
        p = 0 if t1 == t0 else min(max((t - t0) / (t1 - t0), 0), 1)
        if arch == 'CIERRE':
            lado = int(820 + 30 * p)
            fg = src.resize((lado, lado), Image.LANCZOS)
            x = (W - lado) // 2
            y = 560 + (820 - lado) // 2
            sombra = Image.new('L', (lado + 60, lado + 60), 0)
            ImageDraw.Draw(sombra).rounded_rectangle([30, 30, lado + 29, lado + 29], 36, fill=150)
            sombra = sombra.filter(ImageFilter.GaussianBlur(18))
            frame.paste(Image.new('RGB', sombra.size, (0, 0, 0)), (x - 30, y - 20), sombra)
            frame.paste(fg, (x, y), self.redondear(fg, 36))
            return frame
        zoom = 1.0 + 0.07 * p
        alto = FG_H * zoom
        s = alto / src.height
        sw = src.width * s
        centro = (cx + deriva * p) * sw
        izq = min(max(centro - W / 2, 0), sw - W)
        top = (alto - FG_H) / 2
        box = (izq / s, top / s, (izq + W) / s, (top + FG_H) / s)
        fg = src.resize((W, FG_H), Image.LANCZOS, box=box)
        sombra = Image.new('L', (W, FG_H + 60), 0)
        ImageDraw.Draw(sombra).rectangle([0, 30, W, FG_H + 29], fill=140)
        sombra = sombra.filter(ImageFilter.GaussianBlur(20))
        frame.paste(Image.new('RGB', sombra.size, (0, 0, 0)), (0, FG_Y - 20), sombra)
        frame.paste(fg, (0, FG_Y))
        return frame

    # --- texto --------------------------------------------------------------
    @staticmethod
    def texto_borde(d, xy, s, f, fill, borde=7, anchor='mm'):
        d.text(xy, s, font=f, fill=fill, anchor=anchor, stroke_width=borde, stroke_fill=BORDE)

    @staticmethod
    def linea_karaoke(d, ws, y, t):
        esp = d.textlength(' ', font=F_SUB)
        palabras = [limpia(w['w']) for w in ws]
        anchos = [d.textlength(p, font=F_SUB) for p in palabras]
        x = (W - (sum(anchos) + esp * (len(palabras) - 1))) / 2
        for p, an, w in zip(palabras, anchos, ws):
            activo = w['t'] <= t < max(w['fin'], w['t'] + 0.12)
            d.text((x, y), p, font=F_SUB, fill=AMARILLO if activo else (255, 255, 255), anchor='lm',
                   stroke_width=7, stroke_fill=BORDE)
            x += an + esp

    def dibujar_sub(self, frame, t):
        d = ImageDraw.Draw(frame)
        if t >= self.planos[self.i_cierre][3]:
            a, b = self.lineas_cierre
            self.linea_karaoke(d, a, 380, t)
            self.linea_karaoke(d, b, 462, t)
            return
        for tr, a, b in self.trozos:
            if a <= t < b:
                self.linea_karaoke(d, tr, 450, t)
                break

    def dibujar_textos(self, frame, t):
        d = ImageDraw.Draw(frame)
        cierre = t >= self.planos[self.i_cierre][3]
        if t < self.corte(0) + 0.6 and not cierre:
            a = min(1, t / 0.25)
            self.texto_borde(d, (W // 2, 300), self.p['gancho'], F_GANCHO,
                             CREMA if a >= 1 else tuple(int(c * a) for c in CREMA), borde=8)
        if cierre:
            self.texto_borde(d, (W // 2, 240), 'Don Bigotes', F_TITULO, CREMA, borde=9)
            self.texto_borde(d, (W // 2, 1460), self.p['categoria'], F_MARCA, CREMA, borde=6)
        else:
            self.texto_borde(d, (W // 2, FG_Y + FG_H + 70), 'Don Bigotes', F_MARCA, CREMA, borde=6)
        self.dibujar_sub(frame, t)

    def frame_en(self, t):
        idx = max(i for i, p in enumerate(self.planos) if p[3] <= t)
        f = self.cuadro_plano(idx, t)
        if idx > 0 and t < self.planos[idx][3] + XF:
            prev = self.cuadro_plano(idx - 1, t)
            f = Image.blend(prev, f, (t - self.planos[idx][3]) / XF)
        if t > self.t_fin - 0.4:
            f = Image.blend(f, Image.new('RGB', (W, H), (0, 0, 0)), min(1, (t - (self.t_fin - 0.4)) / 0.4))
        self.dibujar_textos(f, t)
        return f

    # --- salida -------------------------------------------------------------
    def render(self, salida, crf=21):
        n = int(self.t_fin * FPS)
        cmd = ['ffmpeg', '-y', '-loglevel', 'error',
               '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
               '-i', str(self.audio),
               '-filter_complex', f'[1:a]apad=pad_dur=3.2,atrim=0:{self.t_fin:.3f},loudnorm=I=-14:TP=-1.5:LRA=11[a]',
               '-map', '0:v', '-map', '[a]',
               '-c:v', 'libx264', '-preset', 'slow', '-crf', str(crf), '-pix_fmt', 'yuv420p', '-profile:v', 'high',
               '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-movflags', '+faststart', '-shortest', str(salida)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        for k in range(n):
            proc.stdin.write(self.frame_en(k / FPS).tobytes())
        proc.stdin.close()
        if proc.wait() != 0:
            raise SystemExit('PARADA: ffmpeg falló')

    def hoja(self, tiempos, salida):
        ims = [self.frame_en(t).resize((360, 640)) for t in tiempos]
        hoja = Image.new('RGB', (360 * len(ims), 640))
        for k, im in enumerate(ims):
            hoja.paste(im, (360 * k, 0))
        hoja.save(salida, quality=85)


def montar(ruta_pieza, salida, crf=21):
    pieza = json.loads(pathlib.Path(ruta_pieza).read_text('utf-8'))
    m = Montaje(pieza)
    m.render(salida, crf=crf)
    return m


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    pieza = json.loads(pathlib.Path(sys.argv[1]).read_text('utf-8'))
    if sys.argv[2].startswith('preview:'):
        Montaje(pieza).hoja([float(x) for x in sys.argv[2].split(':', 1)[1].split(',')], sys.argv[3])
    else:
        Montaje(pieza).render(sys.argv[2])
    print('OK')
