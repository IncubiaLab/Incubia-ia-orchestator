# Roadmap — etapa 3: persistencia compartida, tooling y conocimiento

Fecha: 2026-10-07. **Planificación completada; implementación pendiente.** Tier 3 significa tercera etapa de desarrollo. El resultado buscado es un piloto integrado que pueda acreditar condiciones de producción con evidencia.

## Punto de partida

CLI responde y Telegram está parcialmente funcional. Gate A E2 está cerrado según su [VERIFICACION](../etapa-2/VERIFICACION.md); Gate B sigue en progreso y Gate C pendiente. El smoke real acredita una generación/contador, sin cerrar evaluación. Neon está seleccionado localmente en [ADR-025](../../adr/ADR-ORCH-025-NEON-POSTGRESQL-TIER-3.md); adapter y operación están pendientes. El baseline de Linear procede del corte heredado, que se revalida al iniciar E3-01.

## Documentos de trabajo

| Documento | Uso |
| --- | --- |
| [howto](howto.md) | Guía práctica de implementación, baseline, secuencia y validación por incremento. |
| [dessing](dessing.md) | Diseño técnico, diferencias frente al código actual y buenas prácticas de contratos, datos y ejecución. |
| [GLOSARIO](GLOSARIO.md) | Términos, IDs y estados compartidos. |
| [GOALS](GOALS.md) | G1–G9, umbrales de calidad, carga y definición de terminado. |
| [BASE](BASE.md) | Ownership, contratos, transacciones, claims y arquitectura. |
| [AGENTES](AGENTES.md) | General/Ventas/Marketing con evidencia y límites de contexto. |
| [TOOLING](TOOLING.md) | Registry/Discovery/Executor y primer conector READ. |
| [KNOWLEDGE](KNOWLEDGE.md) | Retrieval, dataset, ingestión, versiones y decisión vectorial. |
| [IMPLEMENTACION](IMPLEMENTACION.md) | Backlog E3-01…15 y dependencias. |
| [PLAN-E3](PLAN-E3.md) | Archivos objetivo, trabajo y validación por tarea. |
| [AUTOPLAN-REVIEW](AUTOPLAN-REVIEW.md) | Decisiones pendientes, responsables por designar y riesgos. |
| [LINEAR-ADR](LINEAR-ADR.md) | Fuentes, estado fechado y correspondencia con hitos de plataforma. |
| [RUNBOOK](RUNBOOK.md) | Corte de autoridad, restore, recuperación y release. |
| [VERIFICACION](VERIFICACION.md) | Matriz de evidencia y criterios de gates. |
| [PROGRESS](PROGRESS.md) | Estado actual y registro de avance. |

## Alcance

Monolito modular con contratos propios, PostgreSQL administrado en Neon para servicio compartido, identidad/tenant confiables, una integración externa READ gobernada, RetrievalPort multi-tenant con evidencia, audit y operación medidos. Leads y casos se registran internamente con autorización/consentimiento; exports externos son incrementos posteriores. CLI conserva modo offline y Telegram sus garantías de inbox/outbox.

## Hitos y gates

| Hito | Entregable / tareas | Gate de salida |
| --- | --- | --- |
| H0. Baseline y contratos | E3-01/02: inventario E2/ADR, identidad, persistencia/UoW, NFR | **E3-0:** A/B/C E2 acreditados; decisiones del recorte y contratos versionados; SLO/retención/responsables definidos. |
| H1. Persistencia compartida | E3-03/04/05: adapter Neon, roles, migraciones, claims/fencing, restore | **E3-1:** IDs/atomicidad/deduplicación preservados, aislamiento con rol runtime, migración/restore medidos en Neon sintético. |
| H2. Identidad y autorización | E3-06: membresías, bindings, revocación y policy scoped | **E3-2:** cero acceso/entrega cruzados entre dos tenants y dos actores por tenant; pool/RLS y discovery fake verificados. |
| H3. Tooling gobernado | E3-07/08: Registry/Discovery/Executor y una READ externa | **E3-3:** lectura real controlada; denegaciones sin red, errores/límites y audit acreditados; mutations empresariales apagadas. |
| H4. Knowledge y respuesta | E3-09/10/11: selección vectorial, ingestión, retrieval y evidencia combinada | **E3-4:** G5/G6 cumplen umbrales sobre val congelado; aislamiento, revocación/reindex e injection demostrados. |
| H5. Operación | E3-12/13: audit/métricas, deployment, carga, fallos y rollback | **E3-5:** G7/G9 y SLO acordados con mediciones; restore/shutdown y límites operativos reproducibles. |
| H6. Validación integrada | E3-14/15: lead/case internos, evaluación real y expediente | **E3-6:** G1–G9 completos, cero fallos críticos, presupuesto reconciliado y decisión de release registrada. |

## Dependencias

```text
E3-01 → E3-02 → E3-03 → E3-04 → E3-05  [E3-1]
                    └→ E3-06 [E3-2] ┬→ E3-07 → E3-08 ─┐
                                     └→ E3-09 → E3-10 ─┴→ E3-11 [E3-4]
E3-04 + E3-08 + E3-11 → E3-12 → E3-13 [E3-5]
E3-06 + E3-11 → E3-14; E3-13 + E3-14 → E3-15 [E3-6]
```

El grafo muestra dependencias de trabajo; PLAN-E3 detalla prerequisites. Diseñar identidad junto con esquema antes de Neon; probar con fakes antes de retrieval real. E3-0 completo requiere cierre de E2, pero inventario, contratos y código offline E3 pueden avanzar en paralelo con B/C. Staging Neon sintético tampoco implica permiso para migrar tráfico. Antes de conectores reales acreditar E3-1/2; antes del piloto integrado acreditar E3-0…5.

## Decisiones por resolver

Neon relacional está elegido, pero driver/migraciones, región/plan y operación se concretan en H0/H1. ADR-008/009/019 deben cerrar el recorte de conversación/memoria. ADR-010 selecciona store/embeddings en H4. ADR-014/015/024 delimitan audit, retries y topología en H5. ADR-005/006 gobiernan tooling/policy ya aceptados; ADR-021 sigue bloqueando mutations externas nuevas. ADR-012/resume no se implementa por declarar un caso interno.

Monolito modular como propuesta de trabajo: API/worker/broker se separan solo si mediciones y lifecycle lo justifican. No se requieren microservicios ni despliegues por capability.

## Fuera de alcance

Mutations externas empresariales, export a CRM/helpdesk, campañas/envíos proactivos, WhatsApp real, UI web, multi-agent runtime, model routing/LoRA, Kubernetes y multi-región. El servicio no recibe datos reales hasta completar el expediente de release y la autorización de operación correspondiente.

## Primer incremento y cierre

Empezar E3-01 y E3-02: reconciliar estado E2 y definir identidad/UoW antes de adaptar PostgreSQL. Todas las tareas y gates E3 están pendientes al finalizar la planificación. El cierre técnico exige la evidencia de VERIFICACION; las fechas históricas de Linear y esta carpeta no fijan compromisos de entrega.
