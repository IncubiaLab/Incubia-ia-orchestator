# ADR-E2-001 — Ledger durable y recuperación para Gate A

**Status:** Accepted
**Scope:** Etapa 2 / H3
**Decision owner:** responsable técnico de Incubia

## Contexto

Gate A requiere que una entrada repetida, concurrente o recuperada tras reinicio no cree una segunda ejecución ni una segunda entrega. La memoria en proceso implementada en H1 no puede demostrarlo.

## Decisión pendiente

Adoptar SQLite local persistente con WAL y `synchronous=FULL` detrás de los puertos de conversación, inbox y outbox. La retención será de siete días para payloads y treinta días para tombstones.

Quedan para aprobación explícita:

- ruta operativa y permisos de `INCUBIA_DB_PATH`;
- purga diferenciada para payloads y tombstones;
- transiciones de recuperación `PROCESSING → NEEDS_INSPECTION` y `SENDING → UNKNOWN_EFFECT`;
- lock de un runner por bot y prueba de dos conexiones SQLite.

## Criterio de resolución

La decisión se acepta cuando E2-09 tiene migraciones versionadas, pruebas de reinicio/concurrencia y Gate A evidencia una ejecución/turno/entrega lógica por evento. Hasta entonces H4 está bloqueado.

## Progreso de implementación

`SqliteLedger` implementa WAL/FULL, migración inicial, lock exclusivo de runner, inbox/outbox, bindings, offset durable, recuperación, purga y backup SQLite. Las pruebas de integración cubren sus transiciones y `test_gate_a_e2e.py` acredita una ejecución y una entrega únicas de extremo a extremo con entrada, runtime y canal fake, incluyendo duplicado y reinicio.

## Relacionado

- ADR-ORCH-021 (propuesto)
- ADR-ORCH-023 (propuesto)
- E2-09 / Gate A
