#!/usr/bin/env python3
"""Fábrica: convierte las piezas aprobadas de fabrica/cola/ en MP4 listos para Metricool.

Para cada pieza con "estado": "aprobado" y sin MP4: voz (si no la trae) → montaje
→ lote-<lunes de su fecha>/<slug>-<variante>.mp4 (≤ 9,5 MB) → sha256 → "renderizado".

Uso:  python fabrica/procesar.py            (lo lanza el workflow fabricar.yml)
      python fabrica/procesar.py --prueba   (vuelve a montar las piezas ya
            renderizadas con su propia voz y compara con su MP4; no escribe nada)
"""
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'fabrica'))
import montar  # noqa: E402
import voz  # noqa: E402

COLA = RAIZ / 'fabrica' / 'cola'
REGISTRO = RAIZ / 'fabrica' / 'registro.json'
MAX_BYTES = int(9.5 * 1024 * 1024)


def ahora():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def resumen(linea):
    print(linea)
    ruta = os.environ.get('GITHUB_STEP_SUMMARY')
    if ruta:
        with open(ruta, 'a', encoding='utf-8') as f:
            f.write(linea + '\n')


def registrar(evento):
    reg = json.loads(REGISTRO.read_text('utf-8')) if REGISTRO.exists() else {'eventos': []}
    reg['actualizado'] = ahora()
    reg['eventos'].append({'fecha': reg['actualizado'], **evento})
    reg['eventos'] = reg['eventos'][-300:]
    REGISTRO.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding='utf-8')


def piezas():
    for ruta in sorted(COLA.glob('*/*.json')):
        yield ruta, json.loads(ruta.read_text('utf-8'))


def lote_de(fecha_iso):
    d = dt.date.fromisoformat(fecha_iso[:10])
    return 'lote-' + (d - dt.timedelta(days=d.weekday())).isoformat()


def sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, 'rb') as f:
        for bloque in iter(lambda: f.read(1 << 20), b''):
            h.update(bloque)
    return h.hexdigest()


def psnr(a, b):
    out = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(a), '-i', str(b), '-lavfi', 'psnr', '-f', 'null', '-'],
                         capture_output=True, text=True).stderr
    m = re.findall(r'average:(\S+)', out)
    return m[-1] if m else '?'


def prueba():
    fallos = 0
    for ruta, p in piezas():
        mp4 = p.get('salida', {}).get('mp4')
        if not mp4 or not (RAIZ / mp4).exists() or 'voz' not in p:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            nuevo = pathlib.Path(tmp) / 'prueba.mp4'
            montar.montar(ruta, nuevo)
            v = psnr(nuevo, RAIZ / mp4)
        ok = v == 'inf' or (v not in ('?', '') and float(v) >= 45)
        fallos += not ok
        resumen(f"- {'✅' if ok else '❌'} {p['slug']}: PSNR {v} dB frente a {mp4}")
    sys.exit(1 if fallos else 0)


def main():
    hechas, avisos = 0, []
    for ruta, p in piezas():
        if p.get('estado') != 'aprobado':
            continue
        mp4 = p.get('salida', {}).get('mp4')
        if mp4 and (RAIZ / mp4).exists():
            continue
        try:
            if 'voz' not in p:
                creditos = voz.generar(p, ruta)
                resumen(f"- 🎙️ {p['slug']}: voz generada ({creditos} créditos, {p['voz']['origen']})")
            destino = RAIZ / lote_de(p['fecha']) / f"{p['slug']}-{p['variante']}.mp4"
            destino.parent.mkdir(exist_ok=True)
            montar.montar(ruta, destino)
            if destino.stat().st_size > MAX_BYTES:
                montar.montar(ruta, destino, crf=24)
            if destino.stat().st_size > MAX_BYTES:
                raise SystemExit(f"PARADA: {destino.name} pasa de 9,5 MB incluso con CRF 24")
            p['salida'] = {'mp4': str(destino.relative_to(RAIZ)), 'sha256': sha256(destino),
                           'bytes': destino.stat().st_size}
            p['estado'] = 'renderizado'
            p.setdefault('historial', []).append({'estado': 'renderizado', 'fecha': ahora(), 'por': 'fábrica'})
            ruta.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding='utf-8')
            registrar({'pieza': p['slug'], 'estado': 'renderizado', 'mp4': p['salida']['mp4']})
            resumen(f"- 🎬 {p['slug']} ({p['variante']}): {p['salida']['mp4']} · {p['salida']['bytes']:,} B")
            hechas += 1
        except voz.SinClave as e:
            avisos.append(f"{p['slug']}: {e}")
        except voz.TopeAlcanzado as e:
            avisos.append(f"{p['slug']}: tope de créditos, {e}")
            ruta.write_text(json.dumps({**p, 'revisar': str(e)}, ensure_ascii=False, indent=1), encoding='utf-8')
    for a in avisos:
        resumen(f'- ⚠️ {a}')
    resumen(f'Piezas renderizadas: {hechas}')
    sys.exit(1 if avisos else 0)


if __name__ == '__main__':
    prueba() if '--prueba' in sys.argv else main()
