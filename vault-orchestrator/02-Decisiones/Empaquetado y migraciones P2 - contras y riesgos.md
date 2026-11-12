# Empaquetado y migraciones P2 — contras y riesgos

Fecha: 2026-11-11.

- **Tiempo de build en CI:** La compilación de la imagen en CI añade ~1 minuto al workflow offline (compensado por asegurar que no se promuevan commits rotos a nivel de contenedor).
- **Separación de bases para Knowledge:** La cadena `001`–`008` aplica al ledger conversacional y auditoría. Para la base separada de Knowledge por deployment (`ADR-ORCH-010`), se mantiene el script dedicado `scripts/e3/migrate_knowledge.py` con el rol `incubia_kb_migrator`.

[[01-Investigacion/Empaquetado-P2/Investigacion - empaquetado reproducible y cadena completa de migraciones P2]] · [[Empaquetado y migraciones P2 - beneficios]] · [[Empaquetado y migraciones P2 - decisión]] · [[03-Implementacion/Empaquetado y migraciones P2 - estado de implementación]]
