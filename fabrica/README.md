# Fábrica de vídeos de Don Bigotes

Hace voz y montaje en GitHub Actions, sin el Mac. Es la fase 1 del plan de redes aprobado por Xavi el 22-oct-2026.
Este repositorio es **público**: aquí solo entra material publicable. Nada de claves, audio del cuento, capturas con datos ni código privado.

## Flujo

| Paso | Quién | Qué toca |
|---|---|---|
| Día 25 de cada mes | Tarea de Claude | Crea las piezas del mes siguiente en `cola/AAAA-MM/` con `"estado": "preparado"` y avisa a Xavi |
| OK mensual | Xavi, en el chat | Claude pasa a `"aprobado"` las piezas que Xavi acepta (texto exacto) |
| Al hacer push a `cola/` | `fabricar.yml` | Voz (ElevenLabs) → montaje → `lote-<lunes>/<slug>-<variante>.mp4` → `"renderizado"` |
| Martes | Tarea de Claude | Programa en Metricool lo renderizado para 48 h después y manda a Xavi el enlace para vetarlo → `"programado"`, con los ids |
| Jueves | Tarea de Claude | Comprueba en Metricool lo programado y lo publicado → `"publicado"` y actualiza `registro.json` |
| Cada día, 07:00 UTC | `vigilante.yml` | Si algo falla, abre una issue «vigilante» (GitHub manda un email a Xavi) |

**«Aprobado» nunca significa programado, y «programado» nunca significa publicado.** El estado se confirma leyendo Metricool, no el registro.

## Pieza (`cola/AAAA-MM/<fecha>_<slug>.json`)

```json
{
  "slug": "existe", "fecha": "2026-11-03T20:00:00+01:00", "variante": "419",
  "plantilla": "ilustraciones", "estado": "preparado",
  "frases": ["…", "…", "Busca Don Bigotes en tu tienda de apps…"],
  "gancho": "¿Existe el Ratón Pérez?", "categoria": "La app del Ratón Pérez",
  "planos": [{"archivo": "cap10-1.webp", "cx": 0.371, "deriva": 0.02}],
  "textos": {"tiktok": "…", "youtube_titulo": "…", "youtube_descripcion": "…", "youtube_para_ninos": false},
  "historial": [{"estado": "aprobado", "fecha": "…", "por": "Xavi"}]
}
```

- `planos`: uno por frase salvo la última, que es el cierre con Don Bigotes saludando. `cx` es el centro horizontal del encuadre (0-1); `deriva`, cuánto se desplaza durante el plano.
- `voz`: la escribe la fábrica (audio + palabras con tiempos). Si una pieza ya la trae, no se genera otra.
- `revisar`: la fábrica lo añade si whisper no oye exactamente el guion o si se acabó el tope de créditos.

## Reglas que aplica

- Guion **sin exclamaciones**. Voz oficial `QOC5LfBZ4RxewWwU1ntm`, modelo `eleven_v3`.
- Tope de **8.000 créditos de ElevenLabs por mes natural** (`consumo.json`). Si no cabe, no se genera.
- MP4 de ≤ 9,5 MB, en 1080×1920 a 30 fps, H.264 + AAC y −14 LUFS.
- Al programar:
  - TikTok: IA y contenido promocional de marca propia (`isAigc`, `commercialContentOwnBrand`);
  - YouTube: `isAiGeneratedContent`; la audiencia («para niños» o no) se decide pieza a pieza.
- Sin niños reales ni realistas. Los llamados a la acción, siempre a los adultos. No llamar «gratis» a lo que es de pago.

## Comprobaciones

- `python fabrica/procesar.py --prueba`, o el workflow con «prueba» marcado: vuelve a montar lo ya hecho y lo compara con su MP4 (PSNR).
- `python fabrica/vigilante.py`: estado actual. Avisa de verdad solo si `config.json` tiene `"vigilante_activo": true`.

## Secret necesario

`ELEVENLABS_API_KEY` en *Settings → Secrets and variables → Actions*. Lo pone Xavi; la fábrica nunca lo escribe en ningún archivo.
