# Roadmap — etapa 3: persistencia compartida, tooling y conocimiento

Fecha de actualización: 2026-10-15. Tier 3 significa tercera etapa de desarrollo. El resultado buscado es un piloto integrado que pueda acreditar condiciones de producción con evidencia. E3-D0-L está acreditado; H1 y H2 tienen expedientes técnicos listos para decisión; E3-07/08 tienen READ real de humo y E3-09/10/11 tienen G5 acreditado con modelo local versionado y G6 técnico evaluado; falta firma manual de G6; no modifica el estado pendiente de los gates arquitectónicos E3-0…E3-6.

## Prioridad RAG IncubiaLab (2026-10-21)

Desarrollar tres etapas y entregas RAG-V1/V2/V3 con validación explícita por entrega según [GOALS](GOALS.md#feature-rag-incubialab-tres-etapas-y-tres-entregas), [howto](howto.md#10-howto-del-rag-incubialab) y [dessing](dessing.md#11-diseño-del-rag-incubialab). Tras las tres aceptaciones, retomar el desarrollo global y sus gates pendientes. Estado actual: planificación; esta actualización no acredita conexión ni ingestión real.

## Punto de partida

CLI responde y Telegram está parcialmente funcional. Gate A E2 está cerrado según su [VERIFICACION](../etapa-2/VERIFICACION.md); Gate B sigue en progreso y Gate C pendiente. El smoke real acredita una generación/contador, sin cerrar evaluación. Neon está seleccionado localmente en [ADR-025](../../adr/ADR-ORCH-025-NEON-POSTGRESQL-TIER-3.md); el adapter y la campaña sintética H1 están acreditados, pero faltan decisión E3-1 y operación productiva. El baseline de Linear procede del corte heredado y sigue pendiente de revalidación completa en E3-01.

E3-D0 permite ensayar antes el ciclo de entrega local con Docker Compose, PostgreSQL local con volumen persistente y adapters deterministas. Es evidencia de empaquetado, migración y recuperación básica; PostgreSQL local no sustituye la evidencia de Neon requerida por H1.

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
| [KNOWLEDGE](KNOWLEDGE.md) | Retrieval, dataset, ingestión, versiones y operación pgvector por deployment. |
| [IMPLEMENTACION](IMPLEMENTACION.md) | Backlog E3-01…15 y dependencias. |
| [PLAN-E3](PLAN-E3.md) | Archivos objetivo, trabajo y validación por tarea. |
| [AUTOPLAN-REVIEW](AUTOPLAN-REVIEW.md) | Decisiones pendientes, responsables por designar y riesgos. |
| [LINEAR-ADR](LINEAR-ADR.md) | Fuentes, estado fechado y correspondencia con hitos de plataforma. |
| [RUNBOOK](RUNBOOK.md) | Corte de autoridad, restore, recuperación y release. |
| [VERIFICACION](VERIFICACION.md) | Matriz de evidencia y criterios de gates. |
| [PROGRESS](PROGRESS.md) | Estado actual y registro de avance. |

## Alcance

Monolito modular con contratos propios, PostgreSQL administrado en Neon para servicio compartido, identidad/tenant confiables, una integración externa READ gobernada y RetrievalPort sobre pgvector aislado por deployment, audit y operación medidos. Leads y casos se registran internamente con autorización/consentimiento; exports externos son incrementos posteriores. CLI conserva modo offline y Telegram sus garantías de inbox/outbox.

E3-D0 añade una instancia local única de la misma aplicación para el MVP. Docker Compose no aprueba una topología productiva: no decide Kubernetes, múltiples réplicas, broker, microservicios ni ratifica ADR-024. ADR-022 y ADR-024 continúan como decisiones propuestas; monedas, ejes y círculos son recorridos internos del monolito, nunca unidades de despliegue.

## Baseline de deployment E3-D0

**E3-D0 no es E3-0.** E3-0 es el gate arquitectónico de H0; E3-D0 es una pista preliminar y paralela de operación local. No cierra H1–H5, no acredita G2–G9 y no ratifica ADR-024.

| Nivel | Alcance y salida | Límites de la evidencia |
| --- | --- | --- |
| **E3-D0-L** | Compose local: imagen Python 3.12 no-root, `postgres` local, migrador one-shot y `app` única; HTTP loopback, LLM falso y seams deterministas sin I/O para tool/retrieval; estado durable entre reinicios. | Sin Neon, pgvector, READ, LLM, Telegram ni tools de red. Los seams no acreditan contratos H3/H4; sólo se acredita el baseline local. |
| **E3-D0-R** | Validación posterior que reutiliza imagen y contrato HTTP con Neon, pgvector, una READ y LLM reales autorizados, presupuesto, audit y métricas. | Sólo puede empezar después de H1–H4 y autorización de credenciales/presupuesto. Su éxito no sustituye G2–G9 ni los gates E3-1…E3-5. |

### Loop operativo de Monedas / Ejes / Círculos

```text
turno HTTP entrante
  → Contexto (scope sintético configurado + conversation_id)
  → eje de routing
  → capability / círculo seleccionado
  → outcome
  → commit durable (inbox, turno, outcome, outbox y revisión)
  → siguiente turno HTTP
       (mismo conversation_id, nuevo execution_id; puede elegir otra capability)
```

El loop es una cadena de solicitudes HTTP, no una iteración interna ilimitada. Cada `POST /v1/executions` crea un `execution_id` servidor nuevo, conserva el `conversation_id` indicado y termina tras un único outcome/commit. No se crea un contenedor por moneda, eje o círculo, ni se habilitan bucles internos sin límite.

En E3-D0-L el ingress sólo se publica en `127.0.0.1`. Recibe mensaje y clave de conversación —más la clave de idempotencia del transporte cuando aplique— y rechaza `deployment_id`, `tenant_id` y `actor_id` en el payload. El scope sintético procede exclusivamente de configuración de entorno; este endpoint sin autenticación está prohibido en staging y producción.

## Hitos y gates

| Hito | Entregable / tareas | Gate de salida |
| --- | --- | --- |
| E3-D0 (preliminar, paralelo) | Imagen/Compose local, migración one-shot, HTTP mínimo y recuperación local | **E3-D0-L:** build no-root, preflight/readiness, cadena durable/replay/reinicio y cero red externa acreditados. No cierra H1–H5. |
| H0. Baseline y contratos | E3-01/02: inventario E2/ADR, identidad, persistencia/UoW, NFR | **E3-0:** A/B/C E2 acreditados; decisiones del recorte y contratos versionados; SLO/retención/responsables definidos. |
| H1. Persistencia compartida | E3-03/04/05: adapter Neon, roles, migraciones, claims/fencing, restore | **E3-1:** IDs/atomicidad/deduplicación preservados, aislamiento con rol runtime, migración/restore medidos en Neon sintético. |
| H2. Identidad y autorización | E3-06: membresías, bindings, revocación y policy scoped | **E3-2:** cero acceso/entrega cruzados entre dos tenants y dos actores por tenant; pool/RLS y discovery fake verificados. |
| H3. Tooling gobernado | E3-07/08: Registry/Discovery/Executor y Open Food Facts como READ externa; slice local fake/fixture implementado | **E3-3:** smoke real pasado; campaña completa, presupuesto/operación y decisión formal pendientes; mutations empresariales apagadas. |
| H4. Knowledge y respuesta | E3-09/10/11: dataset y slice offline de pgvector, ingestión, retrieval y respuesta combinada; validación real pendiente | **E3-4:** G5/G6 cumplen umbrales sobre val congelado; aislamiento entre deployments, revocación/reindex e injection demostrados. |
| H5. Operación | E3-12/13: audit/métricas, deployment, carga, fallos y rollback | **E3-5:** G7/G9 y SLO acordados con mediciones; restore/shutdown y límites operativos reproducibles. |
| H6. Validación integrada | E3-14/15: lead/case internos, evaluación real y expediente | **E3-6:** G1–G9 completos, cero fallos críticos, presupuesto reconciliado y decisión de release registrada. |

Para H1, E3-H1-N es una preparación de infraestructura (no un gate): rama Neon sintética temporal, base Control Plane, roles separados, DSNs y runner explícito. M1 y M2 están acreditados; la campaña integrada M3 pasó offline (27/27), Compose local y Neon (8/8) en la rama sintética. El expediente quedó `ready_for_gate`, pero `gate_closed=false` hasta registrar la decisión formal E3-1. Consultar evidencia vigente en [RUNBOOK](RUNBOOK.md), [VERIFICACION](VERIFICACION.md) y [PROGRESS](PROGRESS.md).

El cierre de H1 queda organizado en tres milestones: [M1 contrato,
ownership y fencing](H1-CIERRE.md#m1--contrato-compartido-ownership-y-fencing-completo),
[M2 export/import y restore](H1-CIERRE.md#m2--exportimport-backup-y-restore-medidos)
y [M3 campaña integrada y decisión E3-1](H1-CIERRE.md#m3--campaña-integrada-y-decisión-e3-1).
Ningún milestone convierte la rama sintética en producción ni autoriza escribir
en `production`.

## Dependencias

```text
E3-D0-L ───────────────────────────────────────────────────────┐
                                                               │ evidencia local paralela; no cierra H1–H5
E3-01 → E3-02 → E3-03 → E3-04 → E3-05  [E3-1]
                    └→ E3-06 [E3-2] ┬→ E3-07 → E3-08 ─┐
                                     └→ E3-09 → E3-10 ─┴→ E3-11 [E3-4]
E3-04 + E3-08 + E3-11 → E3-12 → E3-13 [E3-5]
E3-06 + E3-11 → E3-14; E3-13 + E3-14 → E3-15 [E3-6]
H1 + H2 + H3 + H4 + presupuesto/credenciales autorizados → E3-D0-R
```

El grafo muestra dependencias de trabajo; PLAN-E3 detalla prerequisites. E3-D0-L puede avanzar en paralelo con E3-02/03, pero no convierte PostgreSQL local en evidencia H1. Diseñar identidad junto con esquema antes de Neon; probar con fakes antes de retrieval real. E3-0 completo requiere cierre de E2, pero inventario, contratos y código offline E3 pueden avanzar en paralelo con B/C. Staging Neon sintético tampoco implica permiso para migrar tráfico. Antes de promover conectores reales al piloto, acreditar E3-1/2; antes del piloto integrado acreditar E3-0…5.

## Decisiones por resolver

Neon relacional, driver `psycopg`, migraciones y región/plan sintéticos están concretados en H1; la operación productiva y la decisión E3-1 siguen pendientes. ADR-008 ya fija Conversation/UoW; ADR-009/019 deben cerrar el recorte de memoria y su frontera con runtime. ADR-010 fija pgvector y una base por deployment para Knowledge; E3-10 aún debe ratificar modelo semántico, dimensión e índices con evidencia real. ADR-014/015/024 delimitan audit, retries y topología en H5. ADR-005/006 gobiernan tooling/policy ya aceptados; ADR-021 sigue bloqueando mutations externas nuevas. ADR-012/resume no se implementa por declarar un caso interno.

Monolito modular como propuesta de trabajo: API/worker/broker se separan solo si mediciones y lifecycle lo justifican. No se requieren microservicios, despliegues por capability ni un proceso/contenedor por moneda, eje o círculo.

## Fuera de alcance

Mutations externas empresariales, export a CRM/helpdesk, campañas/envíos proactivos, WhatsApp real, UI web, multi-agent runtime, model routing/LoRA, Kubernetes, múltiples réplicas, microservicios y multi-región. El servicio no recibe datos reales hasta completar el expediente de release y la autorización de operación correspondiente. El endpoint HTTP sin autenticación de E3-D0-L tampoco se promueve a staging/producción.

## Primer incremento y cierre

E3-D0-L ya acredita la base local. Completar E3-01/E3-02 y el cierre E2 B/C; registrar decisiones E3-1/E3-2; completar campañas E3-3/E3-4 y después E3-12…15. Todos los gates arquitectónicos E3 permanecen pendientes; el cierre técnico exige la evidencia de VERIFICACION. Las fechas históricas de Linear y esta carpeta no fijan compromisos de entrega.


Actualización E3-4 (2026-10-15): [G5 local en Neon](../../../evals/results/e3-4-neon-local-2026-10-15.json) pasó 40/40 recall, 40/40 abstención, p95 0,6177 s, cero fugas, exact/HNSW y pruebas de revocación/rollback. [G6 técnico](../../../evals/results/e3-4-g6-neon-local-2026-10-15.json) evaluó 24 casos: 12/12 afirmaciones respaldadas, 6/6 referencias del manifiesto y cero fallos críticos; la URL pública READ respondió 200 anónimo. El gate sigue abierto por rúbrica manual sin firma y READ de G6 ejecutada con fixture HTTP. El resultado OpenAI anterior fallido se conserva como historial; el modelo local versionado es el candidato actual.
