# Cómo pasar esto a un servidor Linux de la empresa

Aclaración rápida: con Python no hay que "compilar" nada (no es como Java o
C). Lo que hay que hacer es instalar Python y las mismas librerías en el
servidor, copiar el proyecto, y programarlo con `cron` (igual que en tu
Mac) para que corra solo. Esta guía es para dársela a sistemas o para que
la sigas tú mismo si tienes acceso al servidor.

## 0. Requisitos de red (para hablar con sistemas de una vez)

El servidor necesita poder salir a internet a estas tres cosas — pídele a
sistemas que confirme que el firewall lo permite:

- `suameca.banrep.gov.co` (HTTPS, puerto 443) — de aquí se saca la DTF y el
  IBR.
- `login.microsoftonline.com` y `graph.microsoft.com` (HTTPS, puerto 443) —
  para enviar el correo con Microsoft Graph.
- `10.0.0.10` puerto `25000` (Db2/TCPIP) — la base de datos de el core. Si el
  servidor ya está en la red interna de la empresa, esto probablemente ya
  funciona (es la misma base a la que llega tu Mac); si es un servidor
  nuevo, hay que confirmarlo.

Nota sobre el Banrep: cuando probamos este scraping desde el entorno en la
nube de Claude, la página lo bloqueó por parecer tráfico de bot. Un
servidor normal de la empresa, con una IP corporativa como cualquier
computador de la empresa, debería comportarse igual que tu Mac (sin
problema) — pero vale la pena probar el paso 3 (prueba manual) antes de
programar el `cron`, para confirmarlo temprano y no descubrirlo un mes
después.

## 1. Preparar el servidor (una sola vez)

Esto asume un servidor Linux tipo Ubuntu/Debian (los comandos con `apt`);
si es CentOS/RHEL o similar, sistemas puede traducir los mismos pasos a
`yum`/`dnf`.

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

Crea una carpeta para el proyecto (puede ser bajo el usuario de servicio
que sistemas prefiera usar, no hace falta que sea root):

```bash
mkdir -p ~/tasas_automatizacion
cd ~/tasas_automatizacion
```

## 2. Copiar el proyecto al servidor

Sube estos archivos del proyecto (todos menos `config.py`, que se crea
directo en el servidor — ver paso 4):

- `consultar_tasas.py`
- `actualizar_excel_tasas.py`
- `config_ejemplo.py`

La forma más simple, si tienes acceso SSH al servidor desde tu Mac:

```bash
scp consultar_tasas.py actualizar_excel_tasas.py config_ejemplo.py usuario@servidor:~/tasas_automatizacion/
```

Si no tienes acceso SSH directo, sistemas puede subirlos por el medio que
usen normalmente (llave USB, un repositorio interno, etc.) — no hay nada
especial en estos archivos, son texto plano.

## 3. Instalar el entorno virtual y Playwright

```bash
cd ~/tasas_automatizacion
python3 -m venv venv
source venv/bin/activate
pip install playwright ibm_db reportlab openpyxl
python -m playwright install --with-deps chromium
```

El flag `--with-deps` es importante en un servidor (a diferencia de tu
Mac): instala automáticamente, vía `apt`, las librerías del sistema que
Chromium necesita para correr sin entorno gráfico (necesita permisos de
`sudo` para esa parte). Sin esto, es común que Playwright falle en un
servidor con un error de librerías faltantes (`libnss3`, `libatk`, etc.).

## 4. Configurar `config.py` directamente en el servidor

```bash
cp config_ejemplo.py config.py
nano config.py   # o el editor que prefieras
```

Llena los mismos datos que tienes en tu Mac (`AZURE_TENANT_ID`,
`AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_REMITENTE`,
`DESTINATARIOS`, los datos de `DB2_*`). Dos recomendaciones de seguridad
para este paso:

- Escríbelos directo en el servidor (por SSH o por sistemas), no los
  copies pegándolos por chat ni por correo.
- Ya que vas a tener las credenciales en dos sitios (tu Mac y el
  servidor), es un buen momento para rotar la contraseña de `DB2_PASSWORD`
  y el `AZURE_CLIENT_SECRET` — así el servidor arranca con credenciales
  frescas y sabes exactamente dónde están guardadas.

## 5. El Excel histórico: dónde vive `EXCEL_RUTA` en el servidor

Esto es lo único que no es "copiar y pegar", porque hoy el archivo
`FORMATO HISTORICO TASAS COLOCACION Y CAPTACION.xlsx` vive en el Downloads
de tu Mac — un servidor Linux no tiene acceso a eso. Tienes dos caminos:

- **Si el archivo ya está (o vas a moverlo) a una carpeta de Google Drive
  compartida**: en Linux no hay cliente oficial de Google Drive de
  escritorio, pero se puede montar esa carpeta con `rclone` (hay que
  configurarlo una vez con las credenciales de la cuenta de Drive) y
  apuntar `EXCEL_RUTA` a esa ruta montada.
- **Si la empresa tiene un servidor de archivos interno** (una carpeta
  compartida por red, tipo SMB/NFS, donde ya guardan otros documentos
  compartidos): se monta esa carpeta en el servidor Linux y `EXCEL_RUTA`
  apunta ahí.

Si prefieres, puedes dejar `EXCEL_RUTA = ""` en el servidor por ahora (el
script sigue mandando el correo normal, solo no toca el Excel) mientras
decides cuál de los dos caminos usar — no es bloqueante para lo demás.

## 6. Probarlo manualmente antes de programarlo

```bash
source venv/bin/activate
python consultar_tasas.py --solo-ver
```

Si esto funciona (te muestra los valores de DTF/IBR en pantalla sin
enviar correo), ya confirmaste que el servidor sí puede llegar al Banrep.
Después prueba el envío completo:

```bash
python consultar_tasas.py
```

## 7. Programarlo con `cron`

Igual que en tu Mac, pero en el servidor:

```bash
crontab -e
```

```
30 11-17 * * 1-5 cd ~/tasas_automatizacion && ./venv/bin/python consultar_tasas.py >> log.txt 2>&1
```

(Ajusta la ruta si el proyecto quedó en otra carpeta.) Con esto corre cada
hora de 11:30am a 5:30pm, de lunes a viernes, y solo reenvía el correo si
Banrep cambió un valor desde el último envío del día (ver la sección de
`instrucciones.md` sobre esto).

## 8. Diferencia clave vs. correrlo en tu Mac

En el servidor, el script corre solo aunque tu Mac esté apagado o
desconectado — esa es la ventaja de moverlo ahí. Pero también significa
que si algo falla (Banrep cambió el diseño de la página, se venció el
`AZURE_CLIENT_SECRET`, etc.) nadie lo va a notar mirando la pantalla —
por eso vale la pena, de vez en cuando, revisar `log.txt` en el servidor,
o pedirle a sistemas que configure una alerta simple si el archivo de log
no se actualiza en el rango de horas esperado.
