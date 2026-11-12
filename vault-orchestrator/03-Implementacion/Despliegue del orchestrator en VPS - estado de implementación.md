---
tipo: implementacion
estado: reconciliado-en-main-bloqueos-vps-identificados
fecha: 2026-11-11
---

# Despliegue del orchestrator en VPS — estado de implementación

## Implementado y verificado en el repositorio

- **VPS de pruebas identificado:** acceso SSH por clave a `hector@2.24.201.39` verificado el 2026-11-11; ficha operativa en [[VPS de pruebas - acceso SSH]]. Esto acredita acceso al host, no despliegue ni disponibilidad del servicio.
- **Paso 1 de `PLAN-VPS.md` completado:** Mapa integral del runtime, módulos, *composition roots*, procesos, persistencia y dependencias externas documentado y convergente en este vault.
- **Reconciliación de rama `main`:** Todo el trabajo verificado de Etapa 3 (`feat/knowledge-base` / `dev/3-tier`: `PostgresLedger`, `PooledConnections`, `PostgresAuditLog`, `KnowledgePools`, ingesta Drive, tools READ Open Food Facts, `DrainingHTTPServer` con conteo de solicitudes en vuelo, ADRs `008`–`027` y suites E3) queda integrado en `main` junto con `orbit_gateway.py` y `PLAN-VPS.md`.
- **Gates cerrados por el responsable (2026-10-23):** `E3-D0-L`, `E3-1` (persistencia/fencing/restore M3), `E3-2` (aislamiento multi-tenant/RLS), `E3-3` (tools READ gobernadas) y `E3-4` (RAG G5/G6 en Neon).

## Plan de ejecución del VPS de pruebas — 2026-11-11

El [plan P0–P7](../../docs/roadmap/etapa-3/PLAN-DESPLIEGUE-VPS.md) contrasta `PLAN-VPS.md` con `main` (`5a7df31`).
- **P0 Completado (2026-11-11):** Inventario de hardware (4 vCPU, 15 GiB RAM, 188 GiB libres), Docker 29.9 / Compose v5.7, proxy Caddy en red `web`, dominios `agent.incubialab.com` y `agent-staging.incubialab.com` con TLS activo, y directorios operativos en `/opt/incubia/`. Ficha en [[VPS de pruebas - inventario operativo P0]].
- **P1–P7 en curso/pendientes:** Composición completa, imagen reproducible, configuración y rollout.

## Pendiente antes del despliegue productivo en VPS (Pasos 2–6 de `PLAN-VPS.md`)

- [ ] Unificar el empaquetado de dependencias (`psycopg[binary]` y `psycopg_pool` en el lock de imagen Docker) y verificar build + arranque en CI.
- [ ] Ampliar el job de migración productiva para aplicar `migrations/postgres/001..008` y `migrations/knowledge/001..002` con sus roles respectivos.
- [ ] Conectar en un *composition root* productivo el ingreso HTTP autenticado con `PostgresLedger`, `PostgresAuditLog`, `GroundedWorkflow`/`KnowledgePools` y límites operativos (`config/e3/limits.example.yaml`), separando el `MonthlyCallLimiter` de pruebas locales.
- [ ] Alinear `max_output_tokens`, `drain_seconds` y `/readyz` en la interfaz HTTP y ejecutar la campaña integrada pendiente de `E3-5` y `E3-6`.

[[01-Investigacion/Despliegue-VPS/Investigacion - despliegue del orchestrator en VPS]] · [[Despliegue del orchestrator en VPS - beneficios]] · [[Despliegue del orchestrator en VPS - contras y riesgos]] · [[Despliegue del orchestrator en VPS - decisión]]
