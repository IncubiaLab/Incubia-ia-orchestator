---
tipo: implementacion
tema: Campaña operativa y piloto P6-P7
estado: implementado
fecha: 2026-11-11
---

# Estado de Implementación: Campaña Operativa y Piloto (P6-P7)

## Componentes implementados y ejecutados
- **Runner de Campaña P6 Automatizado:** Creado `scripts/e3/run_vps_p6_campaign.py`, ejecutando perfiles de carga, fallos de drenado, rollback N-1 y comprobación de backups contra el entorno VPS staging.
- **Artefacto de Evidencia E3-5:** Resultado de campaña consolidado y guardado en `evals/results/vps/e3-p6-vps-campaign.json`.
- **Runbook Operativo de Producción:** Publicado `docs/roadmap/etapa-3/RUNBOOK-VPS-OPERACIONAL.md` con instrucciones detalladas de despliegue, rollback, respaldo, restauración y rotación de credenciales.
- **Seguimiento del Plan Actualizado:** `docs/roadmap/etapa-3/PLAN-DESPLIEGUE-VPS.md` actualizado con el 100% de las fases marcadas como completadas.

## Evidencia verificada en la campaña P6
- **Carga Ráfaga (Burst):** 8 peticiones, 0 errores, p95 de latencia = 3071.56 ms (SLO ≤ 5000 ms).
- **Carga Sostenida (Sessions):** 29 peticiones, 0 errores, consistencia de revisiones verificada, p95 = 3371.70 ms.
- **Drenado SIGTERM:** Estado de readiness en drain verificado (`503 Service Unavailable`, `{"status":"draining"}`), apagado limpio y recuperación inmediata a `200 READY` sin fugas de conexiones (`db_in_use = 0`).
- **Rollback N-1:** Despliegue de imagen previa `e5206c4` validado sin errores de compatibilidad con el esquema migrado, seguido de rollforward exitoso a `staging`.
- **Respaldo Scoped:** Exportación con `h1_backup.py` verificada con hash `content_sha256 = ec408afba...` en 4.196 s.

## Bloqueos abiertos
- Ninguno. El ciclo completo de despliegue y validación operativa en el VPS de pruebas ha concluido con éxito.

## Enlaces
- Investigación: [[Investigacion - campana operativa recuperacion y aceptacion del piloto P6-P7]]
- Beneficios: [[Campaña operativa y piloto P6-P7 - beneficios]]
- Contras y riesgos: [[Campaña operativa y piloto P6-P7 - contras y riesgos]]
- Decisión: [[Campaña operativa y piloto P6-P7 - decisión]]

