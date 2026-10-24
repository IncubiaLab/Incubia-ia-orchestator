# Campaña E3-3 — READ gobernado

Estado: evidencia técnica ejecutada el 2026-10-24; gate cerrado por el responsable el 2026-10-23.

## Alcance

El runner `scripts/e3/run_e3_3_campaign.py` prueba una única lectura pública
controlada de Open Food Facts mediante `ExecuteTool` y el PEP. En la misma
salida registra las rutas que nunca deben llegar al adapter:

- `ALLOW`: una llamada READ autorizada;
- `DENY`: cero llamadas externas;
- `INDETERMINATE`: cero llamadas externas;
- `REQUIRE_APPROVAL`: cero llamadas externas;
- input inválido: cero llamadas externas antes de policy.

El runner exige los cuatro opt-ins siguientes antes de construir el adapter
real: `INCUBIA_E3_3_CAMPAIGN=1`,
`INCUBIA_E3_3_BUDGET_APPROVED=1`,
`INCUBIA_E3_3_BUDGET_USD>=0.01` e `INCUBIA_E3_READ_REAL=1`. `--dry-run` no
crea artefactos ni hace I/O remoto. Los artefactos mantienen
`gate_closed=false`: pasar pruebas no sustituye la decisión del responsable.

## Resultado 2026-10-24

La ejecución real controlada está registrada en
[`e3-3-campaign-2026-10-24.json`](../../../evals/results/e3-3-campaign-2026-10-24.json):

- `ALLOW`: `SUCCESS`, una llamada al adapter y cuatro eventos de auditoría.
- `DENY`, `INDETERMINATE`, `REQUIRE_APPROVAL` e input inválido: cero llamadas
  al adapter; cada caso produjo eventos de auditoría.
- `zero_call_safety=true`, `total_adapter_calls=1`, presupuesto aprobado de
  USD 0,01 y `gate_closed=false`.

Los controles offline están en `tests/unit/test_e3_3_campaign.py`,
`tests/integration/test_openfoodfacts_read.py` y
`tests/integration/test_read_tool.py`.

## Decisión del gate

El responsable aceptó y cerró E3-3 el 2026-10-23 tras revisar la evidencia,
presupuesto y operación. El artefacto conserva `gate_closed=false` por diseño:
esa bandera expresa que el runner no puede autoautorizar el cierre; la decisión
de este expediente es la autoridad de cierre.
