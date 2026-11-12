# Composición ejecutable del orchestrator P1 — contras y riesgos

Fecha: 2026-11-11.

- **Mayor acoplamiento de dependencias en arranque:** Si la base de datos de Neon o el esquema no están listos, `/readyz` fallará cerrado (esto es intencional para evitar tráfico sin persistencia, pero requiere que el job de migraciones corra antes).
- **Consumo de conexiones hacia Neon:** Tanto el ledger conversacional como la auditoría y el retrieval comparten conexiones pooled; el pool debe acotarse (`max_size=4` por defecto) para respetar los límites del connection pooler de Neon.
- **Riesgo de streaming incompleto en SSE:** El adaptador SSE genera los eventos `delta`, `citation` y `done` tras completar la inferencia segura; el streaming token a token se mantiene aplazado para una fase posterior con el fin de garantizar la auditoría fail-closed antes de emitir bytes al cliente.

[[01-Investigacion/Composicion-P1/Investigacion - composicion ejecutable del orchestrator P1]] · [[Composición ejecutable del orchestrator P1 - beneficios]] · [[Composición ejecutable del orchestrator P1 - decisión]] · [[03-Implementacion/Composición ejecutable del orchestrator P1 - estado de implementación]]
