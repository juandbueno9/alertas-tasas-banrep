# -----------------------------------------------------------------------
# CONFIGURACIÓN - copia este archivo como "config.py" y llena tus datos.
# No subas config.py a ningún repositorio compartido (tiene tu contraseña).
# -----------------------------------------------------------------------

# -----------------------------------------------------------------------
# Envío de correo: Microsoft Graph (app "empresa-tasas" en Entra ID)
#
# la empresa usa Microsoft 365 con SMTP AUTH bloqueado, así que el correo se
# envía con la API de Microsoft Graph en vez de SMTP. Estos datos salen del
# registro de la app "empresa-tasas" en Entra ID (centro de administración
# Microsoft Entra > Registros de aplicaciones > empresa-tasas):
#
#   AZURE_TENANT_ID     -> "Id. de directorio (inquilino)" en Información general
#   AZURE_CLIENT_ID     -> "Id. de aplicación (cliente)" en Información general
#   AZURE_CLIENT_SECRET -> el "Valor" del secreto creado en Certificados y secretos
#                          (ojo: el valor solo se ve una vez, al crearlo)
#   AZURE_REMITENTE     -> el correo desde el cual se envía (normalmente el tuyo)
#
# IMPORTANTE DE SEGURIDAD: AZURE_CLIENT_SECRET es como una contraseña de la
# app — no la pegues a Claude en el chat ni la subas a ningún repositorio.
# Si el permiso Mail.Send de esta app quedó como "Send mail as any user"
# (permiso de aplicación, sin restringir), pide a sistemas que lo limiten
# con una Application Access Policy en Exchange Online para que solo pueda
# enviar como AZURE_REMITENTE.
# -----------------------------------------------------------------------
AZURE_TENANT_ID = "tu_tenant_id_aqui"
AZURE_CLIENT_ID = "tu_client_id_aqui"
AZURE_CLIENT_SECRET = "tu_client_secret_aqui"
AZURE_REMITENTE = "alertas@empresa.com"

# -----------------------------------------------------------------------
# Excel histórico (FORMATO HISTORICO TASAS COLOCACION Y CAPTACION.xlsx)
#
# Ruta completa al archivo. El script llena automáticamente la hoja
# "TASAS IBR" (diario) y agrega filas nuevas en "TASAS DTF" (semanal),
# sin sobreescribir ninguna celda que ya tenga un valor. Si dejas esto
# vacío (""), el script sigue funcionando igual, solo que no toca el Excel.
# -----------------------------------------------------------------------
EXCEL_RUTA = ""

# Nombre que verán los destinatarios como remitente
REMITENTE_NOMBRE = "Automatización de Tasas"

# --- Destinatarios: agrega aquí todos los correos que deben recibir el aviso ---
DESTINATARIOS = [
    "alertas@empresa.com",
    # "usuario@empresa.com",
    # "usuario@empresa.com",
]

# --- URLs fuente (tomadas del documento del core) ---
URL_DTF = "https://suameca.banrep.gov.co/indicadores-economicos-del-dia/"
URL_IBR = "https://suameca.banrep.gov.co/estadisticas-economicas/informacionSerie/241/tasas_interes_indicador_bancario_referencia_ibr"

# -----------------------------------------------------------------------
# Base de datos del core (Db2) - SOLO LECTURA, para comparar el valor de Banrep
# contra lo que ya está cargado en el core y decir si toca actualizar.
#
# IMPORTANTE DE SEGURIDAD:
#   - Usa aquí el usuario "readonly" (o uno de solo consulta), NUNCA un
#     usuario con permisos de escritura/admin.
#   - Llena esta contraseña directamente en tu Mac. No se la pegues a
#     Claude en el chat ni la subas a ningún repositorio.
# -----------------------------------------------------------------------
DB2_HOST = "10.0.0.10"
DB2_PORT = "25000"
DB2_DATABASE = "COREDB"
DB2_USER = "readonly"
DB2_PASSWORD = "tu_contraseña_aqui"
