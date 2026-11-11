# E3-5 — Campaña integrada (how-to del operador)

Runner único: `scripts/e3/run_e3_5_campaign.py` (helpers en `scripts/e3/e3_5_lib.py`). Cubre E3-13 de
`PLAN-E3.md`, las secciones Rollback y Restore de `RUNBOOK.md` y alimenta `VERIFICACION.md` (G7, G9, SLO).
Sólo opera sobre la rama Neon sintética `e3-h1-synthetic` y el scope sintético
`e3-5-synth-deployment` / `e3-5-synth-tenant`. **No cierra el gate**: `gate_closed` es siempre `false`.

## Requisitos

- `deploy/e3-neon.env` (o `.env`/entorno): `DATABASE_URL` (rol `incubia_runtime`, pooled),
  `INCUBIA_MIGRATION_DATABASE_URL` (rol `incubia_migrator`, directa), `INCUBIA_E3_DB_POOL_MAX`.
- Autorización explícita: `INCUBIA_E3_5_CAMPAIGN=1`, `INCUBIA_E3_NEON_TESTS=1`,
  `INCUBIA_E3_NEON_BRANCH=e3-h1-synthetic`, `INCUBIA_E3_5_BUDGET_APPROVED=1`,
  `INCUBIA_E3_5_BUDGET_USD=<monto aprobado>`. Sin ellas el runner se niega (exit 2) antes de tocar nada.
- Los guards reutilizan `run_neon_h1.py`: roles y tipo de endpoint correctos, TLS, y el host directo debe
  coincidir con el que resuelve `neon connection-string e3-h1-synthetic` (requiere `npx`/Neon CLI autenticado).
- Para carga con proveedor real: `OPENAI_API_KEY` y, si el endpoint exige auth, `INCUBIA_E3_PROBE_TOKEN`
  (nunca se imprime ni se guarda).
- Opcional: `psutil` (si no, se lee `/proc`); Docker y `INCUBIA_E3_5_IMAGE_N1_DIGEST` para el ensayo de imagen N-1.

## Ejecución

```bash
# 1. Plan sin tocar nada
python scripts/e3/run_e3_5_campaign.py --dry-run

# 2. Campaña completa (>= 3 x 10 min de carga). El runner levanta la app D0 en --url (loopback)
set -a; . deploy/e3-neon.env; set +a
INCUBIA_E3_5_CAMPAIGN=1 INCUBIA_E3_NEON_TESTS=1 INCUBIA_E3_NEON_BRANCH=e3-h1-synthetic \
INCUBIA_E3_5_BUDGET_APPROVED=1 INCUBIA_E3_5_BUDGET_USD=5 \
python scripts/e3/run_e3_5_campaign.py --image-n1-digest repo/imagen@sha256:<digest>

# Subconjunto o ensayo corto (nunca cuenta como evidencia G9)
python scripts/e3/run_e3_5_campaign.py --phases seed,restore
python scripts/e3/run_e3_5_campaign.py --phases load --allow-short --profile-seconds 60 --burst-waves 2 --burst-interval 10
```

Parámetros útiles: `--conversations 5000 --turns 50000 --chunks 2000`, `--sessions` (≤80),
`--session-interval`, `--constant-rate`, `--burst-waves/--burst-interval`, `--fault-seconds`,
`--provider-env NAME` (variables que apuntan al proxy de fallos; por defecto `OPENAI_BASE_URL`),
`--tolerate-429`, `--external-app --app-pid N` (app ya levantada: se omiten los fallos que requieren
proceso propio), `--provider-reported-usd` (si las métricas no traen base `reconciled`).

Cada ejecución usa un `run_id` único (`e3-5-<fecha>-<hex>`); la `--seed` de cada perfil de `load.py` deriva de él.

## Fases y evidencia

Salida en `evals/results/e3-5-<fecha>/` (ignorar/commitear según política del repo): `seed.json`, `load.json`,
`faults.json`, `restore.json`, `rollback.json`, `cost.json`, `summary.json`.

| Fase | Qué hace | Criterios |
| --- | --- | --- |
| seed | Inserta volumen sintético idempotente (`ON CONFLICT DO NOTHING`, ids determinísticos) con el migrador; chunks pgvector en una generación `RETIRED` si existen tablas Knowledge. | conteos >= objetivo; el 2.º run inserta 0 filas |
| load | `load.py` perfiles sessions / constant / burst (>= 600 s cada uno) sobre `/v1/executions`; p50/p95/p99, errores, 429, CPU/RSS del proceso, pool y costo de `/metrics`; integridad (revision == turnos, sin entregas duplicadas) y cobertura de `audit_events` por ejecución. | G7 100% audit; cero pérdida/duplicación; SLO p95 <= 5 s |
| faults | Proveedor caído (proxy local: timeout, 5xx, reset) bajo carga; saturación de pool; claim vencido con fencing (dos workers, generación y renew/release stale rechazados); revocación de credencial (REVOKE/GRANT reversible de `incubia_runtime` sobre `inbox_events`); SIGTERM bajo carga (drain, salida limpia, reinicio). | recuperación + integridad tras cada fallo |
| restore | Export scoped, delivery marcador posterior al backup, rama temporal `e3-5-restore-*` desde la sintética con expiración de 2 h, vaciado del scope sólo en la temporal, import, conteos vs manifest, migraciones, pgvector (extensión, índices válidos, vecino más cercano), cuarentena (sin SENDING, UNKNOWN_EFFECT, claims limpiados, marcador ausente); la rama se borra siempre. | RPO <= 12 h, RTO <= 1 h |
| rollback | Check expand/contract offline, `schema_migrations` vs `migrations/postgres`, imagen N-1 por digest (`repo@sha256:...`, nunca `latest`; se omite con motivo si falta digest o Docker). | estado `inconclusive` si la imagen se omitió |
| cost | Estimado vs reconciliado (base `reconciled` de `/metrics` o `--provider-reported-usd`), tolerancia 10 %, dentro del presupuesto aprobado. | desviación <= 10 % |

`summary.json` lista cada criterio como `passed`, `failed` o `inconclusive` (evidencia ausente/omitida nunca
cuenta como pass) y `all_criteria_passed`; el cierre del gate y el registro en `VERIFICACION.md` los decide el responsable.

## Seguridad y recuperación

- Todo paso destructivo se revalida: scope debe empezar por `e3-5-synth`; la rama temporal debe llamarse
  `e3-5-restore-*`, nacer de `e3-h1-synthetic` y su DSN no puede ser el de la rama primaria; los GRANT/REVOKE se
  limitan al rol runtime sobre `inbox_events`.
- Si el proceso muere con los grants revocados: `python scripts/e3/run_e3_5_campaign.py --recover-grants
  evals/results/e3-5-<fecha>/grants-to-restore.json` (mismos guards y variables de entorno).
- Si queda una rama temporal por un fallo del CLI: `npx neon@8.3.3 branches delete e3-5-restore-...` (expira sola a las 2 h).
- La fase restore falla cerrada (sin vaciar nada) si el DSN de la rama temporal no coincide con el host que reporta `branches create`.
- Limitaciones: el proxy de fallos cubre las URLs base configurables (OpenAI vía `OPENAI_BASE_URL`); el READ
  OpenFoodFacts no tiene variable de base URL y no se inyecta. `load.py` apunta a `/v1/executions` (app D0), no a `/v1/probe`.
- Exit code: 0 sólo si todos los criterios pasan; 1 si una fase falla/error; 3 si no falló nada pero hay evidencia `inconclusive`; 2 guard/argumentos.
- Verificación offline de este runner: `PYTHONPATH=src python -m pytest -q tests/unit/test_e3_5_campaign.py`.
