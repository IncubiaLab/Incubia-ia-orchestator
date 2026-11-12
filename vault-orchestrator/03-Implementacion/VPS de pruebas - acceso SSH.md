---
tipo: operacion
tema: Acceso SSH al VPS de pruebas del orchestrator
estado: acceso-verificado-despliegue-pendiente
fecha: 2026-11-11
---

# VPS de pruebas — acceso SSH

## Identificación y propósito

| Campo | Valor |
| --- | --- |
| Entorno | VPS de pruebas de la empresa para desplegar el orchestrator completo |
| IP pública | `2.24.201.39` |
| Usuario SSH | `hector` |
| Hostname observado | `srv2113451` |
| Sistema observado | Ubuntu 24.04, `x86_64` |
| Herramientas encontradas | `docker` y `git` disponibles en `/usr/bin` |
| Estado | Acceso SSH por clave verificado el 2026-11-11; despliegue del orchestrator pendiente |

La API será la interfaz de acceso para los aplicativos consumidores; el runtime completo del orchestrator debe ejecutarse en este VPS, conforme a [[Despliegue del orchestrator en VPS - decisión]] y `docs/roadmap/etapa-3/PLAN-VPS.md`.

## Conexión estándar

Desde un equipo o agente con una clave SSH pública autorizada para `hector` y la huella del host ya verificada:

```bash
ssh hector@2.24.201.39
```

Alias sugerido para `~/.ssh/config` de cada operador (configuración local, fuera del repositorio):

```sshconfig
Host incubia-orchestrator-test
    HostName 2.24.201.39
    User hector
    Port 22
    PreferredAuthentications publickey
    IdentitiesOnly yes
    IdentityFile ~/.ssh/<clave_autorizada>
    StrictHostKeyChecking yes
```

Sustituir `<clave_autorizada>` por la ruta de la clave privada autorizada en ese equipo. Después, usar `ssh incubia-orchestrator-test`. No copiar claves privadas, contraseñas ni secretos de despliegue al vault o al repositorio.

## Verificación de identidad del servidor

El archivo `known_hosts` del entorno desde el que se probó la conexión contenía estas huellas el 2026-11-11:

| Algoritmo | Huella SHA256 |
| --- | --- |
| ED25519 | `SHA256:5DYjxTjsRlou1tgIXgvg2ucAleXh7nhMoVSCEcS3bkc` |
| RSA | `SHA256:E/FAH44dw+gJaP3uOCxC5nv2fy0WRVYSEWtzK8FPcKk` |
| ECDSA | `SHA256:0X3pjQb+f/hQ07z8bEja04qv5kiCNGbBTXYzPDogulA` |

Son huellas observadas en el `known_hosts` local, no una validación independiente con el proveedor del VPS. Antes de aceptar una clave nueva o cambiada, contrastar la huella por un canal administrativo independiente. No desactivar `StrictHostKeyChecking` para resolver una discrepancia.

## Evidencia y operación pendiente

- Se ejecutó una conexión SSH no interactiva con autenticación por clave y `StrictHostKeyChecking=yes`; terminó con código 0. Una segunda consulta de solo lectura confirmó hostname, sistema, arquitectura y presencia de `docker` y `git`.
- En el entorno de Codex, la configuración global `/etc/ssh/ssh_config.d/20-systemd-ssh-proxy.conf` presentó un error de permisos. Para la comprobación se omitió únicamente esa configuración local con `ssh -F /dev/null ...`; no se cambió la configuración del VPS.
- No se han verificado todavía la versión de Docker Compose, los recursos reales, el firewall, el proxy HTTPS, los volúmenes, los backups ni el arranque del orchestrator. Registrar esas comprobaciones durante la preparación de staging indicada en `PLAN-VPS.md`.

[[Despliegue del orchestrator en VPS - estado de implementación]] · [[01-Investigacion/Despliegue-VPS/Investigacion - despliegue del orchestrator en VPS]]
