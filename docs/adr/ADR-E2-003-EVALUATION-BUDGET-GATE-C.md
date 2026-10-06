# ADR-E2-003 — Presupuesto y evidencia de evaluación real para Gate C

**Status:** Proposed  
**Scope:** Etapa 2 / H5  
**Decision owner:** responsable de presupuesto

## Contexto

La calidad de routing y generación no se acredita con el fake. `eval-e2` reserva 150 llamadas y 400 tokens de salida, pero el tope monetario está deliberadamente en `null`; sin él no se permite invocar un proveedor real.

## Decisión pendiente

Registrar un `usd_cap` positivo para `eval-e2`, el archivo de contador `INCUBIA_EVAL_BUDGET_FILE`, el modelo/versión y la fuente vigente de precios. El cupo CLI de 6 llamadas no se reutiliza ni reinicia.

## Criterio de resolución

El ADR se acepta tras ejecutar `routing-v2` en `val` y la rúbrica de 12 escenarios, registrar matriz de confusión, latencias, tokens, costo estimado y limitaciones. Gate C requiere ≥80 % y cero fallos críticos definidos en GOALS.

## Relacionado

- E2-12 / Gate C
- `docs/roadmap/etapa-2/GOALS.md`
