---
tipo: operacion
tema: Inventario del VPS de pruebas (P0)
estado: completado
fecha: 2026-11-11
---

# VPS de pruebas — Inventario operativo (P0)

Resultado del inventario no destructivo ejecutado por SSH sobre `hector@2.24.201.39` (`srv2113451`) el 2026-11-11, correspondiente a la fase **P0** de [[docs/roadmap/etapa-3/PLAN-DESPLIEGUE-VPS.md|PLAN-DESPLIEGUE-VPS.md]].

## 1. Hardware y Sistema Operativo

| Recurso | Detalle observado | Capacidad disponible |
|---|---|---|
| **CPU** | 4 vCPU KVM, AMD EPYC 9354P 32-Core Processor (1 socket, 1 thread/core) | Capacidad muy superior a la estimación inicial (2 vCPU) |
| **Memoria RAM** | 15 GiB Total, 653 MiB usados, **14 GiB disponibles** (Swap: 0B) | Margen amplio para orchestrator, runtime y pool de conexiones |
| **Almacenamiento** | Disco `/dev/sda1` de 193 GB (5.0 GB en uso, **188 GB libres**, 3% uso) | Margen amplio para `/data`, imágenes Docker N y N-1 |
| **Sistema Operativo** | Ubuntu 24.04.5 LTS (`x86_64`), Kernel `6.8.0-147-generic` | Mantenido y totalmente compatible |

## 2. Docker, Red y Permisos

- **Docker Engine:** `29.9.3`, build `5457199`.
- **Docker Compose:** plugin `v5.7.0`.
- **Usuario SSH `hector`:** `uid=1003(hector)`, grupos: `docker (988)`, `incubia-ops (1001)`, `sudo (27)`. Puede gestionar Docker y tiene permisos de escritura en `/opt/incubia/` vía GID `incubia-ops`.

## 3. Servicios Coexistentes y Proxy HTTPS (Caddy)

- **Contenedores activos:** Existe un único contenedor `caddy` (`caddy:2`), gestionado por Compose desde `/opt/incubia/proxy/docker-compose.yml`.
- **Red externa de Docker:** Red bridge externa llamada **`web`** (`8b7dd020f2c7`), a la cual está conectado Caddy.
- **Puertos escuchando en el host:**
  - `0.0.0.0:80` y `[::]:80` -> Caddy (HTTP)
  - `0.0.0.0:443` y `[::]:443` -> Caddy (HTTPS / HTTP/3 QUIC)
  - `0.0.0.0:22` y `[::]:22` -> OpenSSH
  - Puertos 8080 y 8081 **libres**.
- **Dominios y TLS verificados activos:**
  - `agent-staging.incubialab.com` -> TLS automático Let's Encrypt / ZeroSSL en Caddy (respondiendo `200 OK`).
  - `agent.incubialab.com` -> TLS automático en Caddy (respondiendo `200 OK`).
- **Estructura en `/opt/incubia`:**
  - `/opt/incubia/proxy/`: `docker-compose.yml` y `Caddyfile`.
  - `/opt/incubia/staging/`: directorio listo con permisos `deploy:incubia-ops (2775)` para el despliegue del orchestrator en staging.
  - `/opt/incubia/prod/`: directorio reservado para producción.

## 4. Conclusiones y Decisiones de Despliegue para P1–P4

1. **Ingreso y Red:** El orchestrator (en staging) se conectará a la red Docker existente `web` (o expondrá `127.0.0.1:8080`), y Caddy enrutará `agent-staging.incubialab.com` hacia `http://orchestrator-staging:8080` con buffering desactivado (para SSE) y timeouts `>= 60s`.
2. **Ubicación de archivos:** `/opt/incubia/staging/` alojará `docker-compose.yml` y el archivo de entorno `.env` (modo `0600`).
3. **Persistencia local:** Volumen Docker dedicado para `/data` (UID/GID `10001:10001`).

[[docs/roadmap/etapa-3/PLAN-DESPLIEGUE-VPS.md|PLAN-DESPLIEGUE-VPS.md]] · [[VPS de pruebas - acceso SSH]] · [[Despliegue del orchestrator en VPS - estado de implementación]]
