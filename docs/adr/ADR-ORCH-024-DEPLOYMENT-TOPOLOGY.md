# ADR-ORCH-024 — Topología de despliegue Tier 3

**Estado:** Aceptado el 2026-10-23 por el responsable (hector.cruz@sig.systems); Docker Compose no decide producción. La evidencia de la sección «Evidencia que debe ratificarlo» sigue pendiente y condiciona el tráfico real  
**Fecha:** 2026-10-23  
**Alcance:** Hosting de la aplicación, red y datos, rollback; decisión D8 / gate E3-5  
**Relacionados:** ADR-ORCH-010 (una base por deployment para Knowledge), ADR-ORCH-025, ADR-ORCH-027

## Contexto (hechos del repositorio)

- Monolito modular: una imagen (`Dockerfile`, Python 3.12 multi-stage, usuario
  10001, sin secretos) con tres roles de proceso: `migrate` one-shot, `app` HTTP
  y, a demanda, el dispatcher de canal. No hay broker. Monedas, ejes y círculos
  son recorridos internos, no unidades de despliegue.
- `compose.yaml` (E3-D0-L): `postgres` 16 local, `migrate` con rol `d0_migrator`,
  `app` con rol `d0_runtime`, FS de solo lectura, `cap_drop: ALL`, publicación en
  `127.0.0.1`. Es un baseline de instancia única; el endpoint sin autenticación
  está prohibido en staging y producción (RUNBOOK).
- Apagado: `DrainingHTTPServer` deja de aceptar y espera a los requests en vuelo
  hasta `drain_seconds=10` (hilos daemon; registra `http_drain_abandoned`).
  Tras un kill, el estado queda recuperable: PROCESSING con lease que vence →
  RECEIVED; SENDING → UNKNOWN_EFFECT sin reenvío (`test_e3_shutdown.py`).
- Datos: Neon, rama sintética `e3-h1-synthetic`. Runtime (`incubia_runtime`) por
  endpoint pooled con TLS, migrador (`incubia_migrator`) por conexión directa
  (`deploy/e3-neon.env.example`, ADR-ORCH-027). El `PostgresLedger` abre una
  conexión corta por transacción con `connect_timeout=3`; el pooling lo aporta el
  pooler de Neon. Knowledge usa una base por deployment con `KnowledgePools`
  acotado (`max_size=4`, `timeout=3`).
- Rollback (RUNBOOK): migraciones forward-only con regla expand/contract; primero
  rollback de imagen por digest N-1; el de esquema/datos es restore, no SQL inverso.
- Concurrencia: claims con generación y lease (fencing) permiten varios workers
  sin doble commit (`test_e3_faults.py`), aunque no se ha medido bajo carga.

## Opciones de hosting (D8)

| Opción | Ventajas | Desventajas |
| --- | --- | --- |
| A. Una instancia contenedor en VM/PaaS de contenedores (p. ej. VM + Compose endurecido o servicio gestionado de un contenedor) con Neon externo | Mínima superficie operativa; coincide con lo ya probado en D0; rollback por digest trivial; costo bajo y predecible | Sin HA propia: caída de la instancia = indisponibilidad hasta reinicio; escalado vertical; TLS/autenticación de borde por añadir |
| B. N réplicas stateless de la app tras balanceador (PaaS/orquestador gestionado), Neon pooled | HA y despliegue gradual; el fencing ya tolera varios workers | Requiere LB, auth de borde, health/readiness en orquestador y evidencia de fencing a carga; dispatcher de canal debe seguir siendo un único dueño (claim) |
| C. Kubernetes | Máxima flexibilidad | Complejidad y costo no justificados por carga medida; contradice D8 (HTTP/worker separados sólo por necesidad medida) |
| D. Serverless/funciones | Escala a cero | Tiempo de vida limitado frente a drain de 10 s y llamadas LLM de hasta 30 s; conexiones por request contra pooler; peor control de apagado |

## Decisión (aceptada 2026-10-23)

**Opción A como punto de partida, con una ruta explícita a B** si la carga lo
exige: una sola imagen, un proceso `app` (más migrador one-shot previo al
rollout), Neon con runtime pooled y migrador directo, una base Knowledge por
deployment, rollback por digest N-1 con la regla expand/contract. Réplicas
(opción B) se habilitan sólo con evidencia; Kubernetes y serverless quedan
descartados en esta etapa.

Condiciones de borde obligatorias antes de tráfico real: autenticación y TLS
frente al servicio (el ingress D0 no los tiene), secretos desde el gestor de la
plataforma (nunca en la imagen), `terminationGracePeriod` >= `drain_seconds` + margen
y readiness como criterio de admisión.

## Criterios de escala de A a B

El responsable aceptó la opción A con una ruta explícita a B. Se pasa a N réplicas
(misma imagen, dispatcher de canal con un único dueño por claim) cuando se
cumpla cualquiera de estos disparadores, medido en la campaña o en operación:

1. El p95 de recepción→outcome supera 5 s de forma sostenida por saturación de la
   instancia (no por latencia del proveedor).
2. El RTO ≤1 h o la disponibilidad requerida no se cumple con reinicio de una
   sola instancia (la caída de la instancia es el punto único de fallo de A).
3. La CPU/memoria o las solicitudes en vuelo de la instancia se saturan en la
   carga acordada, o el escalado vertical deja de ser suficiente.
4. Se exige despliegue sin indisponibilidad (rolling) que A no puede ofrecer.

Antes de habilitar B debe existir evidencia de fencing con 2+ workers sobre Neon
bajo carga, autenticación de borde y LB con readiness. Los umbrales numéricos
exactos de CPU/memoria se fijarán con las mediciones de la campaña E3-5.

## Evidencia que debe ratificarlo

1. Carga >= 10 min por perfil (burst y sostenido) contra Neon real con rol runtime
   pooled: p95/p99, errores, CPU/memoria, conexiones, sin pérdida ni duplicados.
2. Shutdown: SIGTERM bajo carga en la plataforma elegida; cero requests perdidos
   dentro de `drain_seconds`, `http_drain_abandoned=0` y reconciliación limpia.
3. Fault injection (`tests/integration/test_e3_faults.py`) repetido contra Neon:
   proveedores caídos, saturación del pooler y claim vencido con 2+ workers.
4. Rollback ejecutado (imagen N-1 y restore) con RPO/RTO medidos. `h1_backup.py` sólo cubre las tablas del ledger conversacional: el restore de audit y Knowledge (base por deployment) requiere un procedimiento adicional por definir.
5. SLO/RPO/RTO y costo mensual por opción; decisión del responsable registrada en
   VERIFICACION. Si A no cumple SLO, escalar a B con la misma imagen.
