# Plan de implementación — etapa 4

Estado: backlog propuesto. Los IDs E4 son locales; no representan issues de Linear ya creados.

| ID | Entregable | Dependencia | Verificación |
| --- | --- | --- | --- |
| E4-01 | Inventariar entradas y divergencias (`HandleMessage`, `HandleInbound`, Telegram y HTTP); levantar tipos de empresa, casos de uso y sistemas antes de fijar dataset de decisiones/handoffs. | E2/E3 actuales y requisitos de producto | Casos positivos, ambiguos y negativos por perfil; baseline reproducible sin proveedor impuesto. |
| E4-02 | Versionar perfiles y salidas estructuradas para respuesta, aclaración, abstención y solicitud de handoff. | 01 | Un perfil cambia sin editar router ni grafo; validación de configuración y contexto. |
| E4-03 | Definir `HandoffRequest`, `HandoffContext`, `AgentRun` y resultado de transición en Domain/Application; esquema versionado. | 02, ADR-011 | Serialización, validación de scope e inmutabilidad; sin tipos LangGraph. |
| E4-04 | Implementar `HandoffCoordinator` con Discovery/Selection/Policy, presupuesto de hops y deadline. | 03 | Una transición entre perfiles actuales con fakes; DENY, candidato disabled/ajeno, loop y expiry no activan destino. |
| E4-05 | Persistir transición de owner en Conversation/UoW y agregar audit. | 04, evidencia E3-1/E3-2 | Competencia, crash, replay, fencing y revocación producen un solo owner; eventos correlacionados. |
| E4-06 | Integrar ruta de entrada y evaluar transiciones adicionales según casos de uso aprobados, sin compartir contexto completo. | 05 | Fallback seguro, scope preservado y salida trazable; cualquier integración externa requiere requisitos y gate propios. |
| E4-07 | Campaña de calidad y operación; decisión de gate E4. | 06 y gates E3 aplicables | Rúbrica, latencia, costo, aislamiento, recuperación y decisión documentada. |

Primera iteración: E4-01 levanta los requisitos de producto; E4-02 a E4-04 usan escenarios aprobados y adapters fake. E4-05 es la frontera de durabilidad; el handoff requiere demostrarla antes de llegar a tráfico real. Reutilizar contratos existentes de E2/E3, evitando un segundo router o un acceso directo de agentes a conectores.

## Milestone 03 de Linear: definición pendiente

1. **HEC-8:** identificar tipos de empresas usuarias, sistemas que usan, datos que necesitan consultar, permisos disponibles y restricciones de integración. Sólo entonces elegir el sistema piloto.
2. **HEC-9:** contrastar el contrato técnico actual con los requisitos del sistema piloto elegido; documentar brechas y adaptar el conector.
3. Definir campaña, presupuesto y criterios de aceptación para esa integración concreta antes de declarar el milestone completo.

Las fechas originales del milestone están vencidas y no se convierten aquí en un compromiso nuevo.
