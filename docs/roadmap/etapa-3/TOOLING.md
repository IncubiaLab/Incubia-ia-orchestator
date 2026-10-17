# Tooling — etapa 3

ADR-005 Accepted gobierna Registry → Discovery → Selection → PEP → ToolExecutor → adapter. Ningún agente o workflow llama un cliente externo directamente. Las tools empresariales se distinguen de repositorios internos usados por casos de uso autorizados.

## Primer slice

Una capability READ `business.catalog.lookup` con input tipado query/product_ref y output de elementos con fuente, versión e instante. El slice empezó con adapter fake y servidor fixture HTTP; la fuente real seleccionada en E3-07 es Open Food Facts v3. No se supone Jira/CRM/POS ni se inventan endpoints. La lectura pública no usa credenciales, pero el gate remoto exige igualmente presupuesto, operación y evidencia controlada.

## Slice local E3-07/E3-08 (2026-10-15)

El contrato vive en `modules/orchestration/domain/tools.py`; los puertos están en
`ports/tool_discovery.py` y `ports/tool_executor.py`. `InProcessToolRegistry`
mantiene inventario versionado y `InProcessToolDiscovery` filtra enabled,
deployment/tenant, capability y compatibilidad de input. La selección es estable
por prioridad/id/versión y no equivale a autorización.

`ExecuteTool` es el PEP de aplicación. Revalida scope, versión e input, exige
policy `ALLOW` justo antes del adapter y deja mutations/external actions fuera del
MVP. La auditoría conserva `tool_call_id`, decisión, intentos, estado y errores
sanitizados; no conserva credenciales ni cuerpos remotos.

`business.catalog.lookup` tiene un fake sin I/O, `CatalogHttpAdapter` para
fixture y `OpenFoodFactsAdapter` como fuente real seleccionada. Open Food Facts
v3 está fijado a `https://world.openfoodfacts.org`, usa `GET
/api/v3/product/{product_ref}`, exige un `product_ref` numérico, limita la
respuesta y sólo envía campos configurados por el adapter. READ no usa
credencial; el `User-Agent` identificable es configuración no secreta. La prueba
HTTP usa `httpx.MockTransport` y el smoke real está en
`evals/results/e3-3-read-openfoodfacts-2026-10-15.json`. La respuesta externa se
trata como datos no confiables y nunca como instrucciones ejecutables.

La selección se basa en la [documentación oficial de la API](https://openfoodfacts.github.io/documentation/docs/Product-Opener/api/), que marca v3 como versión actual, y en la referencia oficial de [lectura de producto por código](https://openfoodfacts.github.io/documentation/docs/Product-Opener/v3/products/get-api-v3-product-code/).

Descriptor: tool_id/version, capabilities, schemas, deployment/tenant, availability, operation_type READ, idempotency_semantics, reversibility, destructive y credential_profile_ref. READ puede consumir cuota o registrar acceso remoto; no significa costo cero. Selection determinista y versionada; discovery filtra enabled/scope/compatibilidad sin autorizar.

## Seguridad y fiabilidad

Validar scope, rol, recurso, input, deadline y presupuesto antes de ejecutar; revalidar autorización tras espera. Resolver credenciales en adapter desde referencia administrada. URLs base y rutas configuradas por operador; impedir URLs arbitrarias del usuario y accesos internos no permitidos.

Propuesta local inicial: timeout por llamada 3 s, máximo 2 intentos READ y deadline total 10 s, configurables bajo el presupuesto del turno. Solo reintentar fallos transitorios explícitos mientras exista tiempo/cuota; respetar rate limit. No prometer p95 ≤5 s cuando el camino consume 10 s: registrar el fallo de SLO y ajustar en H5.

Registrar tool_call_id estable, intentos físicos distintos, policy decision, timestamps, estado, fuente y error sanitizado. No incluir auth headers ni cuerpos sensibles en logs. MUTATION/EXTERNAL_ACTION empresariales deshabilitadas hasta ADR-021 y aprobación aplicable; la entrega Telegram existente conserva sus reglas E2.

## Salida de E3-3

Una lectura de fuente real controlada por tenant y respuesta pública fundamentada. Casos negativos: descriptor ajeno, credenciales revocadas, JSON inválido, payload excesivo, URL prohibida, rate limit, timeout y respuesta que contiene instrucciones maliciosas. Cada denegación prueba cero llamada externa.
