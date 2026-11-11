# Gobernanza de tools y auditoría — contras y riesgos

Fecha: 2026-11-11.

- **Acoplamiento de disponibilidad con la base de auditoría:** al ser *fail-closed*, una caída o saturación del pool hacia Neon bloquea la ejecución de herramientas `READ` (comportamiento intencional de seguridad que exige dimensionar el pool y monitorear saturación).
- **Dos mecanismos de límite coexistentes en el código:** coexisten `MonthlyCallLimiter` (`bootstrap/composition.py`, pensado para proteger pruebas locales en Etapa 1/2 con 20 llamadas/mes) y `foundation/limits.py` (`config/e3/limits.example.yaml`, ratificado para Etapa 3). Deben unificarse en la composición productiva del VPS (`PLAN-VPS.md` bloqueo 3).
- **Campaña integrada `E3-5` pendiente:** falta ejecutar la prueba sostenida de 10 minutos bajo carga real en el entorno final para cerrar formalmente el gate `E3-5`.

[[01-Investigacion/Gobernanza-tools-y-auditoria/Investigacion - gobernanza de tools y auditoría]] · [[Gobernanza de tools y auditoría - beneficios]] · [[Gobernanza de tools y auditoría - decisión]] · [[03-Implementacion/Gobernanza de tools y auditoría - estado de implementación]]
