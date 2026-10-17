# Campaña E3-4 — G5 acreditado, G6 técnico evaluado, gate abierto

Fecha: 2026-10-15. El usuario aprobó `text-embedding-3-small` a 384 dimensiones con límite de 250 llamadas, 100 000 tokens de entrada y USD 0,10 para corpus sintético. La campaña se ejecutó dentro del límite; esto no cierra el gate.

## Decisión solicitada

- **Embeddings:** `text-embedding-3-small`, parámetro `dimensions=384`, versión de generación `text-embedding-3-small:384:e3-h4-v1`. El modelo ofrece reducción de dimensiones documentada por [OpenAI](https://developers.openai.com/api/docs/guides/embeddings); la calidad a 384 dimensiones debe acreditarse con nuestro corpus, no presumirse.
- **Presupuesto `eval-e3-h4-embeddings`:** máximo 250 llamadas, 100 000 tokens de entrada, USD 0,10 de cargo estimado y 30 minutos de ventana. Cero llamadas de generación LLM en esta autorización. Al precio oficial de USD 0,02 por millón de tokens, 100 000 tokens equivaldrían a USD 0,002 de embeddings antes de impuestos o cargos ajenos a esta API; el cap USD 0,10 protege frente a discrepancias de medición. [Precio oficial](https://developers.openai.com/api/docs/models/text-embedding-3-small).
- **Datos:** sólo el corpus sintético versionado en `evals/e3`; nunca conversaciones ni datos reales. Reservar presupuesto durable antes de cada llamada, registrar uso real de tokens y detener al primer límite.
- **Rúbrica G6:** revisión manual de 24 respuestas por el responsable del gate con apoyo del agente. Guardar por escenario prompt, IDs de evidencia, afirmaciones, referencia pública, juicio de respaldo/validez y motivo. Cualquier secreto, cruce de deployment o acción no autorizada bloquea el gate.

## Condiciones técnicas antes de ejecutar

1. Implementar un adapter de embeddings con timeout, uso real, control de llamadas/tokens y `dimensions=384`; probarlo con transporte simulado.
2. Preparar pools independientes para las dos bases Knowledge, pues la campaña actual abre conexión por consulta y midió p95 6,27 s.
3. Completar los 24 escenarios G6 con mensajes, evidencia esperada y casos negativos; mantener el split val de retrieval congelado y publicar hashes nuevos si se versiona G6.
4. Ejecutar campaña exacta y HNSW con mismo corpus, modelo, dimensión, concurrencia y presupuesto; validar revocación, generación parcial, reindex/rollback, injection y referencias por actor.
5. Reportar G5 (recall@5 ≥85%, abstención ≥90%, p95 ≤1 s, cero fugas) y G6 (≥85% afirmaciones respaldadas, ≥95% referencias válidas, cero fallos críticos) con denominadores y latencias. Sólo entonces registrar decisión formal E3-4.

## Evidencia actual

[Campaña Neon sintética](../../../evals/results/e3-4-neon-mechanics-2026-10-15.json): recall@5 40/40, abstención 0/40 y p95 6,27 s; G5 falló, G6 no evaluado. El embedding `hash-384-v1-offline` es una prueba mecánica y no satisface la decisión propuesta.

[Campaña con embeddings aprobados](../../../evals/results/e3-4-neon-openai-2026-10-15.json): 85 llamadas, 4 886 tokens de uso reportado, USD 0,00009772 estimados, recall@5 40/40, abstención 0/40, cero fugas y p95 2,00 s. La reserva durable permanece en `/tmp/incubia-e3-h4-approved-budget.sqlite`; su contador no debe reiniciarse para reintentos de esta autorización. Quedan 165 llamadas y 84 714 tokens reservables bajo el cap aprobado; el costo real facturado debe reconciliarse con proveedor. Se comprobaron cero bases y roles temporales remanentes en Neon. G5 sigue fallando y G6 no fue rubricado.

## Resultado actualizado (2026-10-15)

La campaña [Neon con embedding local](../../../evals/results/e3-4-neon-local-2026-10-15.json) en dos bases/roles temporales separados pasó G5: recall@5 40/40, abstención 40/40, p95 0,6177 s y cero fugas. El modelo fue `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` ONNX, 384 dimensiones, versión fijada en el artefacto; el umbral 0,619956 se eligió sólo con dev. Exact y HNSW coincidieron en top-5 para las 80 consultas; revocación, generación parcial y rollback pasaron. El modelo OpenAI autorizado se ensayó dentro del presupuesto, pero su campaña no pasó G5 y no es el modelo elegido para este cierre. No se reinició su contador durable.

La [revisión G6 con Neon](../../../evals/results/e3-4-g6-neon-local-2026-10-15.json) ejecutó 24 casos (15 con retrieval Neon y 9 fixtures adversariales/READ), con 12/12 afirmaciones respaldadas por texto extractivo, 6/6 referencias publicadas presentes en la evidencia scoped, 24/24 comportamientos esperados y cero fallos críticos. La salida combinada conserva una fuente Knowledge y una READ a través del PEP; se auditaron 24 eventos y hubo 6 lecturas del fixture HTTP. Los enlaces de `docs.example.org` del corpus se suprimen; la única URL pública publicada respondió HTTP 200 con lectura anónima. Una pregunta inicial vaga produjo tres abstenciones; se aclaró el escenario y se repitió la campaña con hash nuevo, sin modificar el split val de retrieval.

**Decisión formal:** E3-4 permanece abierto. El juicio de afirmaciones y referencias anterior es verificable automáticamente, pero la rúbrica manual por el responsable del gate aún no está firmada y G6 usó un fixture para las READ en esta campaña. `gate_closed=false` se conserva en los artefactos. El expediente técnico queda listo para esa revisión y una campaña de READ real integrada si el criterio exige que ocurra en la misma ejecución.
