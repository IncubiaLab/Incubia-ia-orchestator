---
tipo: decision
tema: Campaña operativa y piloto P6-P7
estado: aceptado
fecha: 2026-11-11
---

# Decisión sobre la Campaña Operativa y Aceptación del Piloto (P6-P7)

Se da por completada y formalmente aceptada la campaña operativa y la puesta en marcha del piloto en el VPS de pruebas (`2.24.201.39`):
1. **Aceptación de SLOs de rendimiento y resiliencia:**
   - SLO p95 ≤ 5000 ms ratificado y cumplido (observado: 3071.56 ms en ráfaga y 3371.70 ms en sostenido).
   - RTO ≤ 1 h cumplido (observado: 0.07 min para reinicio y conmutación de contenedor).
   - RPO ≤ 12 h cumplido (observado: 0 h gracias al ledger transaccional PostgreSQL).
2. **Procedimientos operativos estandarizados:**
   - Adopción de `RUNBOOK-VPS-OPERACIONAL.md` como guía canónica para despliegues, actualizaciones, rollbacks y contingencias.
   - Preservación del perímetro seguro: sin puertos expuestos en el host, todo el tráfico cursa por Caddy TLS en la red Docker `web`.
3. **Cierre de fases:**
   - Todas las fases del plan VPS (`P0`, `P1`, `P2`, `P3`, `P4`, `P5`, `P6`, `P7`) se declaran cerradas con evidencia empírica archivada en `evals/results/vps/e3-p6-vps-campaign.json`.

## Enlaces
- Investigación: [[Investigacion - campana operativa recuperacion y aceptacion del piloto P6-P7]]
- Beneficios: [[Campaña operativa y piloto P6-P7 - beneficios]]
- Contras y riesgos: [[Campaña operativa y piloto P6-P7 - contras y riesgos]]
- Estado de implementación: [[Campaña operativa y piloto P6-P7 - estado de implementación]]

