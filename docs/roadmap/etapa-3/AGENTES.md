# Agentes — etapa 3

Se mantienen General, Ventas y Marketing de [etapa 2](../etapa-2/AGENTES.md). Este corte amplía evidencia y capacidades, conservando los perfiles versionados y la selección por capability.

| Perfil | Capacidad nueva | Evidencia admitida | Límite |
| --- | --- | --- | --- |
| General | Respuesta sustentada y fallback | Documentos autorizados, resultados READ y contexto canónico | Abstenerse ante información insuficiente/conflictiva; proponer caso interno. |
| Ventas | Consulta comercial y propuesta de lead | Catálogo/datos sintéticos autorizados y consentimiento explícito del actor | No inventar precios ni disponibilidad; no enviar al CRM ni prometer acciones. |
| Marketing | Plan basado en brief/knowledge | Brief scoped, documentos y hechos públicos autorizados | Sin campañas, envíos ni mutations externas. |

## Contexto y respuesta

Orden: restricciones del perfil → mensaje actual → hechos autorizados → evidencia recuperada pertinente → pares recientes completos. Preservar presupuesto E2; añadir límites por tool output, retrieval y total de tokens. Si lo obligatorio no cabe, error tipado o pedir reducción; truncar solo evidencia opcional por una regla registrada.

Separar instrucciones de contenido de tool/documento; textos como “ignora la política” nunca cambian permisos. Referencias de fuente públicas permitidas se renderizan por ResponseContextPort; no publicar URLs firmadas, IDs privados, credenciales o el contexto completo. Evidence expirada/conflictiva produce abstención o explicación de incertidumbre.

## Matriz de evaluación

Los ≥24 escenarios de G6 cubren: READ válido, retrieval válido, combinación de ambos, fuente ausente, dato desactualizado, conflicto, cambio de perfil, prompt injection, tenant ajeno, DENY, timeout, overflow, consentimiento y fallback. Incluir al menos cuatro escenarios por perfil y variantes negativas. Val se congela antes de ajustar prompts; dev es la única partición de ajuste.

Rúbrica manual: fidelidad de hechos, validez de referencias, utilidad y protección de scope. G6 gobierna porcentajes; fuga, secreto o acción no autorizada es fallo crítico y bloquea el gate con cualquier score promedio.
