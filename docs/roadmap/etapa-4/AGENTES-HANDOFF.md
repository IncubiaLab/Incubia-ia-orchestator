# Agentes y handoff — contrato propuesto para E4

## Comportamiento por perfil

| Perfil | Resuelve | Solicita handoff cuando | Salida y límite |
| --- | --- | --- | --- |
| General | Orientación, síntesis sustentada y aclaración | La solicitud requiere una capability especializada definida para el caso de uso | Respuesta, pregunta de aclaración o abstención; no inventa hechos ni ejecuta tools fuera de policy. |
| Ventas | Capacidades comerciales definidas en el perfil vigente | La solicitud requiere una capability de otro perfil y policy permite transferirla | Resultado dentro de su contrato; no confirma datos empresariales sin evidencia ni ejecuta acciones externas sin autorización. |
| Marketing | Capacidades de marketing definidas en el perfil vigente | La solicitud requiere una capability de otro perfil y policy permite transferirla | Resultado dentro de su contrato; no presupone campañas, canales ni fuentes externas concretas. |

Cada perfil versionado declara `capabilities`, `required_context`, `allowed_evidence`, `output_contract`, condiciones de abstención y `handoff_reasons`. Los descriptores declaran disponibilidad y scope, nunca instrucciones ni permisos. Una solicitud de handoff expresa la capability requerida, no un nombre de agente obligatorio.

## Contrato y flujo

```text
AgentRun origen → HandoffRequest → HandoffCoordinator
  → Discovery(scope, capability) → Selection → Policy
  → HandoffContext mínimo → commit de ownership → AgentRun destino
  → outcome / posible nueva solicitud dentro de límites
```

`HandoffRequest` contiene versión, source run/ref, capability solicitada, `reason_code`, objetivo acotado, modo de salida, referencias de evidencia, scope de datos solicitado y tiempo restante. No acepta `deployment_id`, `tenant_id` o `actor_id` elegidos por el modelo. El coordinador toma esos IDs del `ExecutionScope` confiable y valida que origen y destino pertenecen al mismo contexto autorizado.

`HandoffContext` contiene IDs de correlación, agente origen/destino versionados, objetivo, resumen mínimo de conversación, hechos relevantes con procedencia y revisión, referencias a artefactos autorizados, revisión de policy, `hop_count`, lineage y expiración. Las referencias requieren nueva lectura mediante PEP. Quedan fuera historial completo por defecto, secretos, credenciales, contenido de tool sin filtrar, `GraphState` y checkpoints.

La autoridad efectiva del destino es la intersección de actor, origen, destino y policy vigente. Discovery y Selection eligen candidatos; Policy autoriza la transferencia y cada tool vuelve a autorizarse justo antes de I/O. `DENY`, `INDETERMINATE`, vencimiento o revocación impiden activar destino. `REQUIRE_APPROVAL` produce una salida tipada pendiente y espera el diseño de ADR-012; no se simula aprobación.

## Ownership y recuperación

Estados mínimos: `REQUESTED → EVALUATED → ACCEPTED → ACTIVATED → COMPLETED/FAILED`, con `DENIED/DECLINED/EXPIRED` como terminales alternos. La aceptación y el cambio de owner se persisten en la misma transacción de Conversation/UoW con revisión optimista y fencing. Un resultado incierto se inspecciona antes de cualquier reintento; no se ejecutan ambos runs. Repetir la misma solicitud idempotente devuelve el estado ya persistido.

El máximo de handoffs y el deadline total quedan por definir con escenarios, latencia y evaluación. Serán configurables por policy y se validarán antes del piloto. Se bloquean ciclos de la misma pareja capability/agente sin evidencia nueva. Al llegar al límite, el outcome es aclaración, abstención o `ESCALATION_REQUIRED`, según el caso; no hay reentrada silenciosa.

## Evidencia mínima

Medir precisión de selección y utilidad del destino frente a respuesta sin handoff, porcentaje de abstención apropiada, p95 extremo a extremo, hops, tokens/costo y fallos de scope. Casos negativos obligatorios: candidato disabled/ajeno, policy DENY/INDETERMINATE, revocación entre evaluación y activación, payload con instrucciones maliciosas, evidencia expirada, loop, timeout, replay y crash en el cambio de owner. Cualquier fuga entre tenants, elevación de autoridad, doble owner o efecto duplicado bloquea el gate.
