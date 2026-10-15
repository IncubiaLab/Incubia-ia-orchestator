# E3-1 — Expediente de campaña integrada

Esta plantilla define el expediente que M3 debe producir para solicitar el
cierre de H1. El runner es `scripts/e3/run_h1_campaign.py`; su salida JSON
debe conservarse como evidencia versionada o adjunta al registro de decisión.

El runner nunca cierra el gate por sí solo: produce `open` o
`ready_for_gate`, y la decisión humana/arquitectónica se registra después de
revisar este expediente. `ready_for_gate` tampoco sustituye la firma de la
decisión en Linear.

## Comando reproducible

La campaña local no necesita red:

```bash
uv run --isolated --extra test --extra deployment python scripts/e3/run_h1_campaign.py \
  --phase offline \
  --output evals/results/e3-1-campaign-<UTC>.json
```

La campaña completa requiere artefactos JSON aprobados de M1/M2 y un manifest
sintético. Neon sólo se habilita con doble opt-in y usa los DSNs del archivo
local ignorado `deploy/e3-neon.env`; nunca se copian al expediente:

```bash
uv run --isolated --extra test --extra deployment python scripts/e3/run_h1_campaign.py \
  --phase all \
  --include-neon \
  --m1-evidence evals/results/e3-1-m1.json \
  --m2-evidence evals/results/e3-1-m2.json \
  --dataset-manifest evals/results/e3-1-dataset.json \
  --output evals/results/e3-1-campaign-<UTC>.json
```

El runner exige `INCUBIA_E3_NEON_TESTS=1`,
`INCUBIA_E3_NEON_BRANCH=e3-h1-synthetic` y hosts `.neon.tech` antes de
ejecutar la campaña Neon. No debe ejecutarse contra `production`.

Si no se dispone de un DSN PostgreSQL local, la fase `postgres` usa el smoke
Compose sólo con doble opt-in (`E3_D0_COMPOSE_SMOKE=1`); su evidencia queda
separada de Neon.

## Checklist de salida

| ID | Evidencia | Resultado esperado | Estado |
| --- | --- | --- | --- |
| M3-01 | Suite offline dirigida | Contratos SQLite, Gate A, recuperación, deduplicación y `UNKNOWN_EFFECT` pasan | `passed`: 27 passed en la campaña dirigida |
| M3-02 | PostgreSQL local / Compose | Equivalencia del contrato, readiness, replay, reinicio, recuperación y rollback lógico sin filas parciales | `passed`: E3-D0-L smoke, proyecto `incubia-e3-d0-final`, 52.569 s; imagen reutilizada con `E3_D0_SKIP_BUILD=1` |
| M3-03 | Suite Neon separada | TLS, rol runtime, RLS, UoW, claims/fencing y migraciones pasan en rama sintética | `passed`: 8 passed en 204.17 s sobre `e3-h1-synthetic`; restore M2 con filas acreditado |
| M3-04 | Manifest sintético | `synthetic=true`, hash y versión del dataset conservados | [Dataset](../../../evals/results/e3-h1-dataset-2026-10-10.json) |
| M3-05 | Evidencia M1 | JSON con `milestone=M1`, `status=passed|complete|accepted`, cero fallos críticos | [M1](../../../evals/results/e3-h1-m1-2026-10-10.json) |
| M3-06 | Evidencia M2 | JSON con `milestone=M2`, `status=passed|complete|accepted`, cero fallos críticos, RPO/RTO | [M2 Neon](../../../evals/results/e3-h1-m2-neon-2026-10-10.json) |
| M3-07 | Revisión de secretos | Sin DSN, contraseña, token, prompt o payload sensible en artefactos/logs | `passed`: runner sanitiza DSN/secretos; smoke valida logs locales |
| M3-08 | Decisión E3-1 | Registro de Linear con responsable, fecha, límites y expiración | Pendiente |

Un check `pending` o `failed`, un artefacto ausente, un hash conflictivo,
pérdida/duplicación lógica, bypass de RLS o RPO/RTO no medible mantiene H1
abierto.

## Contrato de artefactos M1/M2

Cada milestone debe entregar un JSON similar a:

```json
{
  "milestone": "M1",
  "status": "passed",
  "critical_failures": 0,
  "campaign_branch": "e3-h1-synthetic",
  "tests": {"passed": 0, "failed": 0, "skipped": 0},
  "evidence": [
    {"id": "M1-01", "result": "passed", "command": "...", "observed_at": "..."}
  ],
  "limits": ["..."],
  "owner": "..."
}
```

El comando de M3 valida únicamente la forma mínima, el estado, el milestone,
la ausencia de fallos críticos y el hash del archivo. La revisión debe
confirmar el contenido, los n/denominadores, los tiempos y la relación con
los commits implementados.

## Registro de ejecución

Completar al revisar el JSON generado:

| Campo | Valor |
| --- | --- |
| Campaign ID | Ver artefacto generado |
| Fecha UTC | 2026-10-13 |
| Commit | `f1e43a1` + working tree de etapa 3 |
| Rama Neon | `e3-h1-synthetic` / `<nueva rama si expiró>` |
| Migraciones y hashes | `<migrations>` |
| Dataset hash | `<sha256>` |
| Resultado runner | `ready_for_gate`; `gate_closed=false` |
| Decisión E3-1 | `Pendiente; no cerrar desde el script` |
| Responsable | `<nombre>` |
| Expiración de evidencia | `<fecha>` |

La evidencia integrada vigente es [e3-1-campaign-2026-10-13-final.json](../../../evals/results/e3-1-campaign-2026-10-13-final.json). La evidencia de Neon debe permanecer separada de cualquier evidencia Docker
local. El éxito de esta campaña no acredita H2–H4 ni sustituye la evidencia
de restore de M2.
