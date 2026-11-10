# TODOS — feat/knowledge-base (RAG IncubiaLab)

Estado al 2026-10-24. Rama local `feat/knowledge-base`, **sin push**.

## 0. Seguridad (bloqueante antes de cualquier push)

- [x] **Quitar la `OPENAI_API_KEY` real del historial** (hecho 2026-10-24): los commits reescritos son `131de5a` y `38770ed`; se purgaron `refs/original`, el reflog y los objetos (`gc --prune=now`). Verificado: `git log --all -S` no encuentra la clave.
- [x] **Rotar la `OPENAI_API_KEY`** (2026-10-24, verificada con HTTP 200).
- [x] **Rotar las contraseñas de los roles `incubia_kb_*`** (2026-10-24). Runtime e ingestor verificados.
- [ ] Actualizar `INCUBIA_KNOWLEDGE_MIGRATION_DATABASE_URL` en `deploy/knowledge-neon.env`: sigue con la contraseña anterior (`password authentication failed`). Usar la conexión directa.
- [ ] Agregar un hook o un chequeo en CI que rechace secretos (`sk-`, `npg_`, DSN con password) en archivos versionados, en especial `.env.example`.

## 1. Configuración local

- [ ] Agregar `INCUBIA_KNOWLEDGE_DEPLOYMENT_ID` a `.env`. Confirmar el ID real; el valor propuesto es `incubialab`.
- [ ] Corregir `INCUBIA_KNOWLEDGE_NEON_BRANCH_ID` (`br-…`) y `INCUBIA_KNOWLEDGE_NEON_PROJECT_ID` donde corresponda. El branch ID tenía el project ID.
- [ ] La DSN del migrador debe ser **directa** (sin `-pooler`). La que se pegó en `.env.example` era pooled.
- [ ] Commitear `TODOS.md` y, si aplica, los cambios pendientes de `.env.example`.

## 2. Corpus Drive (bloqueado por credenciales)

- [ ] Decidir si se mantiene la estrategia actual (service account + `drive.readonly`) o se reemplaza.
- [ ] Crear la service account, habilitar Drive API y compartir la carpeta `1IiwcAQpeY-OeK9EwkS9oJnfMxw653kun` como **Lector**.
- [ ] Guardar la clave JSON fuera del repo con `chmod 600` y definir `INCUBIA_DRIVE_SERVICE_ACCOUNT_FILE` e `INCUBIA_DRIVE_ROOT_FOLDER_ID` en `.env`.
- [ ] Prueba en seco: `.venv/bin/python scripts/e3/ingest_drive_knowledge.py` (inventario, export y conteo de chunks; sin OpenAI ni Neon).
- [ ] Revisión de ACL a nivel carpeta. ¿Todos los lectores del deployment pueden leer toda la carpeta? Si no, no ingerir hasta tener ACL por documento.
- [ ] Ingesta real: `--apply --acl-reviewed`; después probar consultas con `--query "…"`.
- [ ] Sheets, Slides, PDF y archivos `.md`/`.txt` subidos a Drive **se omiten** hoy (solo Google Docs → Markdown). Decidir el conversor (xlsx/pptx/pdf) o aceptar la omisión.
- [ ] ACL por documento: `DriveSourceCatalog` produce siempre `AclState.UNKNOWN` y el filtro de permisos en SQL antes del top-k (dessing §11) no existe.

## 3. RAG-V1: criterios pendientes (GOALS «1 / RAG-V1»)

- [ ] Preflight sanitizado con acceso real a Drive. `run_rag_v1_preflight.py` siempre devuelve `drive_identity: UNRESOLVED`; conectarlo a `ServiceAccountDriveIdentity`.
- [ ] El preflight y `neon_branch_guard.guard_campaign_environment` leen `INCUBIA_E3_NEON_BRANCH` (que en `.env` es `e3-h1-synthetic`). Hacer que el flujo Knowledge use `INCUBIA_KNOWLEDGE_NEON_BRANCH`.
- [ ] Muestra congelada de 10–20 documentos con procedencia, hashes, revisión de extracción y de permisos (`prepare_knowledge_markdown.py` + manifest).
- [ ] Demo de fidelidad y rechazo de fuente no autorizada.

## 4. RAG-V2: RAG consultable (GOALS «2 / RAG-V2»)

- [ ] Multichunk real: hoy cada chunk se publica como su propia fila de `knowledge_sources` (`drive:<id>:<n>`) porque el esquema es de un chunk por fuente. Revocar un documento implica revocar todas sus filas. Evaluar una migración `003` con chunks por fuente/versión.
- [ ] Reingestión idempotente verificada y limpieza de sources de generaciones retiradas.
- [ ] Sets dev/val congelados (≥20 dev, ≥40 val: 20 respondibles, 10 sin respuesta, 10 prohibidas). Recall@5 ≥85 %, abstención ≥90 %, cero fugas, p95 retrieval ≤1 s.
- [ ] Ajustar el umbral de abstención con dev; evaluar HNSW (`002_hnsw_opt_in.sql`) contra la búsqueda exacta.
- [ ] Rúbrica manual de ≥24 respuestas (soporte, citas).

## 5. Integración

- [ ] Conectar `compose_incubialab_retrieval` + `openai_embedding_from_env` a un entrypoint real (`GroundedWorkflow`, CLI o Telegram).
- [ ] Decidir qué hacer con `scripts/e3/provision_knowledge_runtime.py` (dev/3-tier): exige `neondb_owner` y falla si el rol existe. En esta rama los roles ya existen y los grants por defecto funcionaron.
- [ ] `INCUBIA_E3_PROBE_KNOWLEDGE_DSN` (probe sintético) y el Knowledge de IncubiaLab son entornos distintos; no mezclarlos.

## 6. Limpieza menor

- [ ] `docs/roadmap/etapa-3/PROGRESS.md`: el párrafo del 2026-10-23 heredado de dev/3-tier tiene `**` duplicados.
- [x] `stash@{0}` antiguo (sobre `3265249`): **se perdió** como efecto secundario de `git reflog expire --all` durante la purga de la clave. No es recuperable.
- [ ] Rama Neon `feat-knowledge-base` sin expiración: eliminarla al cerrar el feature.

## Hecho en esta sesión (referencia)

- Merge de `origin/dev/3-tier` (`7aee82d`).
- Resolver de DSN runtime e ingest con validación estricta (`b59bef8`, `131de5a`).
- Runner de migraciones Knowledge (`32bb060`), aplicado en Neon: 3 tablas creadas y grants verificados.
- Composición del retrieval y smoke end-to-end en Neon: 6/6 checks con limpieza (`131de5a`).
- Transport Drive con service account, ingesta, embedding OpenAI con presupuesto USD 1 / 500 calls y script `ingest_drive_knowledge.py` (`38770ed`). **No se ha ejecutado contra Drive ni OpenAI.**
