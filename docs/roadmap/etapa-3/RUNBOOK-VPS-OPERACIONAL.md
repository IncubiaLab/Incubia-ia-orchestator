# Runbook Operativo: Despliegue, Rollback y Operación en VPS

**Entorno:** Staging / Piloto VPS (`hector@2.24.201.39` / `srv2113451`)  
**Dominio público:** `https://agent-staging.incubialab.com`  
**Referencia arquitectónica:** `ADR-ORCH-001`, `ADR-ORCH-024`, `ADR-ORCH-025`, `ADR-ORCH-027`, `PLAN-VPS.md`

---

## 1. Topología y Arquitectura del Entorno

- **Host VPS:** Ubuntu 24.04 LTS, 4 vCPU AMD EPYC, 16 GB RAM, 190 GB SSD NVMe.
- **Perímetro de red:**
  - Caddy (`caddy:2`) gestiona TLS automático en los puertos `80/tcp` y `443/tcp/udp` en la red Docker `web`.
  - El orchestrator (`orchestrator-staging`) corre conectado a la red interna `web` sin publicar puertos en el host.
  - Caddy enruta `agent-staging.incubialab.com` hacia `http://orchestrator-staging:8080` con `flush_interval -1` para streaming SSE en tiempo real.
- **Persistencia Externa (Neon PostgreSQL):**
  - Conexión runtime pooled TLS con rol de mínimo privilegio `incubia_runtime` (`NOBYPASSRLS`).
  - Conexión directa no-pooled TLS para migraciones con rol `incubia_migrator`.

---

## 2. Procedimiento de Despliegue y Actualización

### 2.1 Compilación y Transferencia de Imagen
Desde el entorno de desarrollo o runner CI:

```bash
# 1. Compilar imagen
docker build -f Dockerfile.vps -t incubia-orchestrator:staging .

# 2. Transferir imagen al VPS
docker save incubia-orchestrator:staging | gzip -1 | ssh hector@2.24.201.39 "gunzip -c | docker load"
```

### 2.2 Ejecución de Migraciones
Las migraciones deben ejecutarse antes de reiniciar la aplicación:

```bash
ssh hector@2.24.201.39 "cd /opt/incubia/staging && docker compose run --rm migrate"
```
*Si la migración falla, el runner aborta fail-closed y NO se reinicia el contenedor de aplicación.*

### 2.3 Despliegue de la Aplicación
```bash
ssh hector@2.24.201.39 "cd /opt/incubia/staging && docker compose up -d --force-recreate orchestrator"
```

### 2.4 Verificación Inmediata de Salud
```bash
# Healthcheck de proceso
curl -sI https://agent-staging.incubialab.com/healthz

# Readiness contra base de datos y pool
curl -sI https://agent-staging.incubialab.com/readyz
```

---

## 3. Procedimiento de Rollback de Aplicación (N-1)

Bajo la regla *expand/contract* de migraciones, el esquema de base de datos siempre es compatible con la imagen anterior (N-1).

1. **Editar la imagen en `/opt/incubia/staging/.env`:**
   ```bash
   ssh hector@2.24.201.39
   cd /opt/incubia/staging
   # Reemplazar la versión actual por el digest o commit previo N-1
   sed -i 's/INCUBIA_IMAGE=incubia-orchestrator:staging/INCUBIA_IMAGE=incubia-orchestrator:<digest-n-1>/' .env
   ```

2. **Recrear el contenedor con la imagen N-1:**
   ```bash
   docker compose up -d --force-recreate orchestrator
   ```

3. **Verificar estado:**
   ```bash
   curl -sI https://agent-staging.incubialab.com/readyz
   ```

---

## 4. Procedimiento de Respaldo y Restauración de Datos

### 4.1 Exportar Respaldo Scoped del Ledger
```bash
set -a; . deploy/e3-neon.env; set +a
PYTHONPATH=src .venv/bin/python scripts/e3/h1_backup.py export \
  --database-url-env DATABASE_URL \
  --deployment-id incubia-staging \
  --tenant-id <tenant_id> \
  --output /var/backups/incubia/backup-<timestamp>.json
```

### 4.2 Restaurar Respaldo Scoped
```bash
set -a; . deploy/e3-neon.env; set +a
PYTHONPATH=src .venv/bin/python scripts/e3/h1_backup.py import \
  --database-url-env INCUBIA_MIGRATION_DATABASE_URL \
  --package /var/backups/incubia/backup-<timestamp>.json
```

---

## 5. Rotación de Secretos

El archivo `/opt/incubia/staging/.env` tiene permisos estrictos `0600` (`deploy:incubia-ops`).

1. **Rotación de `INCUBIA_ORCHESTRATOR_TOKEN`:**
   - Generar nuevo token seguro: `python3 -c "import secrets; print(secrets.token_urlsafe(36))"`.
   - Actualizar `INCUBIA_ORCHESTRATOR_TOKEN` en `/opt/incubia/staging/.env`.
   - Reiniciar orchestrator: `docker compose restart orchestrator`.
   - Notificar al consumidor (Orbit Gateway) con la nueva credencial.

2. **Rotación de Credenciales de Base de Datos:**
   - Crear o rotar contraseña del rol en Neon PostgreSQL:
     ```sql
     ALTER ROLE incubia_runtime WITH PASSWORD '<nuevo_password>';
     ```
   - Actualizar `DATABASE_URL` en `/opt/incubia/staging/.env`.
   - Reiniciar orchestrator: `docker compose restart orchestrator`.

---

## 6. Monitoreo, Alertas y Métricas

- **Endpoint de métricas:** `GET https://agent-staging.incubialab.com/metrics`.
- **Métricas clave:**
  - `requests`: Contador global de peticiones.
  - `server_errors`: Contador de respuestas HTTP 5xx (debe ser 0).
  - `db_pool.in_use`: Conexiones activas tomadas del pool (debe converger a 0 tras procesamiento).
  - `stage_latency_ms.reception_to_delivery`: Histogramas de latencia (objetivo: p95 ≤ 5000 ms).
- **Criterio de Parada Fail-Closed:**
  - Si `/readyz` devuelve `503 Service Unavailable`, Caddy o el balanceador detiene la admisión de tráfico.
  - Si la auditoría durable falla o se agota la cuota presupuestada, el orchestrator aborta la ejecución antes de invocar efectos externos.

