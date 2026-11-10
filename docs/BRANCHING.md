# Flujo de ramas

El repositorio usa un flujo de promoción único:

```text
feat/* → dev → qa → main
```

`main`, `qa` y `dev` son ramas permanentes. El nombre canónico es en minúsculas,
incluso cuando se hable de los ambientes QA o Dev.

| Rama | Propósito | Recibe cambios desde | Despliegue esperado |
| --- | --- | --- | --- |
| `main` | versión de producción | `qa`, `hotfix/*` | producción |
| `qa` | candidato validado y UAT | `dev`, `main` (propagación de hotfix) | staging/QA |
| `dev` | integración continua | `feat/*`, `fix/*`, `chore/*`, `docs/*`, `qa` (propagación) | desarrollo |
| `feat/*` | una capacidad acotada | se crea desde `dev` | ninguno |

## Nombres

Usar nombres en minúscula y con guiones. Incluir el identificador de trabajo
cuando exista:

```text
feat/123-drive-ingestion
fix/456-retry-timeout
chore/actualizar-lockfile
docs/guia-operacion
hotfix/789-revocar-token
```

No se crean ramas de trabajo directamente desde `main` ni `qa`; una excepción es
`hotfix/*`, que nace de `main` para una corrección productiva urgente.

## Promoción y merge

1. Una rama de trabajo abre PR únicamente hacia `dev`.
2. `dev` se promueve por PR a `qa` cuando CI está verde y el cambio está listo
   para validación integrada.
3. `qa` se promueve por PR a `main` tras UAT, revisión de riesgo y plan de
   rollback.
4. Todo hotfix fusionado en `main` se propaga por PR `main → qa` y después
   `qa → dev` antes de comenzar otro release.

Los PR de trabajo usan *squash merge*. Las promociones entre ramas permanentes
conservan el commit de promoción (merge commit) para que el historial muestre el
paso de ambiente. No se permiten commits directos, force-pushes ni borrado de
ramas permanentes.

## Controles requeridos en GitHub

Configurar rulesets (o branch protection) para `main`, `qa` y `dev`:

- pull request obligatorio, conversaciones resueltas y rama actualizada;
- CI `offline` y `branch-policy` requeridos;
- una aprobación para `dev` y `qa`; dos para `main` cuando haya capacidad de
  revisión independiente;
- bloquear force-push, borrado y bypass salvo administradores de emergencia;
- restringir cambios en `.github/`, `deploy/`, `migrations/` y secretos a los
  responsables definidos por el equipo mediante `CODEOWNERS`.

La asignación concreta de `CODEOWNERS` no se versiona hasta contar con los
usuarios o equipos reales de GitHub: nombres inventados bloquearían PRs válidos.

## Ramas existentes

Las ramas históricas `dev/1-tier`, `dev/2-tier`, `dev/3-tier` y
`dev/3-tier-2nd-int` no son parte del flujo nuevo. Se mantienen sin moverlas
hasta que una auditoría confirme que su contenido quedó integrado mediante PR.
No se eliminan ni se reescribe su historia como parte de esta política.
