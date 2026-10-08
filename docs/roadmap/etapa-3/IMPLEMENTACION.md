# Implementación — backlog etapa 3

Estado: todas las tareas pendientes. Rutas propuestas relativas a `src/incubia_orchestrator/`, salvo config/tests/scripts/migrations/deploy/evals/docs. Los archivos se crean al abrir el slice; no representan código existente.

| Tarea | Hito | Entregable | Dependencias E3 | Goals | Estado |
| --- | --- | --- | --- | --- | --- |
| [E3-01](PLAN-E3.md#e3-01) | H0 | Inventario y decisiones | — | G1/G9 | Pendiente |
| [E3-02](PLAN-E3.md#e3-02) | H0 | Contratos de identidad y unidad de trabajo | 01 | G1/G2/G3 | Pendiente |
| [E3-03](PLAN-E3.md#e3-03) | H1 | PostgreSQL y migraciones | 02 | G2/G3 | Pendiente |
| [E3-04](PLAN-E3.md#e3-04) | H1 | Claims, fencing y outbox compartida | 03 | G2 | Pendiente |
| [E3-05](PLAN-E3.md#e3-05) | H1 | Migración y restore Neon | 04 | G2/G9 | Pendiente |
| [E3-06](PLAN-E3.md#e3-06) | H2 | Identidad, membresías y policy | 02/03 | G3 | Pendiente |
| [E3-07](PLAN-E3.md#e3-07) | H3 | Contratos Tool Registry y Discovery | 02/06 | G4 | Pendiente |
| [E3-08](PLAN-E3.md#e3-08) | H3 | Tool Executor y adapter READ | 07 | G4/G7 | Pendiente |
| [E3-09](PLAN-E3.md#e3-09) | H4 | Contratos Knowledge y dataset | 02/06 | G5/G6 | Pendiente |
| [E3-10](PLAN-E3.md#e3-10) | H4 | Decisión vectorial e ingestión | 09/03 | G5 | Pendiente |
| [E3-11](PLAN-E3.md#e3-11) | H4 | Respuesta combinada y contexto | 08/10 | G5/G6 | Pendiente |
| [E3-12](PLAN-E3.md#e3-12) | H5 | Auditoría, métricas y despliegue | 04/08/11 | G7/G9 | Pendiente |
| [E3-13](PLAN-E3.md#e3-13) | H5 | Carga, fallos y operación | 05/06/12 | G2/G3/G7/G9 | Pendiente |
| [E3-14](PLAN-E3.md#e3-14) | H6 | Leads y casos internos | 06/11 | G8 | Pendiente |
| [E3-15](PLAN-E3.md#e3-15) | H6 | Evaluación y cierre | 13/14 | G1–G9 | Pendiente |

## Orden de ejecución

E3-01 → E3-02 → E3-03 → E3-04 → E3-05. E3-06 puede avanzar tras E3-03; E3-07/08 y E3-09/10 tienen contratos comunes y convergen en E3-11. E3-12/13 preparan operación; E3-14 construye flows internos; E3-15 cierra evidencia.

El diseño y trabajo offline pueden comenzar con E2 B/C abiertos. E3-0 y piloto integrado requieren su cierre. Los gates de datos/identidad se comprueban antes de conectar fuentes reales. Las dependencias sobre fixtures no autorizan acceso productivo.

Estimaciones y fechas se fijan después de E3-01 con disponibilidad de responsables, accesos y límites; las fechas históricas de Linear no son compromisos de este backlog.
