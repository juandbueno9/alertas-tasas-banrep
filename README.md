# Alertas de tasas Banrep

Automatización que consulta cada hora las tasas de referencia publicadas por el **Banco de la República** (DTF e IBR), las compara con las cargadas en la base de datos del core financiero y envía un correo cuando hay que actualizarlas.

![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-2EAD33?logo=playwright&logoColor=white)
![IBM Db2](https://img.shields.io/badge/IBM_Db2-052FAD?logo=ibm&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-FCC624?logo=linux&logoColor=black)

## Cómo funciona

```
cron (L-V, 12:00–17:00) ──► consultar_tasas.py
                               ├─ Playwright (Chromium headless) ──► portal Banrep: DTF, IBR
                               ├─ Db2 (usuario de SOLO LECTURA) ──► tasas cargadas en el core
                               ├─ compara valor y fecha de vigencia
                               └─ Microsoft Graph ──► correo HTML + PDF resumen
```

- La **primera corrida del día** siempre envía el correo; las siguientes solo si Banrep cambió una tasa.
- Si la base de datos no responde, el correo sale igual con los valores de Banrep y un aviso.
- El correo sale por **Microsoft Graph** (app de Entra ID con permiso `Mail.Send`), sin contraseñas SMTP.

## Instalación en servidor (Ubuntu)

`instalar.sh` deja todo listo en una sola ejecución y es **idempotente** (se puede correr varias veces):

1. Instala Python y crea el entorno virtual.
2. Instala Playwright con Chromium y sus dependencias del sistema.
3. Hace una prueba de consulta sin enviar correo.
4. Programa el `cron`, ajustando la hora si el servidor no está en hora de Colombia.

```bash
cp config_ejemplo.py config.py   # completa credenciales (config.py está en .gitignore)
bash instalar.sh
```

Guía completa: [despliegue_servidor_linux.md](despliegue_servidor_linux.md).

## Uso manual

```bash
python consultar_tasas.py            # consulta, compara y envía correo
python consultar_tasas.py --solo-ver # solo muestra en pantalla, sin enviar
```

## Seguridad
- Credenciales solo en `config.py`, fuera de git.
- Usuario de base de datos de **solo lectura**.
- Secreto de la app de Entra ID rotado al pasar a producción.
