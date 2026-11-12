---
tipo: decision_beneficios
tema: Campaña operativa y piloto P6-P7
estado: aceptado
fecha: 2026-11-11
---

# Beneficios de la Campaña Operativa y Aceptación del Piloto (P6-P7)

1. **Acreditación empírica de SLOs:** Se comprobó mediante carga ráfaga y sostenida que el p95 de latencia (3.07 s en ráfaga y 3.37 s sostenido) satisface ampliamente el objetivo ratificado (p95 ≤ 5.0 s), incluso con invocaciones reales a OpenAI y persistencia remota en Neon.
2. **Cero pérdida ante paradas imprevistas o redeploys:** La verificación de drenado SIGTERM certifica que el servidor suspende la admisión en `/readyz` y permite que las peticiones en vuelo terminen limpiamente antes de liberar recursos.
3. **Rollback instantáneo de imagen:** La comprobación de arranque de la imagen previa N-1 (`e5206c4`) contra el esquema migrado valida la regla *expand/contract*, permitiendo revertir cualquier incidente de aplicación en segundos sin tocar la base de datos.
4. **Respaldo granular con integridad garantizada:** `h1_backup.py` genera manifiestos criptográficos reproducibles por scope de tenant y deployment, garantizando RTO < 1 h y RPO < 12 h.
5. **Autosuficiencia operativa:** La entrega de `RUNBOOK-VPS-OPERACIONAL.md` permite a cualquier operador desplegar, monitorear, rotar secretos y recuperar el servicio de manera autónoma.

## Enlaces
- Investigación: [[Investigacion - campana operativa recuperacion y aceptacion del piloto P6-P7]]
- Contras y riesgos: [[Campaña operativa y piloto P6-P7 - contras y riesgos]]
- Decisión: [[Campaña operativa y piloto P6-P7 - decisión]]
- Estado de implementación: [[Campaña operativa y piloto P6-P7 - estado de implementación]]

