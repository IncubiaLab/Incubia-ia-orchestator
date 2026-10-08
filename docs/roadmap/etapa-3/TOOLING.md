# Tooling — etapa 3

ADR-005 Accepted gobierna Registry → Discovery → Selection → PEP → ToolExecutor → adapter. Ningún agente o workflow llama un cliente externo directamente. Las tools empresariales se distinguen de repositorios internos usados por casos de uso autorizados.

## Primer slice

Una capability READ `business.catalog.lookup` con input tipado query/product_ref y output de elementos con fuente, versión e instante. Empezar con adapter fake y servidor fixture HTTP. El sistema externo real se elige en E3-07 según acceso disponible del proyecto; no suponer Jira/CRM/POS ni inventar endpoints. Sin credenciales, el gate remoto permanece pendiente aunque el slice fake pase.

Descriptor: tool_id/version, capabilities, schemas, deployment/tenant, availability, operation_type READ, idempotency_semantics, reversibility, destructive y credential_profile_ref. READ puede consumir cuota o registrar acceso remoto; no significa costo cero. Selection determinista y versionada; discovery filtra enabled/scope/compatibilidad sin autorizar.

## Seguridad y fiabilidad

Validar scope, rol, recurso, input, deadline y presupuesto antes de ejecutar; revalidar autorización tras espera. Resolver credenciales en adapter desde referencia administrada. URLs base y rutas configuradas por operador; impedir URLs arbitrarias del usuario y accesos internos no permitidos.

Propuesta local inicial: timeout por llamada 3 s, máximo 2 intentos READ y deadline total 10 s, configurables bajo el presupuesto del turno. Solo reintentar fallos transitorios explícitos mientras exista tiempo/cuota; respetar rate limit. No prometer p95 ≤5 s cuando el camino consume 10 s: registrar el fallo de SLO y ajustar en H5.

Registrar tool_call_id estable, intentos físicos distintos, policy decision, timestamps, estado, fuente y error sanitizado. No incluir auth headers ni cuerpos sensibles en logs. MUTATION/EXTERNAL_ACTION empresariales deshabilitadas hasta ADR-021 y aprobación aplicable; la entrega Telegram existente conserva sus reglas E2.

## Salida de E3-3

Una lectura de fuente real controlada por tenant y respuesta pública fundamentada. Casos negativos: descriptor ajeno, credenciales revocadas, JSON inválido, payload excesivo, URL prohibida, rate limit, timeout y respuesta que contiene instrucciones maliciosas. Cada denegación prueba cero llamada externa.
