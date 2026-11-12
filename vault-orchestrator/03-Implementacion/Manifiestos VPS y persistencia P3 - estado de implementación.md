---
tipo: implementacion
estado: completado
fecha: 2026-11-11
---

# Manifiestos VPS y persistencia P3 — estado de implementación

## Trabajo completado (P3)
- [x] Creación y validación sintáctica de `deploy/compose.vps.yaml`.
- [x] Creación de `deploy/vps.env.example` con variables de conexión a Neon pooled/direct, token Bearer y parámetros de runtime.
- [x] Configuración de red externa `web` conectada a Caddy y volumen `/data`.
- [x] Documentación en el vault de Obsidian.

## Siguiente paso: P4
- Despliegue en el VPS (`hector@2.24.201.39`), preparación de `/opt/incubia/staging/`, ajuste de Caddyfile y primer rollout privado.

[[01-Investigacion/Manifiestos-P3/Investigacion - manifiestos VPS persistencia y configuracion operacional P3]] · [[Manifiestos VPS y persistencia P3 - beneficios]] · [[Manifiestos VPS y persistencia P3 - contras y riesgos]] · [[Manifiestos VPS y persistencia P3 - decisión]]
