# Verificación de la etapa 1

Fecha: 2026-10-06. Estado: **etapa 1 cerrada para el prototipo local definido en ROADMAP y GOALS**. Modelo compartido: `gpt-4o-mini` para General, Ventas y Marketing.

## Evidencia local

- Instalación en Python 3.12 desde `requirements.lock` y `pip install --no-deps -e .`; comando `incubia` instalado.
- Suite sin credenciales ni red: **28 pruebas pasaron**. Cubre contratos, policy, runtime, proveedor simulado, routing, CLI, fronteras de imports y bloqueo de red en proceso y subproceso.
- REPL fake de tres turnos, `/help`, `/exit`, IDs y especialidades visibles. El historial está acotado a pares completos y se descarta al reiniciar.
- Routing determinista: **15/15** en `evals/routing-v1.jsonl` (5 Ventas, 5 Marketing, 5 General, incluidos 2 ambiguos). Es un conjunto inicial escrito junto con las reglas; no mide generalización.
- Los tres perfiles comparten el modelo configurado y tienen instrucciones propias. Un turno invoca como máximo una generación.

## Medición real mínima

El 2026-10-06 se ejecutó una llamada terminada por perfil con el modelo de `.env`, `gpt-4o-mini`. Las tres respuestas empezaron identificando al especialista correcto y trataron la solicitud de forma pertinente. La observación de calidad es solo una revisión manual de un ejemplo por perfil.

| Perfil | Solicitud de prueba | Latencia | Entrada | Salida | Costo estimado USD |
| --- | --- | ---: | ---: | ---: | ---: |
| General | `hola` | 1860 ms | 45 tokens | 15 tokens | 0,00001575 |
| Ventas | `quiero vender` | 2819 ms | 51 tokens | 53 tokens | 0,00003945 |
| Marketing | `necesito una campaña de marketing` | 1360 ms | 66 tokens | 30 tokens | 0,00002790 |
| **Total de respuestas completas** | 3 turnos | 6039 ms | 162 tokens | 98 tokens | **0,00008310** |

La estimación usa la tarifa de texto estándar consultada el 2026-10-06 en la [ficha oficial de GPT-4o mini](https://developers.openai.com/api/docs/models/gpt-4o-mini): USD 0,15 por millón de tokens de entrada y USD 0,60 por millón de salida. Fórmula por turno: `entrada × 0,15 / 1 000 000 + salida × 0,60 / 1 000 000`. Se trata de una estimación conservadora sin separar posible caché ni cargos de otros intentos; el gasto facturado definitivo se consulta en la plataforma de API.

## Fallos y límites observados

- Antes de añadir saldo, dos solicitudes diagnósticas devolvieron HTTP 429 con `insufficient_quota` / `credit_balance_exhausted`; una fue con `gpt-4o-mini` y otra con `gpt-5.4-mini`. Ninguna generó salida. La [guía oficial de errores](https://developers.openai.com/api/docs/guides/error-codes) distingue ese caso de un límite temporal de peticiones.
- Con saldo, **dos intentos** de generación (Ventas con 64 tokens de salida y Marketing con 128) devolvieron `PROVIDER_INCOMPLETE`. El adapter no conservó `usage` en esos outcomes: su costo es **no disponible**, no cero. Tras pedir una sola frase de hasta 30 palabras, Marketing completó con 128 tokens como límite.
- El control local quedó en **6/6 intentos para octubre de 2026**. Cuenta intentos fallidos antes de llamar; no se harán más llamadas desde este entorno durante ese mes sin cambiar explícitamente el control. El límite es por esta aplicación, no por toda la cuenta de API.
- El modo real aplica 10 segundos entre llamadas, máximo 500 caracteres de entrada, 2 pares de historial, 128 tokens de salida y cero reintentos. El timeout es por intento, no un deadline total de sesión.

## Alcance del cierre

Se cumplieron los seis objetivos verificables de [GOALS.md](GOALS.md) y la medición manual mínima pedida en el paso 5. El Gate 0 técnico se acreditó para la ruta local permitida. La evaluación de routing y calidad es pequeña; no prueba rendimiento en producción. `REQUIRE_APPROVAL`/resume funcional, guardrails de contenido, HTTP, persistencia y aislamiento multi-tenant permanecen fuera del alcance de esta etapa. Los ADR propuestos conservan su estado.
