---
tipo: decision
estado: aceptada
fecha: 2026-11-11
---

# Manifiestos VPS y persistencia P3 — decisión

Se adopta:
1. `deploy/compose.vps.yaml` como manifiesto Docker Compose oficial para VPS de pruebas y producción.
2. `deploy/vps.env.example` como plantilla documentada para variables de entorno del servidor.
3. El servicio HTTP no publica puertos al host (`127.0.0.1` o `0.0.0.0`), sino que se comunica exclusivamente a través de la red Docker `web` con el proxy reverso Caddy.

[[01-Investigacion/Manifiestos-P3/Investigacion - manifiestos VPS persistencia y configuracion operacional P3]] · [[Manifiestos VPS y persistencia P3 - beneficios]] · [[Manifiestos VPS y persistencia P3 - contras y riesgos]] · [[03-Implementacion/Manifiestos VPS y persistencia P3 - estado de implementación]]
