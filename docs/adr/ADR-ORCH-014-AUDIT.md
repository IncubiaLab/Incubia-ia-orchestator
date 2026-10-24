# ADR-ORCH-014 — Audit trail durable y fail-closed

**Estado:** Propuesto — pendiente de ratificación en el registro de ADRs  
**Fecha:** 2026-10-23  
**Alcance:** Governance/Audit, Tool READ, gate E3-5 (G7)  
**Relacionados:** ADR-ORCH-005, ADR-ORCH-006, ADR-ORCH-025 (que lo cita como no cerrado)

## Contexto

ADR-ORCH-025 señala que la adopción de Neon no cierra ADR-ORCH-014. El código ya
implementa un `AuditSinkPort` con dos adaptadores durables (`SqliteAuditLog`,
`PostgresAuditLog` con la migración `008_e3_g7_audit.sql`) y uno en memoria.
`ExecuteTool` es el PEP: registra `TOOL_REQUESTED`, `POLICY_DECISION` y cada
intento antes de que el adaptador haga I/O.

## Decisión propuesta

1. **Fail-closed.** `append` confirma su transacción antes de cualquier I/O
   externo; si falla, la excepción se propaga y la operación no se ejecuta.
2. **Sin datos de cliente.** Sólo identificadores, hash SHA-256 del recurso y
   metadatos enteros/booleanos de una lista blanca (`safe_metadata`); el texto
   libre se descarta. Entradas de tool y recursos no se persisten literales.
3. **Scope y RLS.** En PostgreSQL cada append es una transacción corta con
   `set_config` de deployment/tenant, de modo que RLS aplica al rol runtime.
4. **Correlación.** Todos los eventos de una ejecución comparten `execution_id`.
5. **Solo-append para runtime.** El rol runtime inserta y lee; no modifica ni
   borra. Retención y purga son procedimiento operativo (RUNBOOK), no runtime.

## Consecuencias

- Una caída de la base de audit bloquea Tool READ (disponibilidad menor a
  cambio de trazabilidad); la respuesta degrada a abstención/error controlado.
- No hay audit asíncrono ni broker: el costo es una escritura por evento en
  la ruta crítica, a medir en la campaña de carga E3-5.

## Evidencia pendiente para ratificar

- Carga: p95 de ejecuciones con audit PostgreSQL pooled en Neon real.
- Falla inyectada de audit: ninguna llamada a adapter, error controlado.
- Verificación RLS del audit con rol runtime sin `BYPASSRLS` (ADR-ORCH-027).
