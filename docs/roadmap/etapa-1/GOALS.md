# Objetivos — primera etapa del MVP

## Objetivo principal

Validar que un chatbot en terminal puede resolver solicitudes mediante orquestación explícita entre un máximo de tres perfiles especialistas, manteniendo el runtime y el proveedor detrás de contratos propios.

## Objetivos verificables

1. **Experiencia:** completar una conversación de al menos tres turnos desde la CLI, con comandos claros para ayuda y salida.
2. **Orquestación:** seleccionar una especialidad por turno y mostrarla; probar ejemplos de cada especialidad y una solicitud ambigua.
3. **Control de alcance:** usar entre uno y tres perfiles activos; cero tools, cero bases de datos y cero dependencias de canales externos.
4. **Arquitectura:** respetar ADR-ORCH-001 y ADR-ORCH-007; mantener contratos serializables propios y tipos de LangGraph dentro del adapter.
5. **Confiabilidad:** devolver un error seguro ante timeout o fallo de proveedor; registrar `request_id` y latencia sin secretos ni contenido de conversación por defecto.
6. **Reproducibilidad:** ejecutar tests de contrato, routing, graph y CLI sin credenciales ni red.

## Medición de validación

- Preparar un conjunto pequeño de solicitudes etiquetadas por especialidad y registrar aciertos de routing. La meta inicial es ≥80 % en ese conjunto; revisar la taxonomía si falla.
- Medir latencia y costo por turno en una prueba manual con los modelos elegidos; establecer umbrales después de obtener una línea base.
- Registrar fallos por tipo: configuración, proveedor, routing y entrada inválida.

## Fuera de alcance

API HTTP, UI web, WhatsApp, RAG, búsqueda, ejecución de herramientas, persistencia de conversaciones, multi-tenancy, autenticación y agentes autónomos que delegan entre sí.

## Definición de terminado

Se cumplen los seis objetivos verificables, el conjunto de evaluación está versionado, las pruebas locales pasan y existe una guía de arranque con variables de entorno y ejemplo de sesión. Ningún ADR propuesto se presenta como aceptado por haber implementado una variante.

## Estado de cierre (2026-10-06)

Los seis objetivos verificables y la medición manual mínima se completaron para el prototipo local. La evidencia, costos estimados y límites de la muestra están en [VERIFICACION.md](VERIFICACION.md).
