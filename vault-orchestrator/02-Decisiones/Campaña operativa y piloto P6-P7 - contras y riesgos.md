---
tipo: decision_contras
tema: Campaña operativa y piloto P6-P7
estado: aceptado
fecha: 2026-11-11
---

# Contras y Riesgos de la Campaña Operativa y Piloto (P6-P7)

1. **Impacto de latencia en dependencias externas:** Dado que el proveedor LLM (OpenAI) y la persistencia (Neon AWS us-east-2) son servicios gestionados externos, la degradación en sus redes o tiempos de cómputo fríos repercute directamente en la latencia final del orchestrator.
2. **Límites de conexión en bases de datos compartidas:** Aunque el pooler acotado mitiga la sobrecarga (`max=10`), un incremento abrupto de sesiones concurrentes (> 20) podría saturar el pool si no se escalan las Compute Units en Neon.
3. **Necesidad de disciplina operativa estricta:** La validez del procedimiento de rollback N-1 depende exclusivamente de que ninguna migración futura rompa retrocompatibilidad (*breaking DDL*); toda migración debe permanecer estrictamente *forward-only* y aditiva.

## Enlaces
- Investigación: [[Investigacion - campana operativa recuperacion y aceptacion del piloto P6-P7]]
- Beneficios: [[Campaña operativa y piloto P6-P7 - beneficios]]
- Decisión: [[Campaña operativa y piloto P6-P7 - decisión]]
- Estado de implementación: [[Campaña operativa y piloto P6-P7 - estado de implementación]]

