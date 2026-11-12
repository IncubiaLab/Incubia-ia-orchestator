# Revisión de dependencias y preparación del despliegue VPS

Fecha: 2026-11-09 (America/Bogota). Base: `feat/knowledge-base`, HEAD `38770ed`, incluyendo cambios locales pendientes. Revisión de código y configuración; no se provisionó infraestructura ni se accedió a servicios reales.

## Plan de ejecución asociado

El [plan de despliegue en el VPS de pruebas](PLAN-DESPLIEGUE-VPS.md) contrasta este diagnóstico con `main` (`5a7df31`) al 2026-11-11 y organiza fases P0–P7, entregables, dependencias y aceptación. Este informe conserva su fecha y evidencia originales; las correcciones de estado posteriores se registran en ese plan.

## Dictamen y alcance corregido

El objetivo es desplegar **el orchestrator completo en el VPS**, con su runtime, lógica de orquestación, políticas, adaptadores y configuración operativa. La API es su interfaz de acceso para los demás aplicativos. El PC de desarrollo no participa en la ejecución productiva ni se necesita un puente hacia él.

La respuesta del responsable sobre API define el método de acceso; no autoriza reducir el orchestrator a un gateway, rediseñar sus módulos ni decidir una nueva distribución de procesos. La revisión anterior confundió estos planos e introdujo decisiones de producto no acordadas; se retiran de este plan.

ADR-ORCH-024 ya contempla una instancia contenedor con Neon externo. La planificación debe partir de esa arquitectura y comprobar cómo ejecutar sus capacidades reales en el VPS. El repositorio aún tiene bloqueos de empaquetado, composición y operación; cambiar el alojamiento no los resuelve.

## Ubicación de los componentes

| Ubicación | Responsabilidad |
| --- | --- |
| VPS | Ejecutar el orchestrator: interfaz API, casos de uso, runtime LangGraph, políticas, adaptadores de herramientas/retrieval y procesos auxiliares que requiera su operación. Configuración, secretos y estado de archivos necesarios deben estar disponibles allí. |
| Servicios externos existentes | Neon para la persistencia prevista en los ADR; proveedores LLM y fuentes/herramientas externas invocados por el orchestrator desde el VPS. Usar estos servicios no implica ejecutar el orchestrator fuera del VPS. |
| Aplicativos consumidores | Invocar la interfaz del orchestrator desplegado con el contrato y permisos que se definan. |
| PC de desarrollo | Desarrollo y pruebas. Apagarlo no debe afectar al servicio desplegado. |

La interfaz HTTP es una parte del orchestrator. La cantidad de contenedores o procesos, ejecución síncrona/asíncrona, endpoints, credenciales por aplicativo, cuotas y adaptación de Orbit/Telegram necesitan revisión de los contratos existentes; no quedaron decididos al elegir API como acceso. No se establece aquí una migración obligatoria de esos canales.

El siguiente trabajo de planificación es completar el mapa de arranque y dependencias del orchestrator en el VPS: qué módulos están conectados hoy, qué composición falta, qué procesos deben mantenerse activos, qué estado persiste y qué servicios externos utiliza cada capacidad. La interfaz API se revisa dentro de ese conjunto.

## Qué se puede desplegar hoy

| Entrada | Dependencias efectivas | Limitaciones verificadas |
| --- | --- | --- |
| HTTP D0 (`interfaces/http/main.py`, 8080) | LangGraph, PostgreSQL, psycopg y pool | Solo modo `local`, identidad sintética configurada, `FakeLLM`, herramientas/retrieval deterministas, sin autenticación. No es API productiva. |
| Gateway Orbit (`interfaces/http/orbit_gateway.py`, 8081) | Runtime Python, OpenAI, BFF Orbit, archivo de presupuesto escribible | Bearer compartido ≥32 caracteres; confía en identidad/evidencia autorizadas por el BFF. No conecta al ledger PostgreSQL ni al RAG de IncubiaLab. No persiste turnos ni deduplica solicitudes; genera con historial vacío. Archivo aún no versionado. |
| Telegram (`incubia-bot run`) | OpenAI, Telegram, SQLite, archivo de presupuesto | Long polling y dueño único del bot; necesita volumen persistente y bindings o política explícita de altas. El CLI instancia `SqliteLedger`, no PostgreSQL. |
| Probe E3 (`interfaces/http/e3_probe.py`) | Neon Knowledge sintético, embeddings OpenAI, Open Food Facts, auditoría | Exige rama `e3-h1-synthetic`; es instrumento de campaña, no el servicio productivo general. |
| Ingesta Drive/Knowledge | `knowledge-drive`, service account, OpenAI embeddings, Neon/pgvector | Trabajo separado del servidor. No está conectado automáticamente al gateway Orbit; el esquema usa `vector(384)`. Validar corpus y permisos antes de ingesta. |

## Dependencias y reproducibilidad

| Componente | Declaración actual | Acción para despliegue |
| --- | --- | --- |
| Python | `>=3.12`; Docker fija `3.12.10-slim-bookworm` por digest | Validar con Python 3.12 e imagen final. Revisar parches y vulnerabilidades del digest antes de congelar release. |
| Núcleo | `langgraph==1.2.12`, `httpx==0.28.1`, `PyYAML==6.0.3` | Mantener resolución única y pruebas del artefacto instalado. OpenAI se invoca por HTTP; no requiere SDK OpenAI. |
| PostgreSQL | Extra `deployment`: `psycopg[binary]==3.2.10`, `psycopg_pool==3.2.6` | **Bloqueo:** `requirements.lock` no contiene `psycopg_pool`. Docker instala ese lock y luego el paquete con `--no-deps`; `PooledConnections` importa el módulo al iniciar HTTP D0. |
| Ingesta Drive | Extra `knowledge-drive`: `google-auth==2.40.3` | No incluido en la instalación actual de Docker; añadir únicamente al artefacto de ingesta si se habilita. |
| Embeddings locales | Extra `knowledge-local`: `fastembed==0.9.0` | Opcional; exige presupuestar modelos, caché, descargas, RAM y compatibilidad de wheels. No necesario con embeddings remotos. |
| Node | `@neon/config`, `@neon/env`, `package-lock.json` | Tooling de configuración Neon; no requisito del servicio Python actual. |
| Tests | `pytest==8.4.2` | Está también en `requirements.lock` de la imagen. Separar dependencias de pruebas y runtime al unificar empaquetado. |

CI usa `uv.lock` con extras `test` y `deployment`; Docker usa otro lock. `uv lock --check --offline` pasó, pero esto no verifica que el contenedor arranque. Añadir build de imagen, comprobación de imports, arranque y healthcheck en CI. No se realizó auditoría CVE ni build Docker en esta revisión.

## Bloqueos y diferencias operativas

1. **Secretos:** `.env.example`, versionado, contiene un valor con formato de token real de Telegram. No se verificó su validez. Tratar como potencialmente expuesto: revocar/rotar si corresponde, reemplazar por placeholder y revisar historial/CI sin reproducir el valor. No distribuir `.env` de desarrollo al VPS.
2. **Compose local:** arranca PostgreSQL local y D0, tiene `restart: "no"`, no incluye proxy/TLS y desactiva masquerading de red. Crear configuración VPS independiente con salida requerida; no reutilizar esa topología como producción sin cambios.
3. **Límites de prueba en generación real:** `compose_scoped` instala `MonthlyCallLimiter` con 20 llamadas por mes y separación mínima de 10 segundos, compartidos por archivo. Se aplica también a Orbit/Telegram. Definir cuotas operativas y manejo de rechazos antes de un piloto multiusuario; no confundirlas con límites E3 del YAML.
4. **Tokens Orbit:** acepta configurar hasta 512 tokens, pero `compose_scoped` rechaza más de 128 en modo real. Alinear contrato/configuración y probarlo.
5. **HTTP:** D0 y Orbit usan `http.server`. Python desaconseja su uso productivo por sus controles básicos. Planificar adaptación a servidor de producción y pruebas del contrato; al menos mantener el servicio privado tras proxy con TLS, autenticación, límites de cuerpo, conexiones y tiempo. Un proxy no sustituye esa revisión.
6. **Readiness y concurrencia Orbit:** `/readyz` devuelve éxito sin comprobar dependencias ni drenaje. El semáforo limita a 8 generaciones, no todas las conexiones HTTP; faltan cuotas por tenant y pruebas específicas del gateway (no se encontraron referencias a Orbit en `tests`). SSE se envía tras completar la respuesta, sin streaming incremental ni cancelación del proveedor.
7. **Apagado:** `DrainingHTTPServer` espera 10 segundos, frente a timeout LLM de 30 segundos por defecto (Orbit permite hasta 60). Ajustar tanto el drenaje de aplicación como el período de parada del contenedor; aumentar solo el segundo no evita abandono de solicitudes.
8. **Persistencia local:** montar `/data` escribible para presupuesto y, si corresponde, SQLite Telegram. El filesystem de solo lectura necesita esa excepción; verificar permisos UID/GID 10001. Respaldar SQLite de forma consistente y recuperar presupuesto tras reinstalar; no usar `/tmp` para estado operativo durable.
9. **Migraciones:** el entrypoint Docker `interfaces/http/migrate.py` aplica únicamente `001` y `006` del baseline D0. No provisiona la cadena completa de identidad/RLS/audit ni Knowledge. Definir job de migración productivo, roles, orden y comprobación de versión, sin otorgar DDL al runtime.
10. **Entrega:** hay cambios locales en README, pyproject, CI y Neon, y archivos nuevos Orbit/Fly. Fijar commit revisado y artefacto por digest antes de release; no desplegar un árbol de trabajo mutable.

## Requisitos propuestos del VPS

El VPS de pruebas de la empresa quedó identificado el 2026-11-11 como `2.24.201.39` (usuario SSH `hector`, hostname observado `srv2113451`, Ubuntu 24.04 `x86_64`). El acceso SSH por clave se verificó; aún no se ha desplegado ni probado allí el orchestrator. La ficha de acceso, huellas observadas y convención de alias están en `vault-orchestrator/03-Implementacion/VPS de pruebas - acceso SSH.md`.

Dimensionamiento inicial estimado para piloto de baja concurrencia, con LLM remoto y base externa: **2 vCPU, 4 GB RAM y 40 GB SSD**. No es capacidad acreditada ni cotización; medir CPU/RSS/disco y p95 antes de contratar capacidad definitiva. Embeddings locales, ingesta intensiva o PostgreSQL autogestionado requieren otro dimensionamiento.

- Linux mantenido, Docker Engine y Compose plugin; preferir inicialmente x86_64 para reducir variables de compatibilidad. Compilar en CI y descargar imagen en el VPS.
- Elegir región tras confirmar ubicación real de Neon y del BFF; medir RTT. No asumir que los endpoints de ejemplo reflejan la región real.
- Dominio y DNS si existe ingreso público; proxy HTTPS con renovación automática. Publicar solo el proxy, mantener 8080/8081 y la base fuera de acceso público. SSH restringido por clave y origen o VPN.
- Salida DNS, HTTPS hacia OpenAI y servicios habilitados; conexión TLS PostgreSQL hacia Neon por 5432 cuando aplique. Telegram, Google y Open Food Facts solo según el canal/trabajo habilitado.
- Reinicio automático, arranque tras reboot, límites de CPU/RAM/PIDs, rotación de logs, healthchecks y alertas externas. Mantener usuario no-root, `cap_drop: ALL`, `no-new-privileges` y raíz de solo lectura donde sea compatible.
- Imagen por digest, registro de contenedores, secrets por entorno y credenciales separadas de despliegue, runtime y migración. Variables de campañas reales desactivadas en operación normal.
- Volumen de datos local con backups externos cuando se use; presupuesto para imágenes N y N-1, logs retenidos y restauración.

## Configuración actual por componente (a consolidar para el VPS)

| Alcance | Variables/recursos |
| --- | --- |
| Generación real | `OPENAI_API_KEY`, `INCUBIA_MODEL`, `INCUBIA_BUDGET_FILE=/data/api-budget.json`; presupuesto operativo definido y persistente |
| Orbit | `INCUBIA_ORBIT_GATEWAY_TOKEN`, `INCUBIA_ORBIT_GATEWAY_DEPLOYMENT_ID`, host/port; `INCUBIA_ORBIT_GATEWAY_FAKE=0`; BFF con secreto equivalente, autorización y control de reintentos |
| Telegram | `TELEGRAM_BOT_TOKEN`, `INCUBIA_TELEGRAM_DB=/data/telegram.sqlite3`, bindings y deployment/tenant; un solo runner; no habilitar webhook simultáneo |
| Ledger PostgreSQL productivo | `DATABASE_URL` runtime pooled con TLS y rol limitado; DSN directa separada para migraciones/restore; esquema completo y RLS verificados |
| Knowledge IncubiaLab | `INCUBIA_KNOWLEDGE_DEPLOYMENT_ID`, runtime DSN de lectura, DSN de ingesta y migración separadas; base por deployment; integrar el retrieval al entrypoint elegido |
| Ingesta Drive | JSON de service account fuera del repo, montado solo en job de ingesta; `INCUBIA_DRIVE_SERVICE_ACCOUNT_FILE`, `INCUBIA_DRIVE_ROOT_FOLDER_ID`; permisos y presupuesto de embeddings |

Esta tabla describe las entradas existentes; no es la configuración definitiva del despliegue. Hay que consolidar las variables y dependencias de los procesos que ejecutará el VPS. En el gateway Orbit actual no está conectado el ledger/RAG; Telegram usa SQLite. Son hechos del código, no decisiones de limitar el orchestrator a esos entrypoints. Revisar `TODOS.md` como pendientes históricos, no como comprobación actual de credenciales o infraestructura.

## Secuencia de planificación y aceptación

1. **Mapear el runtime completo:** módulos, composition roots, procesos, capacidades conectadas y pendientes, archivos y servicios externos. Contrastar con la arquitectura y contratos del repositorio.
2. **Definir la ejecución en VPS:** comandos de arranque, imagen y dependencias, procesos persistentes y trabajos puntuales, volúmenes, red y secretos. Revisar la interfaz API como acceso al orchestrator, sin convertir su elección en un rediseño del sistema.
3. **Resolver bloqueos verificados:** lock incompleto, configuración de prueba, composición productiva, migraciones, permisos y apagado. Separar correcciones necesarias de propuestas que requieran decidir alcance.
4. **Preparar staging:** ejecutar el orchestrator en el VPS con los servicios externos previstos; verificar acceso API, autenticación, salud, reinicio y persistencia.
5. **Validar operación completa:** recorrido de una solicitud por la orquestación real, recuperación, aislamiento, carga, backup y rollback. Comprobar que el servicio funciona con el PC de desarrollo apagado. Las campañas con gasto requieren alcance/presupuesto acordados.
6. **Habilitar tráfico:** evidencia de los objetivos ratificados en el repo (p95 ≤5 s, RPO ≤12 h, RTO ≤1 h), alertas, runbook y aceptación operativa. El contrato de acceso y los detalles de despliegue pendientes deben quedar explícitos antes de esta etapa.

La decisión de topología está aceptada, pero `VERIFICACION.md` mantiene E3-0/E3-5/E3-6 abiertos. Una revisión de dependencias o una suite offline no cierra esos gates.

## Validación de esta revisión

- `uv lock --check --offline`: correcto.
- Suite offline con campañas Neon deshabilitadas: **505 passed, 10 skipped**, 33,60 s. Ejecutada con `.venv/bin/python` **3.14.4**, no con Python 3.12 del contenedor; no acredita compatibilidad de la imagen.
- `git diff --check`: correcto para cambios versionados existentes. Solo se añadió este informe; se conservaron los cambios previos del usuario.
- No se ejecutaron build/arranque Docker, campañas externas, escaneo de vulnerabilidades ni cambios en VPS/Neon. El fallo de empaquetado del pool se identifica por inspección de Dockerfile, lock e import, no por un arranque fallido observado.

## Referencias

- Repositorio: `pyproject.toml`, `requirements.lock`, `uv.lock`, `Dockerfile`, `compose.yaml`, `config/e3/limits.example.yaml`, `bootstrap/composition.py`, `interfaces/http/*`, `interfaces/cli/bot.py`.
- ADR-ORCH-024 (topología), ADR-ORCH-025 (Neon), `VERIFICACION.md`, `TODOS.md`.
- [Docker Compose en producción](https://docs.docker.com/compose/how-tos/production/): configuración específica y reinicio del servicio.
- [Neon connection pooling](https://neon.com/docs/connect/connection-pooling): pooling transaccional y restricciones; mantener conexiones directas para tareas que lo requieren.
- [Python http.server](https://docs.python.org/3.12/library/http.server.html): limitaciones para uso productivo.
