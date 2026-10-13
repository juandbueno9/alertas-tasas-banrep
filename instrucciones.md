# Automatización de tasas DTF / IBR — aviso diario por correo

Este pequeño proyecto consulta la página del Banco de la República (SUAMECA)
todos los días, saca la tasa DTF (se actualiza semanal) y la tasa IBR (se
actualiza diaria), y te manda un correo a ti y a quien más agregues,
recordando actualizar el core. El ingreso al core lo sigues haciendo tú
manualmente por ahora — este script no toca el core.

## Por qué se corre en tu computador y no "en la nube"

La página del Banrep tiene protección contra consultas automáticas
(anti-bots). Al probarlo desde el entorno en la nube de Claude, la página
bloqueó la conexión. Un computador o servidor normal (como el tuyo, o uno
de la empresa) navega igual que cualquier persona, así que no debería tener
ese problema. Por eso este script está pensado para correr localmente.

## 1. Instalación (una sola vez)

Tu Mac tiene Python instalado por Homebrew, que por seguridad no deja
instalar paquetes directo con `pip3 install` (da el error
"externally-managed-environment"). La solución recomendada es crear un
entorno virtual solo para este proyecto — no afecta nada más de tu equipo.

Abre la Terminal y ejecuta:

```bash
cd ~/Documents/tasas_automatizacion
python3 -m venv venv
source venv/bin/activate
pip install playwright ibm_db reportlab openpyxl
python -m playwright install chromium
```

Esto instala: Playwright (un navegador Chrome "sin cabeza" que el script usa
para leer la página tal como la vería una persona, necesario porque el
Banrep carga los datos con JavaScript), `ibm_db` (el driver oficial de Db2
para Python, que se usa para consultar la base de datos del core y comparar
el valor contra lo ya cargado) y `reportlab` (arma el PDF de resumen que se
adjunta al correo).

Nota: cada vez que abras una Terminal nueva para correr el script a mano,
tienes que activar el entorno primero con `source venv/bin/activate`
(estando parado en la carpeta `tasas_automatizacion`). Para la
programación automática con `cron` (paso 4) no hace falta activarlo a
mano, porque ahí se llama directo al Python de dentro del `venv`.

## 2. Configurar tu correo y destinatarios

```bash
cp config_ejemplo.py config.py
```

Abre `config.py` y llena:
- `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` /
  `AZURE_REMITENTE`: datos de la app "empresa-tasas" registrada en Entra
  ID (Microsoft 365), que se usa para enviar el correo vía Microsoft Graph
  en vez de SMTP (la empresa tiene SMTP AUTH bloqueado). Se sacan del
  registro de la app en el Centro de administración Microsoft Entra >
  Registros de aplicaciones > empresa-tasas — el `AZURE_CLIENT_SECRET` es
  el "Valor" del secreto creado en "Certificados y secretos" (solo se ve
  una vez, al crearlo). No lo compartas por chat ni lo subas a ningún
  repositorio.
- `DESTINATARIOS`: la lista de correos que deben recibir el aviso todos los
  días.
- `DB2_HOST` / `DB2_PORT` / `DB2_DATABASE` / `DB2_USER` / `DB2_PASSWORD`:
  datos de conexión a la base de datos del core, para comparar el valor de
  Banrep contra lo que ya está cargado. Usa el usuario `readonly` (o uno
  de solo consulta) — nunca un usuario de escritura/admin. Llena la
  contraseña directamente aquí en tu Mac, no la compartas por chat.
  Si tu Mac necesita estar conectado a la VPN/red de la empresa para llegar
  a esa base de datos, conéctate antes de probar. Si no llenas estos datos
  (o falla la conexión), el script sigue funcionando igual, solo que el
  correo no incluye la comparación contra el core.
- `EXCEL_RUTA`: la ruta completa al archivo "FORMATO HISTORICO TASAS
  COLOCACION Y CAPTACION.xlsx" (por ahora en tu Downloads, más adelante la
  carpeta de Drive sincronizada). Ejemplo:
  `EXCEL_RUTA = "/Users/usuario/Downloads/FORMATO HISTORICO TASAS COLOCACION Y CAPTACION.xlsx"`
  Cada vez que corras el script, llena automáticamente el día de hoy en la
  hoja "TASAS IBR" y agrega la fila de la semana en "TASAS DTF" — sin
  sobreescribir ninguna celda que ya tenga un valor cargado. Si la dejas
  vacía (`""`), el script sigue igual, solo que no toca el Excel. Necesita
  el paquete `openpyxl` (ver instalación abajo) y que el archivo
  `actualizar_excel_tasas.py` esté en esta misma carpeta.

## 3. Probarlo manualmente

Asegúrate de tener el entorno activado (`source venv/bin/activate` estando
en la carpeta del proyecto) y ejecuta:

```bash
python consultar_tasas.py
```

Si todo sale bien, verás "Correo enviado correctamente." y te llegará el
correo con los valores, dos capturas de pantalla (una de la página DTF y
otra de la IBR) y un PDF adjunto (`Tasas_AAAA-MM-DD.pdf`) con el comparativo
del día generado con los datos reales de esa corrida (Banrep vs. lo que está
activo en el core, y si la fecha de la última carga en el core es la esperada).

El asunto del correo trae un prefijo para que sepas de un vistazo si hay
algo que hacer, sin necesidad de abrirlo:
- `[AL DÍA]`: todo cargado correctamente, no hace falta ninguna acción.
- `[ACCIÓN]`: hay al menos una tasa con un valor distinto al de Banrep,
  pendiente de cargar en el core.
- `[REVISAR FECHA]`: la última fila activa de IBR en el core es más vieja que el
  día hábil anterior — señal de que pudo faltar cargar algún día.
- `[REVISAR]`: no se pudo consultar la página del Banrep (fallo técnico).

Si el script está programado para correr cada hora (ver paso 4), también
puede llegar un correo con `(ACTUALIZACIÓN)` en el asunto — significa que
Banrep cambió un valor después del envío anterior de hoy, y este correo lo
reemplaza.

## Para no olvidar hacer la carga manual en el core

El correo diario es el recordatorio principal, pero como la carga en el core la
sigues haciendo tú a mano, conviene un respaldo por si un día no revisas el
correo a tiempo:

- **Regla en tu correo (Outlook/Gmail)**: crea una regla que, cuando llegue
  un correo de este remitente con asunto que empiece por `[ACCIÓN]` o
  `[REVISAR`, lo marque como importante/con bandera de seguimiento, o lo
  mueva a una carpeta "Tareas diarias" que revises todos los días.
- **Recordatorio de calendario**: un evento recurrente en tu calendario a la
  hora en que llega el correo (ej. 7:30 a.m.), como respaldo independiente
  del correo por si algún día no llega o no lo ves.
- **El propio correo se autochequea**: si un día se te olvida cargar el IBR,
  al día siguiente el asunto saldrá como `[REVISAR FECHA]` avisándote que la
  fila activa en el core quedó más atrasada de lo esperado — es una segunda
  oportunidad para notar que faltó un día, no solo confiar en no olvidarlo
  la primera vez.

**Si el valor de DTF o IBR sale como "no reconocida automáticamente"**: no
pasa nada grave, el correo igual llega con las capturas de pantalla
adjuntas para que veas el dato a simple vista. Para que el texto también
salga bien extraído, hay que ajustar el patrón de búsqueda en
`consultar_tasas.py` (las variables `PATRON_DTF` y `PATRON_IBR`) mirando el
texto real que trae la página — cuéntame qué te sale y te ayudo a
ajustarlo.

## 4. Programarlo para que corra solo todos los días (y se autocorrija si Banrep cambia el dato)

Las tasas que muestra el Banrep en su página pueden cambiar en cualquier
momento después de la primera consulta del día (a veces el dato de la
mañana es provisional y se corrige más tarde). Para no depender de mandar
el correo una sola vez a una hora fija, el script está pensado para
correr **cada hora** con una sola línea de `cron`:

- La primera corrida del día (11:30 a.m.) siempre manda el correo normal.
- Las corridas siguientes (12:30, 1:30pm, etc.) vuelven a consultar Banrep,
  pero **solo reenvían el correo si alguno de los valores oficiales (DTF
  efectiva anual, IBR 1/3/6 meses) cambió** desde el último envío de hoy —
  si no cambió nada, no hacen nada (no llenan la bandeja de correos
  repetidos). Cuando sí reenvían, el asunto trae `(ACTUALIZACIÓN)` y el
  cuerpo avisa que reemplaza el envío anterior de hoy.
- Esto se controla con un archivito `ultimo_envio.json` que el script crea
  solo en esta misma carpeta (guarda la fecha y los últimos valores
  enviados) — no hay que tocarlo ni configurarlo, se reinicia solo cada día.

En macOS, abre la Terminal y ejecuta:

```bash
crontab -e
```

Agrega esta línea (corre cada hora en punto y media, de 11:30 a.m. a
5:30 p.m., de lunes a viernes), reemplazando la ruta si tu carpeta es
distinta:

```
30 11-17 * * 1-5 cd /ruta/al/proyecto && ./venv/bin/python consultar_tasas.py >> log.txt 2>&1
```

(Usamos `./venv/bin/python`, el Python de dentro del entorno virtual que
creaste en el paso 1 — así `cron` encuentra `playwright` sin necesidad de
activar nada a mano. Si quieres que la ventana de reintentos sea más
larga o más corta, cambia el rango `11-17` por las horas que prefieras —
por ejemplo `11-19` para llegar hasta las 7:30 p.m.)

Guarda y cierra. Desde ese momento, el script se ejecutará solo cada hora
en ese rango (mientras el Mac esté encendido), y cualquier error quedará
registrado en `log.txt` en la misma carpeta.

Si prefieres que corra en un servidor de la empresa en vez de tu Mac
personal (más confiable, no depende de que tu equipo esté prendido),
pásale esta misma carpeta a sistemas — el procedimiento es idéntico.
