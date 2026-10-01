# Spec 06 — Verificación y atributos de calidad

## Pruebas

- `tests/unit/`: contratos puros, mapping y `HandleMessage` con runtime/LLM falsos; sin red ni proveedores reales.
- `tests/integration/`: graph LangGraph y adapter OpenAI separados; dependencias externas reales solo en pruebas explícitas y configuradas.
- `tests/contract/`: mismas expectativas funcionales para cada implementación de `WorkflowRuntimePort` y `LLMPort`.
- `tests/architecture/`: imports y dirección de dependencias; Domain/Application no importan LangGraph, LangChain, OpenAI, FastAPI, Qdrant, Redis ni SDKs externos.

## Requisitos de calidad del MVP

- Latencia objetivo extremo a extremo: ≤5 s en condiciones normales; referencia de diseño de ~80 usuarios concurrentes. Se miden en una prueba de carga definida, no se asumen garantizados por la estructura.
- Aislamiento lógico para más de cinco organizaciones; ninguna consulta mezcla contexto, datos o credenciales de tenants.
- Correlation ID por request/conversación, logs estructurados y medición de latencia, errores y disponibilidad de conectores.
- Timeouts y retries explícitos al integrar proveedores; los fallos se degradan de manera controlada.
- Secretos fuera del repositorio y mínimo privilegio para conectores.
- Persistencia mínima de datos sensibles, retención configurable por cliente y trazabilidad de fuentes cuando aplique.

## Criterios de aceptación del primer slice

- Prueba end-to-end local: HTTP → `HandleMessage` → `WorkflowRuntimePort` → LangGraph → `LLMPort` fake → respuesta.
- Pruebas de contrato cubren completed, suspended y failed, incluso si el primer graph solo produce completed/failed.
- Prueba arquitectónica falla ante un import de LangGraph/OpenAI desde Domain/Application.
- Se registra latencia y correlación sin exponer secretos o contenido sensible en logs por defecto.

Los requisitos de aislamiento, fallback humano y carga completa del MVP se verifican al implementar esos componentes; no se declaran satisfechos por el primer slice.

## Fuentes

[ADR-ORCH-020](https://linear.app/hector-cruz/document/adr-orch-020-estrategia-de-tests-arquitectonicos-y-de-contratos-589739f90eac) (propuesto), [NFRs](https://linear.app/hector-cruz/document/incubia-mvp-nfrs-f626bdd0b279), [proyecto MVP](https://linear.app/hector-cruz/project/incubia-platform-mvp-67f3883cb76e).
