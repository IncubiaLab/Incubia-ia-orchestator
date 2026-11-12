---
tipo: implementacion
estado: completado
fecha: 2026-11-11
---

# Empaquetado y migraciones P2 — estado de implementación

## Trabajo completado (P2)
- [x] Inclusión de `psycopg_pool==3.2.6` en `requirements.lock`.
- [x] Creación de `Dockerfile.vps` y build real verificado (`incubia-orchestrator:test-vps`).
- [x] Prueba de importación de módulos y comprobación de UID/GID no-root (`10001:10001`) dentro del contenedor.
- [x] Implementación y pruebas unitarias de `interfaces/http/migrate_all.py` (`tests/unit/test_migrate_all.py` passed).
- [x] Integración de build y validación de contenedor en `.github/workflows/ci.yml`.

## Siguiente paso: P3
- Preparar manifiesto Compose independiente para el VPS (`deploy/compose.vps.yaml`), plantilla de variables (`deploy/vps.env.example`) y configuración de observabilidad.

[[01-Investigacion/Empaquetado-P2/Investigacion - empaquetado reproducible y cadena completa de migraciones P2]] · [[Empaquetado y migraciones P2 - beneficios]] · [[Empaquetado y migraciones P2 - contras y riesgos]] · [[Empaquetado y migraciones P2 - decisión]]
