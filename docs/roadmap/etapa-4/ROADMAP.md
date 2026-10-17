# Roadmap — etapa 4: agentes especializados y handoff gobernado

Fecha de planteamiento: 2026-10-15. Estado: **propuesta**, sin gate aprobado ni implementación atribuida a E4.

## Propósito y punto de partida

Evolucionar General, Ventas y Marketing desde perfiles seleccionados al inicio del turno hacia agentes que pueden **solicitar** una transferencia secuencial de responsabilidad cuando otra capability aporta una mejor respuesta. El coordinador de aplicación decide el destino; el agente origen no invoca a otro agente ni concede permisos. Se conserva el routing por capability, los perfiles y descriptores versionados, Conversation canónica, `GraphState` privado del runtime y la autorización por deployment, tenant y actor.

La base E3 ya ofrece Agent Discovery/Selection parcial y contratos de Tool Registry/Discovery/Executor. `HandleInbound` selecciona un solo perfil por mensaje y el runtime local todavía enruta por términos; no existe `HandoffCoordinator` ni `AgentRun` persistente. E3-1/E3-2 están listos para decisión. La etapa 4 puede diseñarse y probarse con fakes mientras se cierran esos gates; ninguna prueba E4 sustituye su evidencia.

## Resultados buscados

| Resultado | Criterio de salida |
| --- | --- |
| Perfiles reforzados | General, Ventas y Marketing declaran propósito, capabilities, límites, evidencia requerida, contrato de salida y criterios para solicitar handoff; configuración versionada sin rutas hardcodeadas por agente. |
| Handoff secuencial | `HandoffRequest` tipada; Discovery → Selection → Policy decide destino; `HandoffContext` mínimo, inmutable y versionado; un owner activo por ejecución. |
| Recuperación segura | Transición durable con revisión, claim/fencing e idempotencia; un crash o replay no activa dos agentes ni duplica efectos. |
| Control de calidad | Evals de rutas útiles y negativas, contexto mínimo, DENY, revocación, loops, deadline, errores y recuperación; auditoría correlacionada sin contenido sensible completo. |
| Integración desacoplada | Si un caso de uso requiere datos externos, el destino accede mediante contratos y policy vigentes. La elección de sistema, fuente y proveedor queda pendiente de requisitos de empresas usuarias. |

## Secuencia propuesta

| Hito | Trabajo | Gate propuesto |
| --- | --- | --- |
| E4-0. Baseline | Inventario de rutas CLI/Telegram/HTTP, contratos E2/E3, evaluación de tres perfiles, ADR-011/012/016/021 y casos de uso. | Matriz de comportamiento actual, decisiones abiertas y dataset dev/val congelado. |
| E4-1. Perfiles y decisiones | Revisar capacidades, evidencia, fallback, solicitudes de handoff y salidas estructuradas por perfil. Separar decisión de capability, elección de agente y ejecución. | Cambio de versión de perfil sin tocar router/grafo; casos ambiguos y unsupported controlados. |
| E4-2. Handoff local | Contratos framework-neutral y `HandoffCoordinator`; política de autoridad efectiva, contexto mínimo, límites de hops/deadline y lineage. | Transiciones entre perfiles actuales con fakes; DENY/REQUIRE_APPROVAL no activan destino; sin loops. |
| E4-3. Durabilidad | `AgentRun` y handoff en Conversation/UoW, ownership atómico, claim/fencing, recovery y eventos auditables. | Replay, competencia, crash antes/después de commit y revocación: un solo owner, cero doble ejecución. |
| E4-4. Integración y evaluación | Conectar rutas reales de entrada sin cambiar fronteras; trazabilidad y campaña de calidad/latencia/costo. Integrar fuentes externas sólo tras definir el caso de uso. | Gates E3 requeridos cerrados para piloto integrado; rúbrica de utilidad y seguridad pasada, decisión de release registrada. |

La primera entrega vertical se define en E4-0 a partir de escenarios y necesidades de las empresas usuarias. Se valida primero con datos sintéticos: un perfil solicita otra capability, el coordinador verifica discovery y policy, y el destino recibe sólo el contexto autorizado. Si no hay destino elegible o vence el deadline, el origen devuelve una salida controlada según el contrato. No se fija una consulta comercial, fuente de datos ni secuencia concreta de perfiles antes de ese levantamiento.

## Dependencias y decisiones

- [ADR-ORCH-011 en Linear](https://linear.app/hector-cruz/document/adr-orch-011-handoff-agent-agent-219c880b90bf) sigue Proposed. E4-2/E4-3 deben aportar evidencia para aceptarlo; el roadmap no cambia su estado.
- ADR-012 debe definir escalación humana, pausa y resume antes de implementarlos. ADR-016 debe concretar la compatibilidad con runtimes externos antes de un handoff remoto. ADR-021 bloquea mutations y acciones externas por agente.
- E3-1/E3-2 sustentan autoridad durable y aislamiento. Los demás gates E3 se evalúan según el alcance del piloto integrado. El diseño offline E4 puede avanzar en paralelo.
- El milestone 03 de Linear aborda integración externa. La selección de un sistema piloto depende del tipo de empresas usuarias, sus sistemas y permisos; aún no está decidida.

## Alcance excluido en este corte

Planificación autónoma de equipos de agentes, ejecución paralela, A2A remoto, transferencia a humanos, envío proactivo y mutations empresariales. Cualquier ampliación exige contrato, policy y evidencia específicos; no se infiere de que exista un handoff local.

## Documentos

- [AGENTES-HANDOFF](AGENTES-HANDOFF.md): comportamiento por perfil, contrato y estados.
- [PLAN-E4](PLAN-E4.md): entregables, pruebas y orden de implementación.
