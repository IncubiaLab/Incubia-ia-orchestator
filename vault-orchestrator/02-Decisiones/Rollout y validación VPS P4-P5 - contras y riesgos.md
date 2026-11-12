---
tipo: decision_contras
tema: Rollout y validación VPS P4-P5
estado: aceptado
fecha: 2026-11-11
---

# Contras y Riesgos del Rollout y Validación en VPS Staging (P4-P5)

1. **Gestión y rotación de secretos en `.env`:** El archivo `/opt/incubia/staging/.env` reside en disco con permisos restringidos (`0600`). Si bien no está expuesto en Git, cualquier rotación de llaves (OpenAI, Neon o token de orchestrator) requiere intervención manual o scripting seguro.
2. **Dependencia de latencia de red hacia Neon:** La persistencia conversacional y de auditoría se efectúa contra un endpoint externo en AWS us-east-2. Picos de latencia en la red pública o límites de conexión del pooler Neon pueden afectar la latencia global p95.
3. **Consumo de cuota en proveedores LLM:** Al ejecutar llamadas funcionales reales con OpenAI, los tests E2E y de humo consumen tokens presupuestados. Es imperativo mantener topes de llamadas y monitorear el gasto mediante el módulo de métricas.

## Enlaces
- Investigación: [[Investigacion - rollout en VPS staging y validacion funcional E2E P4-P5]]
- Beneficios: [[Rollout y validación VPS P4-P5 - beneficios]]
- Decisión: [[Rollout y validación VPS P4-P5 - decisión]]
- Estado de implementación: [[Rollout y validación VPS P4-P5 - estado de implementación]]
