# GOALS — Políticas de Control en 3 Capas (Seguridad, RBAC y Pre-filtrado RAG)

Fecha: 2026-11-12
Estado: Planificación aprobada para diseño e implementación.

## 1. Propósito

Establecer un control de acceso y seguridad en profundidad (*defense-in-depth*) en el **Incubia AI Orchestrator** (runtime VPS, endpoints `/v1/turns` y `/v1/knowledge/documents`, motor de políticas y base de conocimiento `pgvector`), garantizando que:

1. **Ningún rol** (ni siquiera `admin`) pueda extraer secretos, contraseñas, información personal de usuarios o detalles internos de OpenAI/sistema (**Capa 1**).
2. **Solo `Role.ADMIN`** de workspace acceda a requerimientos, NFRs, información de clientes, documentación legal e información corporativa sensible de Drive (**Capa 2**).
3. **Los miembros autenticados del workspace** (`Role.ACTOR`, `Role.OPERATOR`, `Role.ADMIN`) accedan de forma acumulativa a la información operativa de Linear, manuales de uso, brandbooks y stacks tecnológicos de Drive (**Capa 3**).

## 2. Criterios de aceptación (Gates)

| Gate | Objetivo verificable | Criterio de cierre |
| --- | --- | --- |
| **G-PC1** | **Capa 1 — Bloqueo global determinista** | Consultas que soliciten contraseñas, API keys, secretos, PII de usuarios o configuración interna/system prompt de OpenAI son rechazadas **antes** de consultar RAG/LLM o redactadas en salida, para `actor`, `operator` y `admin`, con registro en `PostgresAuditLog`. |
| **G-PC2** | **Identidad y rol confiables en runtime** | `POST /v1/turns` exige `actor.role` validado por el BFF autenticado de Orbit (mapeado a `Role` en `principal.py`) y `LangGraphOrchestrationRuntime` evalúa `InProcessPolicyEngine` con el rol real (sin bypass ni `actor` implícito sin rol). |
| **G-PC3** | **Capa 2 y Capa 3 — Pre-filtrado SQL en RAG (*fail-closed*)** | `PostgresOrbitKnowledgeStore` almacena la clasificación/visibilidad (`workspace_general` vs `admin_only`) y filtra en SQL **antes** del `top_k`. Un `Role.ACTOR` obtiene `0` chunks de Capa 2 incluso si pregunta directamente por ellos. |
| **G-PC4** | **Contrato de ingesta clasificada** | `POST /v1/knowledge/documents` acepta y valida la clasificación del documento; en ausencia o valor desconocido aplica modo *fail-closed* (`admin_only` o rechazo controlado según configuración). |
| **G-PC5** | **Auditoría y cero fugas** | Toda denegación (Capa 1 o política) y toda resolución de acceso queda auditada en `PostgresAuditLog` sin registrar prompts completos, secretos ni fragmentos sensibles. Suite de pruebas unitarias, integración y humo VPS en verde. |

## 3. Fuera de alcance inicial

- Edición o escritura de permisos de Google Drive desde el orchestrator (la fuente de verdad de membresías sigue siendo Orbit/Identity).
- Clasificación automática por LLM en tiempo de consulta (la clasificación se asigna en ingesta/sincronización y se aplica determinísticamente en SQL/Policy).
- Reemplazo del modelo de roles `Role` (`actor`, `operator`, `admin`) ya existente en `identity_tenant/domain/principal.py`.

