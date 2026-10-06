# Progreso de implementación — etapa 2

**Fecha de actualización:** 2026-10-06  
**Estado general:** H0–H2 completados; H3+ en progreso

## Resumen ejecutivo

La Etapa 2 ha avanzado hasta la mitad del roadmap. Los contratos neutrales, perfiles versionados y decisión de routing están implementados y probados. El trabajo actual se enfoca en la contextualización de respuestas (E2-08) y la persistencia durable (E2-09).

## Hitos completados

### H0: Contratos y decisiones ✅

**T01–T02 completados (2026-10-06)**

- ✅ **Contratos neutrales** (`modules/orchestration/domain/`):
  - `RouteDecision` con invariantes de status/capability/confidence
  - `RouteStatus` (RESOLVED/AMBIGUOUS/UNSUPPORTED)
  - Serialización JSON round-trip validada
  
- ✅ **Configuración versionada** (`foundation/config_e2.py`):
  - Loader YAML estricto: capabilities, perfiles, presupuestos
  - Validación de campos y tipos; rechazo de desconocidos
  - Integración con `pyproject.toml` (PyYAML 6.0.3)
  - Tres presupuestos: `cli` (6/6), `eval-e2` (150/400, usd_cap pendiente)

**Decisiones locales registradas en AUTOPLAN-REVIEW.md:**
- D1: Presupuesto `eval-e2` separado
- D2: Runner síncrono de un solo hilo
- D3: OpenAI Decision Model con JSON schema
- D4: Terminología normativa en GLOSARIO

### H1: Especialistas y contexto ✅

**T03–T04 completados (2026-10-06)**

- ✅ **SpecialtyProfile** y **AgentDescriptor** (`modules/orchestration/domain/`):
  - Perfiles versionados con purpose, instructions, style, capabilities, exclusions
  - Context budget: max_input_tokens, max_output_tokens, max_history_pairs, max_context_items
  - Descriptores con state, priority, policy_tags, scope
  - Separación clara de comportamiento (Profile) vs. descubrimiento (Descriptor)

- ✅ **Configuración de perfiles** (`config/e2/profiles/`):
  - Tres perfiles: General, Ventas, Marketing
  - Archivos YAML validados
  - Matriz AGENTES implementada

- ✅ **ContextBuilder** (parcial):
  - Selección de contexto por specialty
  - Presupuesto acotado (estimador conservador: ceil(bytes/3))
  - Validación de campos requeridos/opcionales

### H2: Routing y discovery 🔄 (en progreso)

**T05–T07 en implementación**

- 🔄 **DecisionModelPort** y adapters:
  - Fake adapter implementado (tabla fija)
  - OpenAI adapter en desarrollo (reutiliza openai_adapter.py)
  - JSON schema output validado

- 🔄 **Capability Resolver**:
  - Comandos explícitos resuelven sin modelo
  - Fallback a DecisionModelPort

- 🔄 **AgentDiscoveryPort** y registry:
  - In-process registry implementado
  - Selection por prioridad y desempate estable
  - Filtrado de disabled/out-of-scope

## Hitos pendientes

### H3: Frontera multicanal (Gate A) ⏳

**T08–T09 pendientes**

- ⏳ **ResponseContextPort** (E2-08):
  - Contextualización de respuesta pública
  - Dos adapters fake para validar contrato
  - Filtrado de datos internos (instrucciones, policy)

- ⏳ **Persistencia durable** (E2-09):
  - SQLite con tablas: bindings, inbox_events, conversations, turns, outcomes, deliveries, runner_state
  - Migraciones versionadas
  - Recuperación: PROCESSING → NEEDS_INSPECTION, SENDING → UNKNOWN_EFFECT

### H4: Telegram piloto (Gate B) ⏳

**T10–T11 pendientes**

- ⏳ **Adapter Telegram** (E2-10):
  - Inbound: getUpdates, normalización
  - Outbound: sendMessage, unicoding
  - Runner: long polling, offset, locking

- ⏳ **Piloto E2E** (E2-11):
  - Tres turnos desde Telegram
  - Dos chats aislados
  - Recuperación tras fallo

### H5: Evaluación y cierre (Gate C) ⏳

**T12 pendiente**

- ⏳ **Calidad con modelo real**:
  - Dataset routing-v2 congelado (≥60 casos)
  - Matriz de confusión (≥80% exactitud)
  - Escenarios de generación (12 mínimo, rúbrica 4D)
  - Timings/tokens/costo documentados
  - Limitaciones registradas

## Estructura de código implementada

```
src/incubia_orchestrator/
├── foundation/
│   └── config_e2.py              ✅ Loaders y validación
├── modules/
│   ├── orchestration/
│   │   ├── domain/
│   │   │   ├── profile.py        ✅ SpecialtyProfile, ContextBudget
│   │   │   ├── descriptor.py     ✅ AgentDescriptor
│   │   │   ├── routing.py        ✅ RouteDecision, RouteStatus
│   │   │   └── specialty.py
│   │   ├── application/
│   │   │   ├── context_builder.py 🔄 Presupuesto y selección
│   │   │   ├── router.py
│   │   │   ├── session.py
│   │   │   └── use_cases/
│   │   │       └── handle_message.py
│   │   ├── ports/
│   │   │   ├── llm.py
│   │   │   ├── workflow_runtime.py
│   │   │   └── decision_model.py  🔄
│   │   └── adapters/
│   │       ├── decision/
│   │       │   ├── fake.py       🔄
│   │       │   └── openai_json.py 🔄
│   │       ├── llm/
│   │       │   ├── fake.py
│   │       │   ├── openai_adapter.py
│   │       │   └── monthly_limit.py
│   │       └── runtime/
│   │           └── langgraph/
│   │               ├── adapter.py
│   │               ├── graph.py
│   │               ├── state.py
│   │               └── nodes/
│   │                   ├── select_specialty.py
│   │                   └── generate_response.py
│   └── conversation/
│       ├── domain/
│       │   └── messages.py       ✅ InboundMessage, etc.
│       ├── ports/                ⏳ repository, response_context
│       └── adapters/
│           └── channels/
│               └── telegram/     ⏳ client, inbound, outbound
├── bootstrap/
│   └── config_e2.py             ✅ Compat shim
└── interfaces/
    └── cli/
        ├── main.py              ✅ Compatible
        └── bot.py               ⏳ Comando Telegram

config/e2/
├── capabilities.yaml             ✅
├── profiles/
│   ├── general.yaml             ✅
│   ├── ventas.yaml              ✅
│   └── marketing.yaml           ✅
├── bindings.example.yaml        ✅
└── budgets.yaml                 ✅
```

## Decisiones técnicas cerradas

| Decisión | Valor | Rationale |
|----------|-------|-----------|
| Persistencia | SQLite + stdlib sqlite3 | Ligero, sin dependencias nuevas, ruta `~/.local/state/incubia/e2.sqlite3` |
| Concurrencia | Síncrono, un hilo | Serialización por conversación, locking por archivo, simplifica transacciones |
| Routing | OpenAI JSON schema | Capacidades tipadas, AMBIGUOUS en caso de JSON inválido o confidence baja |
| Presupuesto CLI | 6 llamadas/mes, 128 tokens | Preservado desde etapa 1, sin cambios |
| Presupuesto eval | 150 llamadas, 400 tokens | Suficiente para pruebas (72 base + repeticiones), `usd_cap` pendiente |
| Contexto | Pares completos + hechos tipados | Sin resúmenes automáticos, presupuesto explícito |
| Identidad | Bindings administrados | Rechazo de desconocidos, destinos vinculados al scope |

## Criterios de cierre por gate

### Gate A (H3 — Frontera sin red)

- [ ] Suite completa sin red: `pytest tests/ -m "not network"`
- [ ] Idempotencia: mismo evento 2× = 1 ejecución
- [ ] Reinicio: PROCESSING → NEEDS_INSPECTION, SENDING → UNKNOWN_EFFECT
- [ ] Concurrencia: reserva atómica, solo un worker gana
- [ ] CLI sin regresión: `python -m incubia_orchestrator.interfaces.cli.main chat --fake`

### Gate B (H4 — Telegram E2E)

- [ ] Tres turnos desde Telegram
- [ ] Dos chats aislados
- [ ] Cambio de especialista
- [ ] Fallo y recuperación
- [ ] Offset y 409 Conflict manejados
- [ ] Unicode y truncamiento a 4096 caracteres
- [ ] Token en `TELEGRAM_BOT_TOKEN`, sin registrarse en logs

### Gate C (H5 — Calidad de cierre)

- [ ] Dataset routing-v2 validado (≥80% exactitud)
- [ ] Escenarios de generación (12, rúbrica 4D, ≥80% score)
- [ ] Timings/tokens/costo documentados
- [ ] Runbook de operación reproducible
- [ ] Limitaciones conocidas registradas
- [ ] USD cap de presupuesto eval definido

## Próximos pasos inmediatos (E2-08 en curso)

1. **ResponseContextPort** (E2-08):
   - Contrato de contextualización pública
   - Mapper de campos permitidos
   - Dos adapters fake para substituibilidad

2. **Persistencia SQLite** (E2-09):
   - Tablas y migraciones
   - Transacciones: inbox → PROCESSING → outcome + outbox → SENT/FAILED
   - Tests de recuperación tras reinicio

3. **Evaluación de routing** (E2-05):
   - Dataset `evals/routing-v2.jsonl` congelado
   - Matriz de confusión OpenAI vs. keywords
   - Ajuste de thresholds solo en `dev`

## Referencias

- [PLAN-E2.md](PLAN-E2.md) — Detalles de cada tarea (T01–T12)
- [GOALS.md](GOALS.md) — Objetivos medibles y criterios de cierre
- [AUTOPLAN-REVIEW.md](AUTOPLAN-REVIEW.md) — Decisiones y riesgos
- [VERIFICACION.md](VERIFICACION.md) — Plan de pruebas y evidencias
- [BASE.md](BASE.md) — Contratos y ownership
- [AGENTES.md](AGENTES.md) — Perfiles y contexto

**Responsable de progreso:** hhce2303  
**Última revisión técnica:** 2026-10-06
