# Verificación — etapa 2

Estado al 2026-10-06: **H0–H1 verificados por tests unitarios; H2 en validación; gates A/B/C pendientes**. Pruebas E2E, modelos reales y envíos de Telegram sin ejecutar en este hito.

## Matriz de pruebas prevista

| Área / goals | Prueba significativa | Resultado requerido |
| --- | --- | --- |
| Perfiles / G1 | Configuración incompleta, versión duplicada, perfil nuevo sin editar router | Fallo de configuración seguro; registro explícito y extensible. |
| Contexto / G2 | Tres turnos, Ventas → Marketing → Ventas, límite y campos faltantes | Contexto pertinente, pares completos, datos compartidos permitidos; nada de instrucciones del perfil previo. |
| Aislamiento / G2/G6 | Dos tenants, actores y chats; replay con scope distinto | Cero lectura/entrega cruzada; binding confiable rechaza suplantación. |
| Routing / G3 | Dataset v2, paráfrasis, ambiguos, unsupported, capability conocida | Umbral G3; sin clasificador cuando operación está fijada; señales sin autoridad. |
| Discovery / G3 | Dos versiones, disabled, scope ajeno y candidato incompatible | Conjunto correcto y selección estable; sin hardcoding de agentes en router. |
| Governance / G3/G6 | DENY, INDETERMINATE y REQUIRE_APPROVAL en inferencia/entrega | Cero operación protegida no autorizada; no afirmar resume funcional. |
| Contratos / G4 | JSON round-trip, schema desconocido, CLI y dos canales fake | Variantes/IDs preservados; error seguro por versión incompatible. |
| Fronteras / G4 | Imports directos/transitivos y canarios internos | Sin SDKs de canal/runtime en core; sin instrucciones/secretos en respuesta pública o logs. |
| Inbox / G5 | Mismo update secuencial, concurrente, tras restart y payload conflictivo | Una ejecución lógica, una incorporación de historia, IDs estables; conflicto rechazado. |
| Outbox / G5 | Doble worker, caída antes de envío y tras éxito remoto sin commit | Una reserva; SENT no reenvía; SENDING incierto no se repite automáticamente. |
| Polling / G5/G6 | Lote parcialmente persistido, caída antes de offset, tipos no soportados | Ningún evento aceptado perdido por confirmar anticipadamente; replay seguro. |
| Telegram / G6 | Límites/Unicode, destino incorrecto, API rate-limit, timeout | Mapping seguro y política de retry/deadline consistente; UNKNOWN_EFFECT cuando corresponda. |
| Calidad / G7 | 12 escenarios revisados con proveedor real | Rúbrica de GOALS, ≥80 % y cero fallos críticos; fake no acredita calidad. |
| Operación / G7 | Arranque limpio, reinicio, recuperación y retención | Guía repetible, versiones registradas y logs sin payloads/secretos. |

La suite automatizada usa fakes y transporte simulado con bloqueo de red; los repositorios durables se prueban con almacenamiento temporal y reapertura desde otro proceso cuando corresponda. El E2E real se ejecuta aparte, no desde la suite local por defecto.

## Evidencias de gates

| Gate | Estado | Evidencia que adjuntar |
| --- | --- | --- |
| A — core/canal sin red | Pendiente | Commit/configuración, comando de suite, resultado, pruebas de caídas y conteos de inferencia/entrega. |
| B — Telegram + fake | Pendiente | Fecha, runner/configuración sin secretos, tres turnos, dos chats, rechazo de desconocidos, replay y reinicio. |
| C — calidad/cierre | Pendiente | Modelos/versiones, datasets, matriz de confusión, rúbrica, muestras de latencia, tokens/costos y fuente de precios vigente. |

Para latencia registrar por separado clasificación, generación y entrega; si se presentan percentiles, declarar número de muestras. Costo desconocido se registra como no disponible, no cero. Los IDs de Telegram se pseudonimizan en evidencia compartida. No incluir tokens, `.env`, transcripciones privadas ni URLs con credenciales.

## Plantilla del informe de cierre

- Fecha, commit y versiones de contratos/perfiles/modelos/configuración.
- Objetivo G1–G7, comando o procedimiento y evidencia resultante.
- Dataset/partición, aciertos por clase y revisión de fallos críticos.
- Incidentes: duplicados, restart, efecto incierto y decisión de recuperación.
- Medición: muestras, latencias, tokens, costo estimado y límites de presupuesto.
- Limitaciones pendientes y gates que permanecen abiertos.

## Validación de esta planificación

La revisión documental debe comprobar enlaces relativos, correspondencia entre goals/hitos/backlog, estados de ADR y distinción entre propuestas y capacidades existentes. Esa validación no cierra ningún gate técnico de etapa 2.

Resultado del 2026-10-06: nueve documentos de etapa 2 creados; enlaces relativos comprobados sin destinos faltantes y `git diff --check` sin errores. Se revisó la correspondencia G1–G7 ↔ H0–H5 ↔ E2-01–12. No se ejecutó la suite del producto porque el cambio es exclusivamente documental.
