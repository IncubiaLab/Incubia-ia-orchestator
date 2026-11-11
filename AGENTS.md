# Guía de contribución para agentes y automatizaciones

## Límites de arquitectura

- El repositorio implementa un **monolito modular con arquitectura hexagonal y DDD selectivo** (`ADR-ORCH-001`, `ADR-ORCH-007`, `ADR-ORCH-017`, `ADR-ORCH-018`) bajo `src/incubia_orchestrator/`:
  - `foundation/`: contratos transversales (`contracts/`), límites operativos (`limits.py`), telemetría (`telemetry.py`) y pool acotado (`pg_pool.py`). No aloja lógica de negocio ni utilidades arbitrarias.
  - `modules/<contexto>/domain/`: entidades, políticas de dominio e invariantes puras. Prohibido importar `application/`, adapters, interfaces, frameworks o SDKs externos.
  - `modules/<contexto>/application/`: casos de uso (`HandleMessage`, `HandleInbound`, `GroundedWorkflow`, `ExecuteTool`, ingesta Knowledge). Conoce únicamente contratos y puertos propios; nunca importa LangGraph, OpenAI, `psycopg` ni clientes HTTP.
  - `modules/<contexto>/ports/`: protocolos e interfaces requeridos por `application/`.
  - `modules/<contexto>/adapters/`: implementaciones concretas (LangGraph en `orchestration/adapters/runtime/langgraph/`, LLM OpenAI/Fake, persistencia PostgreSQL/SQLite, canales Telegram, catálogo HTTP/Open Food Facts, Drive/pgvector).
  - `bootstrap/`: únicos *composition roots* autorizados (`composition.py`, `d0.py`, `knowledge_incubialab.py`) para seleccionar e instanciar adaptadores concretos.
  - `interfaces/`: puntos de entrada CLI (`cli/main.py`, `cli/bot.py`, `cli/tenant.py`) y HTTP (`http/main.py`, `http/orbit_gateway.py`, `http/e3_probe.py`, `http/migrate.py`).
- **Alcance de despliegue en VPS (`ADR-ORCH-024`, `PLAN-VPS.md`):** la unidad productiva en el VPS es el **orchestrator completo** con su runtime, políticas, adaptadores y estado operativo, expuesto mediante su interfaz API a los aplicativos consumidores. No reducir el orchestrator a un gateway sin estado ni depender del PC de desarrollo en producción.
- **Aislamiento y autoridad:** ningún payload de cliente puede definir por sí mismo `deployment_id`, `tenant_id` ni `actor_id` sin validación/autenticación previa del canal o BFF autorizado. El contenido recuperado (Knowledge/RAG o tools READ) se trata siempre como **evidencia no confiable**, nunca como instrucciones que eleven permisos.

## Trabajo local y verificación

Entorno gestionado con Python 3.12 y `uv` (`uv.lock`):

```bash
uv sync --frozen --extra test --extra deployment
```

Antes de entregar cambios de código o configuración, ejecutar las verificaciones correspondientes:

```bash
uv lock --check --offline
uv run --frozen python -m compileall -q src tests
PYTHONPATH=src .venv/bin/python -m pytest -q
git diff --check
```

Las campañas contra Neon (`@pytest.mark.neon`), lecturas reales (`INCUBIA_E3_READ_REAL=1`) o proveedores facturables están bloqueadas por defecto (red deshabilitada en tests ordinarios) y solo se ejecutan de forma explícita sobre la rama sintética aislada (`INCUBIA_E3_NEON_BRANCH=e3-h1-synthetic`) con presupuesto autorizado (`docs/roadmap/etapa-3/RUNBOOK.md`).

## Configuración, seguridad y datos

- Partir de `.env.example` y `deploy/*.env.example`. **Prohibido** versionar secretos, claves API (`sk-`), tokens de bot/gateway, DSNs con contraseña (`npg_`) o claves de service account en Git, logs, artefactos de evaluación o notas del vault.
- **Separación de roles en Neon (`ADR-ORCH-025`, `ADR-ORCH-027`):**
  - Ledger conversacional y auditoría: `DATABASE_URL` usa `incubia_runtime` (`NOBYPASSRLS`, sin DDL, por endpoint `-pooler` con `sslmode=require`); `INCUBIA_MIGRATION_DATABASE_URL` usa `incubia_migrator` por conexión directa para migraciones y restore. Contexto RLS (`deployment_id`, `tenant_id`) fijado dentro de cada transacción.
  - Knowledge Base (`ADR-ORCH-010`): una base por deployment; roles separados `incubia_kb_runtime` (solo `SELECT`, pooled TLS), `incubia_kb_ingestor` (DML de ingesta, pooled TLS) e `incubia_kb_migrator` (DDL directo).
- **Migraciones (`migrations/postgres/`, `migrations/knowledge/`):** son *forward-only* bajo regla *expand/contract* verificada por `tests/unit/test_e3_migration_rollback.py`. El rollback de aplicación es por digest de imagen `N-1`; el rollback de esquema/datos se realiza por restore validado, nunca con SQL inverso manual.
- **Auditoría y límites (`ADR-ORCH-014`, `ADR-ORCH-015`, `config/e3/limits.example.yaml`):** la carga de límites y la auditoría durable (`PostgresAuditLog`) operan en modo *fail-closed*; ante configuración inválida, cuota agotada o fallo de auditoría previo a I/O de herramienta, la operación se aborta sin ejecutar efectos externos.
- Al modificar contratos, entradas o decisiones operativas, mantener sincronizados `README.md`, `docs/codigo/`, `docs/adr/`, `docs/roadmap/etapa-3/` y el vault de Obsidian.

## Vault de conocimiento e investigación

- El vault de Obsidian del repositorio vive en `vault-orchestrator/` (y es navegable también desde la raíz del repositorio en Obsidian). Toda investigación nueva de arquitectura, topología de despliegue, persistencia, RAG, gobernanza de herramientas, seguridad u operación debe documentarse allí antes de cerrar el trabajo.
- Crear una nota en `vault-orchestrator/01-Investigacion/<tema>/` con frontmatter (`tipo: investigacion`, `tema`, `estado`, `fecha`), pregunta y alcance, contexto observado en el código, hallazgos verificables con fuentes primarias, alternativas evaluadas y recomendación.
- Mantener **nodos de convergencia separados**:
  - `vault-orchestrator/02-Decisiones/` consolida en notas atómicas `<tema> - beneficios.md`, `<tema> - contras y riesgos.md` y `<tema> - decisión.md`.
  - `vault-orchestrator/03-Implementacion/` registra en `<tema> - estado de implementación.md` qué está implementado en el código, qué evidencia de pruebas/gates lo respalda y qué bloqueos siguen abiertos.
  - Cada nota de investigación debe enlazar explícitamente mediante `[[wikilinks]]` a sus nodos de beneficios, contras y riesgos, decisión y estado de implementación, y viceversa.
- Actualizar siempre `vault-orchestrator/00-Entrada/Mapa de conocimiento.md` al añadir o modificar investigaciones, decisiones o estados de implementación. Usar `vault-orchestrator/99-Plantillas/Investigacion.md` como plantilla base.

## Convenciones

- Respetar las pruebas de frontera arquitectónica (`tests/test_boundaries.py`): ningún import de infraestructura en `domain/` ni `application/`.
- No registrar prompts, respuestas completas del LLM, cabeceras `Authorization`, DSNs ni datos personales en logs o métricas; conservar únicamente identificadores correlacionados (`request_id`, `execution_id`, `conversation_id`) y conteos/latencias agregadas.
- Mantener el flujo de promoción de ramas documentado en `docs/BRANCHING.md` y no sobrescribir trabajo ajeno sin reconciliación explícita.
