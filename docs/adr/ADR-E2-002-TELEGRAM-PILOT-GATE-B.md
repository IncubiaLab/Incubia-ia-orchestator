# ADR-E2-002 — Configuración y operación del piloto Telegram para Gate B

**Status:** Proposed  
**Scope:** Etapa 2 / H4  
**Decision owner:** responsable de operación del piloto

## Contexto

El piloto requiere un efecto externo y no puede habilitarse solo con código. Debe existir un bot de prueba, dos bindings privados autorizados y un procedimiento para recuperar efectos inciertos sin exponer secretos.

## Decisión pendiente

Autorizar y registrar, fuera del repositorio:

- una cuenta de bot de prueba y `TELEGRAM_BOT_TOKEN` en infraestructura;
- exactamente dos chats/remitentes privados vinculados a tenants y scopes distintos, con FakeLLM exclusivo;
- ausencia de webhook y de otro consumidor antes de iniciar long polling;
- responsables del comando `inspect` y de resolución manual de `UNKNOWN_EFFECT`.

## Criterio de resolución

Después de Gate A, el ADR se acepta con una ejecución controlada: tres turnos, cambio de especialista, dos chats aislados, rechazo de un remitente desconocido y replay/reinicio reproducidos con FakeLLM. La evidencia no incluye token, chat IDs ni transcripciones.

## Relacionado

- E2-10, E2-11 / Gate B
- `docs/roadmap/etapa-2/TELEGRAM.md`
