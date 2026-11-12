# Manifiestos VPS y persistencia P3 — contras y riesgos

Fecha: 2026-11-11.

- **Dependencia de la red externa `web`:** Requiere que la red `web` de Docker esté creada en el host antes de ejecutar `docker compose up` (en P0 ya se verificó que la red existe en el VPS).
- **Ajuste en Caddyfile:** Caddy debe configurarse para enrutar el host `agent-staging.incubialab.com` hacia `http://orchestrator-staging:8080` (o el nombre de contenedor configurado).

[[01-Investigacion/Manifiestos-P3/Investigacion - manifiestos VPS persistencia y configuracion operacional P3]] · [[Manifiestos VPS y persistencia P3 - beneficios]] · [[Manifiestos VPS y persistencia P3 - decisión]] · [[03-Implementacion/Manifiestos VPS y persistencia P3 - estado de implementación]]
