#!/usr/bin/env python3
"""Vigilante de la fábrica, independiente de Claude (workflow vigilante.yml, diario).

Avisa (job en rojo + issue «vigilante» en el repo, que GitHub manda por email) si:
  (a) no hay ninguna pieza «programado» con fecha en los próximos 7 días;
  (b) una pieza «aprobado» lleva más de 48 h sin MP4;
  (c) fabrica/registro.json lleva más de 8 días sin tocarse.
Mientras fabrica/config.json diga "vigilante_activo": false, solo informa y no avisa.
"""
import datetime as dt
import json
import os
import pathlib
import subprocess

RAIZ = pathlib.Path(__file__).resolve().parent.parent
F = RAIZ / 'fabrica'


def fecha(s):
    d = dt.datetime.fromisoformat(s.replace('Z', '+00:00'))
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def revisar():
    ahora = dt.datetime.now(dt.timezone.utc)
    problemas = []
    piezas = [json.loads(r.read_text('utf-8')) for r in sorted((F / 'cola').glob('*/*.json'))]
    proximas = [p for p in piezas if ahora <= fecha(p['fecha']) <= ahora + dt.timedelta(days=7)]
    if not any(p.get('estado') in ('programado', 'publicado') for p in proximas):
        problemas.append('No hay ningún vídeo programado para los próximos 7 días.')
    for p in piezas:
        if p.get('estado') != 'aprobado':
            continue
        aprob = [h for h in p.get('historial', []) if h.get('estado') == 'aprobado']
        if aprob and ahora - fecha(aprob[-1]['fecha']) > dt.timedelta(hours=48):
            problemas.append(f"«{p['slug']}» está aprobado desde hace más de 48 h y la fábrica no lo ha montado.")
    reg = F / 'registro.json'
    if reg.exists():
        act = json.loads(reg.read_text('utf-8')).get('actualizado')
        if act and ahora - fecha(act) > dt.timedelta(days=8):
            problemas.append('El registro de la fábrica lleva más de 8 días sin moverse: las tareas de Claude no están corriendo.')
    return problemas


def avisar(problemas):
    cuerpo = '\n'.join(f'- {p}' for p in problemas)
    cuerpo += '\n\nQué hacer: dile a Claude en el proyecto Don Bigotes «el vigilante de la fábrica ha avisado».'
    env = {**os.environ}
    abiertas = subprocess.run(['gh', 'issue', 'list', '--label', 'vigilante', '--state', 'open', '--json', 'number',
                               '--jq', '.[0].number'], capture_output=True, text=True, env=env).stdout.strip()
    if abiertas:
        subprocess.run(['gh', 'issue', 'comment', abiertas, '--body', cuerpo], env=env)
    else:
        subprocess.run(['gh', 'label', 'create', 'vigilante', '--color', 'B60205', '--force'], env=env)
        subprocess.run(['gh', 'issue', 'create', '--title', 'Fábrica de vídeos: algo no va', '--label', 'vigilante',
                        '--body', cuerpo], env=env)


if __name__ == '__main__':
    cfg = json.loads((F / 'config.json').read_text('utf-8'))
    problemas = revisar()
    resumen = os.environ.get('GITHUB_STEP_SUMMARY')
    texto = '\n'.join(f'- ⚠️ {p}' for p in problemas) or '- ✅ Todo en orden'
    if resumen:
        with open(resumen, 'a', encoding='utf-8') as f:
            f.write(texto + '\n')
    print(texto)
    if problemas and cfg.get('vigilante_activo'):
        avisar(problemas)
        raise SystemExit(1)
