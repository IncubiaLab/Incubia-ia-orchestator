# Revisión de goals y ADR — fuente de la etapa 2

Consulta: 2026-10-06, America/Bogota. Se revisaron el proyecto, todas sus issues, los documentos ADR-003/004/005/023 y el registro de ADR; se leyeron las copias locales aceptadas 001/006/007. Estado de issue y estado arquitectónico se distinguen: Done no prueba implementación, y una propuesta implementada no queda ratificada automáticamente.

## Goals de plataforma y contribución de esta etapa

El [proyecto Incubia Platform MVP](https://linear.app/hector-cruz/project/incubia-platform-mvp-67f3883cb76e) continúa In Progress. Busca integración externa, chat contextual, multi-organización, auditoría, leads y fallback a caso; referencia ≤5 s de respuesta. No se encontró una issue específica de Telegram entre las issues del proyecto consultadas. Los G1–G7 y E2-01–12 son planificación local nueva.

| Fuente Linear | Estado observado | Contribución de etapa 2 / pendiente |
| --- | --- | --- |
| [HEC-12 · AI Orchestrator](https://linear.app/hector-cruz/issue/HEC-12) | In Progress | G1–G4/G6: contexto y orquestación neutral. Su DoD incluye tools + retrieval, que permanecen pendientes. |
| [HEC-11 · Puertos de IA](https://linear.app/hector-cruz/issue/HEC-11) | In Progress | BASE documenta ownership, contratos y errores del corte; Retrieval/Embedding/Knowledge/Tools no se implementan aquí. |
| [HEC-7 · Tenant boundary](https://linear.app/hector-cruz/issue/HEC-7) | In Progress | Binding de prueba y aislamiento de scopes; no equivale a identidad/tenancy de producción. |
| [HEC-9 · Conectores externos](https://linear.app/hector-cruz/issue/HEC-9) | In Progress | Compartir disciplina de adapters; un canal de mensajería no sustituye el conector de datos empresariales. |
| [HEC-14 · Observabilidad](https://linear.app/hector-cruz/issue/HEC-14) | Backlog | Correlación y métricas mínimas G7; no tracing/auditoría de producción completos. |
| [HEC-17 · Model Router y especialización](https://linear.app/hector-cruz/issue/HEC-17) | Backlog | Dataset y perfiles preparan evidencia. DecisionModelPort clasifica capabilities; no es ModelRouterPort, que selecciona modelos/proveedores. Sin LoRA/PEFT/distillation en este corte. |
| Hitos 04 Chatbot Core, 06 Conversation & Context, 10 MVP Validation | Avance informado: 63 %, 0 %, 0 % | Principales hitos de referencia; las fechas vigentes de Linear no son estimaciones del nuevo backlog. |

## ADR aceptados que gobiernan el diseño

| ADR / tracking | Estado verificado | Consecuencia |
| --- | --- | --- |
| [001](../../adr/ADR-ORCH-001.md) / [HEC-18](https://linear.app/hector-cruz/issue/HEC-18) | Accepted / Done | Runtime reemplazable; semántica en producto. |
| [003](../../adr/ADR-ORCH-003.md) / [HEC-19](https://linear.app/hector-cruz/issue/HEC-19) | Accepted / Done | Routing por capability, DecisionModelPort, estados de incertidumbre y policy separada. |
| [004](../../adr/ADR-ORCH-004.md) / [HEC-20](https://linear.app/hector-cruz/issue/HEC-20) | Accepted / Done | Registry, discovery y selección separados; descriptores versionados e in-process. No define por sí mismo prompting interno. |
| [005](../../adr/ADR-ORCH-005.md) / [HEC-21](https://linear.app/hector-cruz/issue/HEC-21) | Accepted / Done | Operaciones externas propuestas por agentes pasan por Tool Layer; descriptores no autorizan y declaran side effects. |
| [006](../../adr/ADR-ORCH-006.md) / [HEC-22](https://linear.app/hector-cruz/issue/HEC-22) | Accepted / Done | PEP/PDP, autoridad acotada, fail-closed; ningún prompt amplía permisos. |
| [007](../../adr/ADR-ORCH-007.md) / [HEC-23](https://linear.app/hector-cruz/issue/HEC-23) | Accepted / Done | Requests/outcomes tipados e IDs separados; nada de GraphState en contratos. |

Las copias completas de 003/004/005 se incorporaron a `docs/adr/` en esta revisión. Los documentos de etapa 1 se conservan como historia: su afirmación de que 003 seguía pendiente está desactualizada frente al documento de Linear aceptado. La implementación local con keywords tampoco acredita la implementación completa de ese ADR.

## Decisiones abiertas y efecto sobre el roadmap

| ADR | Estado al consultar | Tratamiento |
| --- | --- | --- |
| 008/009 | Backlog, HEC-33/34 | Persistencia y memoria: definir recorte local durable/retención en H0. |
| 012 | Proposed / In Progress, HEC-24 | Sin human approval/resume funcional en etapa 2. |
| 013 y 017–020 | Proposed / Todo, HEC-25–29 | Mantener propuestas locales de LLM, estructura, composición, estado y pruebas sin ratificarlas. |
| 014/015 | Backlog, HEC-37/38 | Correlación mínima y retries acotados del piloto; no solución global de observabilidad/fallbacks. |
| [021 / HEC-30](https://linear.app/hector-cruz/issue/HEC-30) | In discussion / Proposed; In Progress | Enforcement de idempotencia, UNKNOWN_EFFECT y side-effect journal aún abiertos. El piloto requiere política local explícita. |
| [022 / HEC-31](https://linear.app/hector-cruz/issue/HEC-31) | Proposed / In Progress | No introducir un motor genérico de monedas/ejes/círculos para este corte. |
| [023 · transmisión](https://linear.app/hector-cruz/document/adr-orch-023-contrato-de-transmision-entre-capas-y-capabilities-0ab6511052a2) | Proposed / Open for validation; Not ratified | Orienta envelope, scope, errores y no repetir efectos sin garantías; complementa 007. |
| [024 · topología](https://linear.app/hector-cruz/document/adr-orch-024-topologia-de-despliegue-del-orchestrator-499b69ecf859) | Proposed / Open for validation, según registro | Monolito modular como propuesta del piloto; sin microservicios/broker por anticipado. |

Fuente del inventario abierto: [registro de ADR](https://linear.app/hector-cruz/document/incubia-mvp-adr-register-3fce75c3bbce). Se verificó además el documento completo de 023; para 024 se usa el resumen del registro, no una revisión completa del ADR.

Idempotencia y arquitectura hexagonal son preocupaciones relacionadas pero distintas: la frontera puerto/adapter evita acoplamiento al canal; inbox/outbox y estados de efecto controlan repeticiones. Ninguna de las dos implica automáticamente la otra. La arquitectura ya contempla la idempotencia; el código actual todavía no la implementa para mensajería.
