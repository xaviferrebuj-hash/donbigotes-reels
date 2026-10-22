#!/usr/bin/env python3
"""Voz de Don Bigotes para una pieza de la fábrica (ElevenLabs).

- Clave: variable de entorno ELEVENLABS_API_KEY (secret del repo). Nunca en archivos.
- Voz oficial QOC5LfBZ4RxewWwU1ntm, modelo eleven_v3, una sola pista continua.
- Guion SIN exclamaciones (regla de Xavi para todo lo que pase por TTS).
- Tiempos por palabra: endpoint with-timestamps; si no los da, faster-whisper
  (modelo small, CPU) y se marca la pieza para revisar si no oye el guion.
- Tope: 8.000 créditos por mes natural, contados en fabrica/consumo.json.
  Antes de llamar se estima ~0,55 créditos por carácter; si no cabe, no se genera.
"""
import base64
import datetime as dt
import json
import math
import os
import pathlib
import time
import urllib.error
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CONSUMO = RAIZ / 'fabrica' / 'consumo.json'
VOICE_ID = 'QOC5LfBZ4RxewWwU1ntm'
MODELO = 'eleven_v3'
TOPE_MES = 8000
API = 'https://api.elevenlabs.io/v1/text-to-speech'


class SinClave(Exception):
    pass


class TopeAlcanzado(Exception):
    pass


def _consumo():
    return json.loads(CONSUMO.read_text('utf-8')) if CONSUMO.exists() else {}


def _apunta(creditos, slug):
    datos = _consumo()
    mes = dt.date.today().strftime('%Y-%m')
    datos.setdefault(mes, {'creditos': 0, 'piezas': []})
    datos[mes]['creditos'] += creditos
    datos[mes]['piezas'].append({'slug': slug, 'creditos': creditos,
                                 'fecha': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')})
    CONSUMO.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding='utf-8')


def _libre():
    mes = dt.date.today().strftime('%Y-%m')
    return TOPE_MES - _consumo().get(mes, {}).get('creditos', 0)


def _pide(url, cuerpo, clave, accept):
    pet = urllib.request.Request(url, data=json.dumps(cuerpo).encode(),
                                 headers={'xi-api-key': clave, 'accept': accept,
                                          'content-type': 'application/json'})
    for intento in range(1, 4):
        try:
            with urllib.request.urlopen(pet, timeout=240) as r:
                return r.read(), r.headers
        except urllib.error.HTTPError as e:
            cuerpo_err = e.read().decode(errors='replace')[:300]
            if e.code in (429, 500, 502, 503) and intento < 3:
                time.sleep(15 * intento)
                continue
            raise RuntimeError(f'HTTP {e.code}: {cuerpo_err}')
        except Exception as e:  # red
            if intento < 3:
                time.sleep(10)
                continue
            raise
    raise RuntimeError('sin respuesta de ElevenLabs')


def _palabras_de_alineacion(al):
    chars = al['characters']
    ini = al['character_start_times_seconds']
    fin = al['character_end_times_seconds']
    palabras, cur, t0, t1 = [], '', None, None
    for c, a, b in zip(chars, ini, fin):
        if c.isspace():
            if cur:
                palabras.append({'t': round(t0, 3), 'fin': round(t1, 3), 'w': cur})
            cur, t0 = '', None
            continue
        if t0 is None:
            t0 = a
        cur += c
        t1 = b
    if cur:
        palabras.append({'t': round(t0, 3), 'fin': round(t1, 3), 'w': cur})
    return palabras


def _whisper(ruta, texto):
    from faster_whisper import WhisperModel  # solo si hace falta
    modelo = WhisperModel('small', device='cpu', compute_type='int8')
    segs, _ = modelo.transcribe(str(ruta), language='es', word_timestamps=True, vad_filter=True,
                                condition_on_previous_text=False)
    oidas = [{'t': round(p.start, 3), 'fin': round(p.end, 3), 'w': p.word.strip()}
             for s in segs for p in (s.words or [])]
    guion = texto.split()
    revisar = [w['w'] for w in oidas] != guion
    if len(oidas) == len(guion):  # mismos tiempos, palabras del guion
        oidas = [{**o, 'w': g} for o, g in zip(oidas, guion)]
    return oidas, revisar


def generar(pieza, ruta_pieza):
    """Genera audio y palabras, actualiza pieza['voz'] y devuelve los créditos estimados."""
    texto = ' '.join(pieza['frases'])
    if '!' in texto or '¡' in texto:
        raise SystemExit(f"PARADA: {pieza['slug']} lleva exclamaciones (regla TTS)")
    carpeta = pathlib.Path(ruta_pieza).parent / 'audio'
    carpeta.mkdir(exist_ok=True)
    base = f"{pieza['slug']}-{pieza['variante']}"
    mp3 = carpeta / f'{base}.mp3'
    js = carpeta / f'{base}.json'
    if mp3.exists() and js.exists():  # ya pagada en una ejecución anterior: no se regenera
        pieza['voz'] = {'audio': str(mp3.relative_to(RAIZ)), 'palabras': str(js.relative_to(RAIZ)),
                        'origen': f'ElevenLabs {MODELO} (reutilizada)', 'creditos': 0}
        return 0
    estimado = math.ceil(len(texto) * 0.55)
    if estimado > _libre():
        raise TopeAlcanzado(f'{pieza["slug"]}: necesita ~{estimado} créditos y quedan {_libre()} este mes')
    clave = os.environ.get('ELEVENLABS_API_KEY', '').strip()
    if not clave:
        raise SinClave('falta el secret ELEVENLABS_API_KEY en el repo')
    cuerpo = {'text': texto, 'model_id': MODELO}
    origen, revisar = 'with-timestamps', False
    try:
        datos, cab = _pide(f'{API}/{VOICE_ID}/with-timestamps?output_format=mp3_44100_128', cuerpo, clave,
                           'application/json')
        resp = json.loads(datos)
        al = resp.get('alignment') or resp.get('normalized_alignment')
        if not al:
            raise RuntimeError('sin alineación')
        mp3.write_bytes(base64.b64decode(resp['audio_base64']))
        palabras = _palabras_de_alineacion(al)
    except RuntimeError as e:
        if 'HTTP 401' in str(e) or 'HTTP 402' in str(e):
            raise
        print(f'  with-timestamps no sirvió ({e}); voz normal + whisper')
        datos, cab = _pide(f'{API}/{VOICE_ID}?output_format=mp3_44100_128', cuerpo, clave, 'audio/mpeg')
        mp3.write_bytes(datos)
        palabras, revisar = _whisper(mp3, texto)
        origen = 'whisper-small'
    try:
        creditos = int(float(cab.get('character-cost') or estimado))
    except ValueError:
        creditos = estimado
    _apunta(creditos, pieza['slug'])
    js.write_text(json.dumps(palabras, ensure_ascii=False, indent=1), encoding='utf-8')
    pieza['voz'] = {'audio': str(mp3.relative_to(RAIZ)), 'palabras': str(js.relative_to(RAIZ)),
                    'origen': f'ElevenLabs {MODELO} ({origen})', 'creditos': creditos}
    if revisar:
        pieza['revisar'] = 'whisper no oye exactamente el guion: escuchar antes de aprobar'
    return creditos
