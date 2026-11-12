---
tipo: investigacion
tema: Empaquetado reproducible y cadena completa de migraciones (P2)
estado: completado
fecha: 2026-11-11
---

# Investigación y Diseño — Empaquetado reproducible y cadena completa de migraciones (P2)

## Pregunta y alcance

¿Cómo asegurar que la imagen de contenedor del orchestrator para el VPS sea estrictamente reproducible, incluya `psycopg_pool` para la concurrencia en Neon, ejecute como usuario no-root (`10001:10001`) y cuente con un runner de migraciones que aplique la cadena completa de PostgreSQL (`001`–`008`) antes del despliegue?

## Hallazgos y Soluciones Implementadas

1. **Unificación de dependencias en `requirements.lock`:**
   - Se añadió `psycopg_pool==3.2.6` (consistente con `uv.lock` y `pyproject.toml`) a `requirements.lock`.
   - Se verificó que `pip install -r requirements.lock` provea tanto el driver `psycopg` / `psycopg-binary` como `psycopg_pool`.
2. **Dockerfile optimizado para el VPS (`Dockerfile.vps`):**
   - Construcción multi-stage partiendo de `python:3.12.10-slim-bookworm` fijado por digest SHA-256.
   - Creación de usuario y grupo de sistema `incubia` (`10001:10001`).
   - Directorio `/data` precreado con permisos `10001:10001` para persistencia en volumen escribible.
   - Entrypoint principal apuntando al nuevo servidor HTTP: `incubia_orchestrator.interfaces.http.service`.
   - Healthcheck integrado consultando `/healthz`.
3. **Runner de Migraciones Completo (`interfaces/http/migrate_all.py`):**
   - Resuelve el bloqueo #9 de `PLAN-VPS.md` (el runner anterior `migrate.py` solo aplicaba `001` y `006`).
   - Aplica en orden estricto las migraciones `001`–`008`:
     1. `001_e3_d0_ledger.sql`: tablas base de conversaciones, turnos y outbox.
     2. `002_e3_h1_rls.sql`: Row Level Security obligatoria por `deployment_id` y `tenant_id`.
     3. `003_e3_h1_claims.sql`: leases y fencing.
     4. `004_e3_h1_dispatcher_claims.sql`: claims de despacho.
     5. `005_e3_h1_backup.sql`: soporte para export/restore.
     6. `006_e3_d0_runtime_claims.sql`: claims de runtime.
     7. `007_e3_h2_identity.sql`: membresías y perfiles de identidad.
     8. `008_e3_g7_audit.sql`: tabla de auditoría durable `audit_events`.
   - Validación fail-closed de roles: rechaza roles de solo lectura (`incubia_runtime`) y exige rol migrador (`incubia_migrator`).
4. **Verificación en CI:**
   - Se agregó en `.github/workflows/ci.yml` el paso de construcción y comprobación de imports del contenedor en cada ejecución offline.

## Beneficios
Enlazar: [[Empaquetado y migraciones P2 - beneficios]]

## Contras y riesgos
Enlazar: [[Empaquetado y migraciones P2 - contras y riesgos]]

## Decisión
Enlazar: [[Empaquetado y migraciones P2 - decisión]]

## Estado de implementación
Enlazar: [[Empaquetado y migraciones P2 - estado de implementación]]
