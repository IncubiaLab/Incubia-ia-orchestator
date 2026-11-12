---
tipo: investigacion
tema: Manifiestos VPS, persistencia y configuración operacional (P3)
estado: completado
fecha: 2026-11-11
---

# Investigación y Diseño — Manifiestos VPS, persistencia y configuración operacional (P3)

## Pregunta y alcance

¿Cómo estructurar los manifiestos de Docker Compose y plantillas de entorno para el VPS de manera que se integren directamente con la red `web` existente de Caddy, garanticen seguridad de contenedor (solo lectura, límites de CPU/RAM, usuario no-root) y mantengan la separación de roles entre el runtime y las migraciones?

## Hallazgos y Soluciones Implementadas

1. **Nuevo manifiesto independiente (`deploy/compose.vps.yaml`):**
   - No altera `compose.yaml` (que sigue sirviendo al baseline local D0).
   - Se conecta como red externa a **`web`** (la red que Caddy ya tiene creada en el VPS).
   - Servicio `orchestrator`:
     - Contenedor con `stop_grace_period: 70s` (alineado a los 60s de drenaje HTTP).
     - Límites de recursos aplicados: `cpus: 2.0`, `memory: 2048M`, `pids: 100`.
     - `read_only: true` con `tmpfs: [/tmp]` y volumen persistente `orchestrator-data:/data`.
     - `cap_drop: [ALL]` y `security_opt: [no-new-privileges:true]`.
     - Healthcheck integrado hacia `http://127.0.0.1:8080/healthz`.
   - Servicio `migrate` (one-shot):
     - Corre `interfaces.http.migrate_all` con `restart: "no"`.
     - Recibe exclusivamente `INCUBIA_MIGRATION_DATABASE_URL` (rol `incubia_migrator`).
2. **Plantilla de entorno (`deploy/vps.env.example`):**
   - Documenta claramente los secretos requeridos y su formato:
     - `INCUBIA_ORCHESTRATOR_TOKEN` (`>=32` caracteres hex).
     - `DATABASE_URL` con endpoint `-pooler`, `sslmode=require` y rol `incubia_runtime`.
     - `INCUBIA_MIGRATION_DATABASE_URL` directa para migraciones.
     - `OPENAI_API_KEY`, `INCUBIA_MODEL`, `INCUBIA_DEPLOYMENT_ID`.

## Beneficios
Enlazar: [[Manifiestos VPS y persistencia P3 - beneficios]]

## Contras y riesgos
Enlazar: [[Manifiestos VPS y persistencia P3 - contras y riesgos]]

## Decisión
Enlazar: [[Manifiestos VPS y persistencia P3 - decisión]]

## Estado de implementación
Enlazar: [[Manifiestos VPS y persistencia P3 - estado de implementación]]
