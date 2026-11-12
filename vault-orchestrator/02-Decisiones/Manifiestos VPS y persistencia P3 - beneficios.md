# Manifiestos VPS y persistencia P3 — beneficios

Fecha: 2026-11-11.

- **Integración limpia con Caddy:** El orchestrator corre dentro de la red `web` sin publicar puertos al exterior del host, protegiendo el endpoint detrás de Caddy.
- **Seguridad en profundidad:** Contenedor endurecido (`read_only`, `cap_drop: ALL`, sin nuevos privilegios y límites estrictos de CPU y memoria de 2 GB).
- **Separación de privilegios en despliegue:** La aplicación en ejecución nunca recibe credenciales DDL de migración; el servicio `migrate` corre de forma puntual y aislada.

[[01-Investigacion/Manifiestos-P3/Investigacion - manifiestos VPS persistencia y configuracion operacional P3]] · [[Manifiestos VPS y persistencia P3 - contras y riesgos]] · [[Manifiestos VPS y persistencia P3 - decisión]] · [[03-Implementacion/Manifiestos VPS y persistencia P3 - estado de implementación]]
