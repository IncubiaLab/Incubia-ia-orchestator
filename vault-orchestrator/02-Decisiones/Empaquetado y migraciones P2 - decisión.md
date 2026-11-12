---
tipo: decision
estado: aceptada
fecha: 2026-11-11
---

# Empaquetado y migraciones P2 — decisión

Se adopta:
1. `requirements.lock` unificado con `psycopg_pool==3.2.6`.
2. `Dockerfile.vps` multi-stage con base fijada por digest, no-root `10001:10001` y healthcheck a `/healthz`.
3. `interfaces/http/migrate_all.py` como runner oficial para la cadena `001`–`008` en PostgreSQL Neon.
4. Gate de verificación de build y contenedor en CI.

[[01-Investigacion/Empaquetado-P2/Investigacion - empaquetado reproducible y cadena completa de migraciones P2]] · [[Empaquetado y migraciones P2 - beneficios]] · [[Empaquetado y migraciones P2 - contras y riesgos]] · [[03-Implementacion/Empaquetado y migraciones P2 - estado de implementación]]
