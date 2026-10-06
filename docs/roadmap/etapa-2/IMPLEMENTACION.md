# Plan de implementación — etapa 2

Estado: backlog local con progreso (T01–T04 completados 2026-10-06; T05+ activos). No son issues creados en Linear; estimaciones fijas por hito.

| ID / hito | Trabajo y entregable | Depende de | Estado | Aceptación |
| --- | --- | --- | --- | --- |
| E2-01 / H0 | Concretar BASE: schemas, ownership, errores, compatibilidad y firmas sync/async | Revisión LINEAR-ADR | ✅ DONE | Contratos de routing, contexto y canal revisables; ADR-007 preservado; excepciones/decisiones locales registradas. |
| E2-02 / H0 | Fijar catálogo de capabilities, presupuestos, retención, scope de piloto y persistencia | E2-01 | ✅ DONE | Configuración versionada; estrategia para contador real; claves/estados de ledger acordados. |
| E2-03 / H1 | Extraer perfiles versionados y paquetes de contexto | E2-02 | ✅ DONE | Matriz AGENTES validada, campos faltantes explícitos, datos sin secretos y sin permisos implícitos. |
| E2-04 / H1 | ContextBuilder y conversación canónica con selección por specialty | E2-03 | 🔄 IN_PROGRESS | Tres turnos, cambio de perfil, presupuesto e aislamiento con fixtures. |
| E2-05 / H2 | DecisionModelPort, fake, `OpenAIDecisionModel` (salida JSON schema `{status, capability, confidence}`) y CapabilityResolver | E2-02/E2-04 | 🔄 IN_PROGRESS | Estados tipados; JSON inválido → AMBIGUOUS; comando explícito `/ventas`, `/marketing`, `/general` resuelve sin clasificador; G3 medido sobre `val` frente al baseline de keywords. |
| E2-06 / H2 | AgentDescriptor, registry in-process, discovery y selección | E2-03/E2-05 | 🔄 IN_PROGRESS | Candidatos filtrados; disabled/fuera de scope excluidos; añadir versión sin tocar router. |
| E2-07 / H2 | Mover decisiones de producto a Application e integrar request contextualizado al runtime | E2-04/E2-06 | 🔄 IN_PROGRESS | Grafo delgado, PEP mantenidos, contratos serializables y CLI compatible. |
| E2-08 / H3 | ResponseContextPort y entrega neutral con dos adapters fake | E2-07 | ⏳ PENDING | Misma contextualización sin tipos del canal; filtrado de datos internos y fallos de formato probados. |
| E2-09 / H3 | Repositorios durables, inbox/outbox, reservas, revisión conversacional y recuperación | E2-02/E2-08 | ⏳ PENDING | Duplicados concurrentes/reinicio y UNKNOWN_EFFECT comprobados; cerrar Gate A. |
| E2-10 / H4 | Adapter Telegram inbound/outbound, binding confiable y runner polling | E2-09 | ⏳ PENDING | Mapping, errores de API, offset, destinos y secretos probados sin red. |
| E2-11 / H4 | Piloto Telegram + FakeLLM y runbook de recuperación | E2-10 | ⏳ PENDING | Evidencia del Gate B según TELEGRAM; no atribuir calidad al fake. |
| E2-12 / H5 | Evaluar Decision Model/perfiles reales; registrar calidad, latencia/costo y limitaciones | E2-11 y presupuesto disponible | ⏳ PENDING | G1–G7 y Gate C; discrepancias documentadas, sin cerrar goals de plataforma ajenos al corte. |

## Rutas objetivo

Rutas relativas a `src/incubia_orchestrator/`; se crean cuando se implementa el ticket, no como carpetas vacías por anticipado.

| Ruta | Cambio previsto |
| --- | --- |
| `modules/orchestration/domain/` | Perfiles, capabilities, descriptores y decisiones neutrales. |
| `modules/orchestration/application/` | Resolución, discovery/selection, construcción de contexto especialista y planificación del request. |
| `modules/orchestration/ports/` | DecisionModelPort y AgentDiscoveryPort; registry administrativo solo si el uso lo necesita. |
| `modules/orchestration/adapters/` | Decision Model fake/real y registry/discovery in-process. |
| `modules/conversation/{domain,application,ports,adapters}/` | Estado canónico, contextualización pública, repositorios e inbox/outbox; adapters de canal en `adapters/channels/telegram/`. |
| `modules/identity_tenant/` | Binding configurado del piloto y resolución confiable; no un IdP completo. |
| `foundation/contracts/` | Solo tipos compartidos, versionados y mínimos; no catálogo de todo el producto. |
| `bootstrap/` | Composición de perfiles, puertos, adapters, credenciales y runner. |
| `interfaces/cli/` | Compatibilidad y eventual comando de arranque del bot, sin SDKs ni reglas de dominio. |
| `tests/` y `evals/` | Casos de VERIFICACION, datasets v2 y rúbrica de perfiles. |

## Migración del prototipo

Mantener las tres etiquetas Specialty y salidas seguras. Sustituir gradualmente `profiles_for(model)` por configuración validada; desacoplar specialty de selección del modelo. El router actual puede quedar como baseline de evaluación/regresión, pero no cumple ADR-003 para interpretación semántica general. Un fake tampoco sustituye el benchmark del Decision Model.

Introducir un caso de uso multicanal que resuelva scope e identidad estable antes de llamar al runtime; conservar una fachada CLI para no romper el comando existente. Evitar deduplicar dentro de LangGraph o generar nuevamente execution_id al recibir un duplicado. Hacer explícita la transacción que escribe historia/outcome/outbox y las recuperaciones fuera de transacción durante red.

Antes de activar el adaptador real, revisar las restricciones reales de composición: la ampliación de contexto no se materializa subiendo prompts mientras el máximo permanece en 128 tokens o borrando el contador de intentos. La elección de modelo generativo puede seguir compartida por los perfiles; el Decision Model es una responsabilidad separada.
