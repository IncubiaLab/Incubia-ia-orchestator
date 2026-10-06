# Verificación de la etapa 1

Fecha: 2026-10-02. Modelo elegido: `gpt-4o-mini` compartido por General, Ventas y Marketing. Estado: **validación local completada; medición real pendiente**.

## Evidencia local

- Instalación en un entorno Python 3.12 nuevo desde `requirements.lock`, seguida de `pip install --no-deps -e .`: completada.
- Comando instalado `incubia chat --fake -m "necesito una campaña"`: CompletedExecution, especialidad Marketing.
- Suite `pytest -q`: pruebas de contrato, policy, runtime, proveedor simulado, routing, CLI, fronteras de imports y bloqueo de red en proceso y subproceso. El bloqueo se comprueba provocando un intento de conexión.
- REPL fake: tres turnos, `/help`, `/exit`, IDs y especialidades visibles. El historial se acota a pares completos y se descarta al reiniciar.
- Evaluación de routing: 15/15 en `evals/routing-v1.jsonl` (5 Ventas, 5 Marketing, 5 General, incluidos 2 ambiguos). Es un conjunto inicial escrito junto con las reglas; no mide generalización.
- Errores simulados: autenticación, límite de peticiones, fallo remoto, timeout del FakeLLM y excepción inesperada de runtime se traducen a códigos propios; no exponen el detalle técnico.

## Medición real pendiente

No hay `OPENAI_API_KEY` en el entorno de ejecución; no se hicieron llamadas a `api.openai.com`. Por ello no se puede afirmar latencia, costo, calidad ni tasa de fallos reales. Los valores del fake no sustituyen esa evidencia. La suscripción a Codex/ChatGPT no concede automáticamente crédito de API.

Procedimiento para registrar una línea base después de habilitar facturación de API:

1. En una shell local, configurar `OPENAI_API_KEY` sin escribirla en el repositorio.
2. Ejecutar una solicitud por perfil con `incubia chat --model gpt-4o-mini -m "..."`; usar, por ejemplo, `hola`, `quiero vender` y `necesito una campaña`.
3. Guardar fecha, modelo, perfil, `latency_ms`, `input_tokens`, `output_tokens`, resultado y código de fallo si lo hubo. No guardar el texto de entrada ni la respuesta en logs de medición.
4. Calcular costo estimado por turno con los tokens informados. Si falta `usage`, registrar **no disponible**, no cero.
5. Evaluar manualmente si la respuesta siguió el perfil y fue útil. Un resultado correcto de routing no prueba calidad de respuesta.

| Perfil | Latencia real | Tokens entrada | Tokens salida | Costo estimado | Calidad observada |
| --- | --- | --- | --- | --- | --- |
| General | Pendiente | Pendiente | Pendiente | Pendiente | Pendiente |
| Ventas | Pendiente | Pendiente | Pendiente | Pendiente | Pendiente |
| Marketing | Pendiente | Pendiente | Pendiente | Pendiente | Pendiente |

Como referencia consultada el 2026-10-02, la [ficha oficial de GPT-4o mini](https://developers.openai.com/api/docs/models/gpt-4o-mini) indica USD 0,15 por millón de tokens de entrada y USD 0,60 por millón de salida. Verificar la tarifa vigente antes de calcular: `USD = input_tokens × 0,15 / 1 000 000 + output_tokens × 0,60 / 1 000 000`. Esta estimación simple no separa tokens de entrada cacheados. La [facturación de API](https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform) es distinta de la suscripción de ChatGPT.

## Alcance del cierre

Los objetivos locales de GOALS están verificados. La etapa completa continúa pendiente de la medición real. `REQUIRE_APPROVAL`/resume funcional y guardrails de contenido siguen fuera del alcance acreditado por Gate 0. Los ADR propuestos conservan su estado.
