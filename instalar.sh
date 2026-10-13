#!/usr/bin/env bash
# -----------------------------------------------------------------------
# Instala y programa "alertas-tasas" en ESTA misma carpeta del servidor
# (/opt/enterprise-projects/alertas-tasas). Se corre una sola vez, como el
# usuario "ubuntu" (usa sudo solo para instalar paquetes del sistema):
#
#     cd /opt/enterprise-projects/alertas-tasas && bash instalar.sh
#
# Antes de correrlo deben estar en esta carpeta: consultar_tasas.py,
# actualizar_excel_tasas.py y config.py (ya con los datos reales).
#
# Qué deja funcionando:
#   - Corre cada hora, de 12:00 m. a 5:00 p.m. (hora de Colombia), de lunes
#     a viernes.
#   - La primera corrida del día (12:00 m.) SIEMPRE manda el correo.
#   - Las siguientes (1pm, 2pm, ...) solo reenvían si Banrep cambió una tasa.
#   - Solo notifica por correo (EXCEL_RUTA vacío en config.py = no toca Excel).
# -----------------------------------------------------------------------
set -euo pipefail

DESTINO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DESTINO"

for f in consultar_tasas.py actualizar_excel_tasas.py config.py; do
  if [ ! -f "$f" ]; then
    echo "ERROR: falta $f en $DESTINO. Súbelo primero (ver instrucciones)."
    exit 1
  fi
done

echo "==> Instalando Python y utilidades del sistema (pide sudo)"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip

echo "==> Creando entorno virtual e instalando paquetes de Python"
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install playwright ibm_db reportlab openpyxl

echo "==> Instalando Chromium para Playwright (+ librerías del sistema)"
./venv/bin/python -m playwright install chromium
sudo ./venv/bin/python -m playwright install-deps chromium

mkdir -p capturas
chmod 600 config.py

echo ""
echo "==> Prueba de consulta (sin enviar correo): Banrep + base de datos el core"
if TZ=America/Bogota timeout 300 ./venv/bin/python consultar_tasas.py --solo-ver; then
  echo "==> Prueba OK."
else
  echo "==> AVISO: la prueba falló. Revisa el mensaje de arriba (¿Banrep bloquea"
  echo "    la IP del servidor? ¿el servidor llega a la base de datos el core?)."
  echo "    El cron igual se programa, pero no sirve hasta que la prueba pase."
fi

# ---- Hora del cron: el servidor puede estar en otra zona horaria que Colombia.
# Colombia es UTC-5 todo el año (sin horario de verano).
OFF="$(date +%z)"                       # ej. +0000 o -0500
SIGNO="${OFF:0:1}"; HH=$((10#${OFF:1:2}))
if [ "$SIGNO" = "-" ]; then SRV=$((-HH)); else SRV=$HH; fi
DELTA=$((SRV + 5))                      # hora_servidor = hora_Colombia + DELTA
H_INI=$((12 + DELTA)); H_FIN=$((17 + DELTA))
if [ "$H_INI" -lt 0 ] || [ "$H_FIN" -gt 23 ]; then
  echo "ERROR: la zona horaria del servidor ($OFF) hace que el horario cruce la"
  echo "medianoche; programa el cron a mano (crontab -e)."
  exit 1
fi

LINEA_CRON="0 ${H_INI}-${H_FIN} * * 1-5 cd ${DESTINO} && TZ=America/Bogota timeout 900 ./venv/bin/python consultar_tasas.py >> log.txt 2>&1"

echo "==> Programando el cron (hora del servidor: $(date +%Z) $OFF)"
( crontab -l 2>/dev/null | grep -vF "$DESTINO" || true; echo "$LINEA_CRON" ) | crontab -

echo ""
echo "==================================================================="
echo "LISTO. alertas-tasas quedó instalado en $DESTINO"
echo ""
echo "Cron instalado:"
crontab -l | grep -F "$DESTINO"
echo ""
echo "Revisar después:"
echo "  - Ver lo que ha hecho:   tail -n 50 $DESTINO/log.txt"
echo "  - Probar un envío real:  cd $DESTINO && TZ=America/Bogota ./venv/bin/python consultar_tasas.py"
echo "==================================================================="
