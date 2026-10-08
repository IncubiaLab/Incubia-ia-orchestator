# ADR-ORCH-025 — PostgreSQL administrado con Neon para Tier 3

**Estado:** Accepted for Tier 3 adoption; rollout gated  
**Fecha:** 2026-10-07  
**Alcance:** Persistencia compartida del servicio Incubia Orchestrator en Tier 3  
**Decisión relacionada:** ADR-E2-001 (SQLite local para Gate A), ADR-ORCH-008 (Conversation State), ADR-ORCH-019 (Conversation State / GraphState), ADR-ORCH-024 (topología)

## Contexto

Tier 2 valida los contratos, CLI, Telegram, recuperación e idempotencia con un proceso y ledger local. Tier 3 empieza a requerir despliegue fuera de la máquina de desarrollo, estado accesible desde procesos reemplazables, aislamiento multi-tenant, backups operables y evolución hacia API/workers separados. El SAD define persistencia como adapter detrás de puertos y evita que Domain/Application dependan de una tecnología concreta.

ADR-E2-001 seleccionó SQLite para el Gate A de un host y declara PostgreSQL como candidato cuando haya múltiples hosts/runners, alta disponibilidad o contención medida. Neon ofrece PostgreSQL administrado y cubre esa evolución sin hacer de su SDK parte del dominio. La decisión no implica mover el ledger local antes de cerrar evidencia E2 ni habilitar despliegues multi-región.

## Decisión

Adoptar **Neon PostgreSQL como base relacional administrada para Tier 3**, accedida mediante el adapter PostgreSQL de infraestructura y contratos/repositorios definidos por la aplicación.

1. Mantener SQLite como adapter local de CLI, desarrollo offline y evidencia de Gate A. El servicio desplegado usa Neon como autoridad compartida para conversación, inbox/outbox, bindings, outcomes y estado operativo que requiera consistencia entre réplicas.
2. Mantener portabilidad PostgreSQL: migraciones SQL versionadas, acceso mediante driver PostgreSQL estándar y configuración por `DATABASE_URL`; Domain/Application no importan SDKs Neon ni tipos SQL.
3. Aplicar `tenant_id` y `deployment_id` en claves/consultas de datos multi-tenant. La identidad y scope se resuelven en servidor; nunca se aceptan como autoridad desde el mensaje. Evaluar Row-Level Security antes de datos de clientes y probar aislamiento en base real.
4. Usar transacciones cortas para inbox/conversation/outcome/outbox, constraints únicas y compare-and-set para idempotencia. No mantener transacciones durante llamadas a LLM, Telegram u otras redes. `UNKNOWN_EFFECT` conserva el comportamiento de ADR-E2-001.
5. Separar credenciales de runtime y migración, usar TLS, secretos inyectados por entorno/gestor de secretos, pool limitado y conexiones compatibles con despliegues serverless si se elige ese modo. No persistir secretos de proveedores.
6. Habilitar backups/PITR, retención, alertas y procedimiento de restore de acuerdo con el plan de operación y los requisitos de privacidad antes de datos reales.
7. Usar Neon branching para desarrollo/CI solo con datos sintéticos. No usar ramas como mecanismo de promoción automática de datos ni como sustituto de migraciones revisadas.

## Límites y transición

La adopción de Neon no cierra por sí sola ADR-ORCH-008, ADR-ORCH-014, ADR-ORCH-019, ADR-ORCH-021 o ADR-ORCH-024. Tampoco decide vector store: la elección de RAG/pgvector corresponde a ADR-ORCH-010 y debe compararse con necesidades de recuperación, operación y costo.

La migración desde SQLite se autoriza como tarea de implementación de Tier 3 cuando se cumplan todos estos prerrequisitos:

- Gate A y Gate B de Etapa 2 cerrados con evidencia y backups/restores comprobados.
- Contrato de persistencia de conversación y lifecycle de ejecución reconciliado con ADR-007/019.
- Modelo de identidad/tenant aprobado, y pruebas negativas de aislamiento.
- Migraciones iniciales, límites de pool, timeout, retry e idempotencia definidos.
- RPO/RTO, retención, residencia de datos, costo y responsable operativo documentados.
- Prueba de restore y prueba de concurrencia sobre Neon completadas antes de datos reales.

El corte debe preservar los IDs lógicos y las claves de deduplicación. Se ejecuta migración con escritura congelada o estrategia dual-write temporal con reconciliación explícita; nunca se declara atomicidad distribuida entre SQLite y PostgreSQL.

## Alternativas consideradas

### Continuar únicamente con SQLite

Adecuado para desarrollo local y Gate A; no satisface el estado compartido requerido para réplicas del servicio ni alta disponibilidad gestionada.

### Operar PostgreSQL autogestionado

Da control directo, pero añade a Tier 3 instalación, actualización, backups, failover y guardias de operación sin una necesidad actual de personalización.

### Usar una base por tenant o por ejecución

Rechazado: multiplica migraciones y conexiones, complica consultas operativas y no aporta aislamiento suficiente por sí solo. El aislamiento se modela en identidad, claves, policy y pruebas; puede evolucionar a separación física si los requisitos lo demandan.

## Consecuencias

**Beneficios:** persistencia compartida administrada; evolución de SQLite a PostgreSQL preservando puertos; soporte de API/workers reemplazables; backups y operación delegados al proveedor.

**Costos/riesgos:** dependencia operacional de Neon y conectividad; límites/costo de conexiones y cómputo; requisitos de diseño multi-tenant; posible adaptación de pooling y latencia; portabilidad no elimina diferencias de operación administrada.

## Gate de producción

No conectar conversaciones reales hasta que exista revisión de seguridad/privacidad y se verifiquen aislamiento entre tenants, migraciones reproducibles, límites de conexiones, restauración, observabilidad de pool/latencia/errores y política de retención/borrado. El cierre de este ADR registra la elección de proveedor; estos criterios gatean su activación productiva.
