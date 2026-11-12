---
tipo: beneficios
tema: Integración consumidores externos y Orbit
estado: aceptado
fecha: 2026-11-11
---

# Integración consumidores externos y Orbit — beneficios

- **Estabilidad del contrato del Orchestrator:** mantiene intactos `/v1/executions`, `/v1/turns`, `/v1/knowledge/documents`, `/healthz` y `/readyz` sin introducir lógica específica de frontend o almacenamiento de Orbit en el servidor Python.
- **Reutilización entre proyectos:** el cliente desacoplado implementado del lado consumidor (`contracts/orchestrator.ts` + `OrchestratorClient`) encapsula autenticación `Bearer`, cabeceras `Idempotency-Key` / `X-Request-Id`, parser SSE CRLF/LF y clasificación de errores HTTP (`401`, `409`, `429`, `502/503`) sin dependencias de framework.
- **Trazabilidad entre repositorios:** alinea la documentación operativa de despliegue VPS (`Rollout y validación VPS P4-P5`) con el primer consumidor BFF real conectado por TLS público (`agent-staging.incubialab.com`).

## Enlaces

- Investigación: [[Investigacion - integracion consumidores externos y Orbit]]
- Decisión: [[Integración consumidores externos y Orbit - decisión]]

