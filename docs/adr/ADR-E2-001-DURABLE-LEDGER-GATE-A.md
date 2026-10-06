# ADR-E2-001 — Ledger durable y recuperación para Gate A

**Status:** Proposed  
**Scope:** Etapa 2 / H3  
**Decision owner:** responsable técnico de Incubia

## Contexto

Gate A requiere que una entrada repetida, concurrente o recuperada tras reinicio no cree una segunda ejecución ni una segunda entrega. La memoria en proceso implementada en H1 no puede demostrarlo.

## Decisión pendiente

Adoptar SQLite local con WAL detrás de los puertos de conversación, inbox y outbox, usando las tablas, claves únicas, estados y retención definidos en `docs/roadmap/etapa-2/BASE.md` y `TELEGRAM.md`.

Quedan para aprobación explícita:

- ruta operativa y permisos de `INCUBIA_DB_PATH`;
- retención de 30 días y procedimiento de purga;
- transiciones de recuperación `PROCESSING → NEEDS_INSPECTION` y `SENDING → UNKNOWN_EFFECT`;
- lock de un runner por bot y prueba de dos conexiones SQLite.

## Criterio de resolución

La decisión se acepta cuando E2-09 tiene migraciones versionadas, pruebas de reinicio/concurrencia y Gate A evidencia una ejecución/turno/entrega lógica por evento. Hasta entonces H4 está bloqueado.

## Relacionado

- ADR-ORCH-021 (propuesto)
- ADR-ORCH-023 (propuesto)
- E2-09 / Gate A
