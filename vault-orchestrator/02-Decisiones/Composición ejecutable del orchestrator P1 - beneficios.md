# Composición ejecutable del orchestrator P1 — beneficios

Fecha: 2026-11-11.

- **Unifica los puntos de entrada:** Centraliza en un único servidor HTTP (`service.py`) tanto las ejecuciones canónicas de API (`/v1/executions`) como las consultas de Orbit (`/v1/turns`), eliminando la fragmentación de puertos y procesos.
- **Persistencia durable y trazabilidad completa para Orbit:** Las respuestas entregadas a Orbit ahora quedan registradas atómicamente en `PostgresLedger` y auditadas en `PostgresAuditLog`.
- **Eliminación del límite local de pruebas:** Reemplaza el `MonthlyCallLimiter` (20 llamadas/mes) por límites operativos y de admisión de producción (`AdmissionLimiter`, `config/e3/limits.example.yaml`).
- **Readiness y Apagado confiables:** `/readyz` reporta el estado real de la base de datos y de las dependencias, y el drenaje de 60 segundos evita cortar llamadas activas del LLM ante despliegues o reinicios.

[[01-Investigacion/Composicion-P1/Investigacion - composicion ejecutable del orchestrator P1]] · [[Composición ejecutable del orchestrator P1 - contras y riesgos]] · [[Composición ejecutable del orchestrator P1 - decisión]] · [[03-Implementacion/Composición ejecutable del orchestrator P1 - estado de implementación]]

