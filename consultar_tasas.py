#!/usr/bin/env python3
# -----------------------------------------------------------------------
# Consulta diaria de tasas DTF (semanal) e IBR (diaria) en la página del
# Banco de la República (SUAMECA) y envío de correo de aviso a varios
# destinatarios recordando que hay que actualizar los datos en el core.
#
# IMPORTANTE: este script se debe correr en un computador o servidor con
# acceso normal a internet (tu PC, un servidor de la empresa). No funciona
# dentro de entornos con acceso restringido a internet (por ejemplo,
# entornos en la nube muy cerrados), porque la web del Banrep bloquea
# consultas automáticas que no vengan de una conexión "normal".
#
# INSTALACIÓN (una sola vez):
#   pip3 install playwright
#   python3 -m playwright install chromium
#
# CONFIGURACIÓN:
#   1) Copia "config_ejemplo.py" como "config.py" (mismo folder) y llena
#      tus datos de correo y la lista de destinatarios.
#
# PRUEBA MANUAL:
#   python3 consultar_tasas.py
#
# PROGRAMACIÓN DIARIA (macOS): ver instrucciones.md en este mismo folder.
# -----------------------------------------------------------------------

import base64
import json
import re
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

try:
    import config
except ImportError:
    print("ERROR: no encontré config.py. Copia config_ejemplo.py como config.py y llénalo.")
    sys.exit(1)

from playwright.sync_api import sync_playwright

CARPETA_SALIDA = Path(__file__).parent / "capturas"
CARPETA_SALIDA.mkdir(exist_ok=True)

# Cada PDF de comparación se guarda en su propia carpeta con la fecha y hora de
# la consulta: reportes/AAAA-MM-DD_HH-MM/Tasas_AAAA-MM-DD_HH-MM.pdf
CARPETA_REPORTES = Path(__file__).parent / "reportes"
MODO_PRUEBA = False  # lo activa main() con --prueba

# La primera prueba mostró que en estas páginas el número casi siempre
# aparece ANTES o justo AL LADO de la palabra clave (ej: "11,178%" seguido
# de "Tasa nominal, base 360" y luego "Indicador Bancario de Referencia
# (IBR) overnight, nominal"). Por eso, en vez de exigir un orden fijo,
# buscamos la palabra clave y tomamos el número con "%" más cercano
# (antes o después) dentro de una ventana de texto.
def _lanzar_navegador(p):
    """Abre el navegador headless. Usa el Chromium de Playwright; si no está
    descargado (ej. sin acceso a la CDN de Playwright), prueba con el Google
    Chrome ya instalado en el equipo."""
    try:
        return p.chromium.launch(headless=True)
    except Exception as e_chromium:
        try:
            return p.chromium.launch(headless=True, channel="chrome")
        except Exception:
            raise e_chromium



def extraer_cercano(texto, palabra_clave, ventana=120):
    m_clave = re.search(palabra_clave, texto, re.IGNORECASE)
    if not m_clave:
        return None
    inicio = max(0, m_clave.start() - ventana)
    fin = min(len(texto), m_clave.end() + ventana)
    fragmento = texto[inicio:fin]
    candidatos = re.findall(r"\d{1,2}[.,]\d{1,4}\s*%", fragmento)
    if candidatos:
        return candidatos[0].replace(" ", "")
    return None


def consultar_pagina(url, nombre_archivo, clics_en_texto=None):
    """Abre la página con un navegador real (headless), espera a que cargue
    el contenido dinámico, opcionalmente hace clic en uno o varios textos
    (para expandir acordeones), guarda una captura de pantalla y devuelve
    el texto visible completo de la página."""
    with sync_playwright() as p:
        navegador = _lanzar_navegador(p)
        pagina = navegador.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ))
        pagina.goto(url, timeout=45000, wait_until="networkidle")
        pagina.wait_for_timeout(3000)  # margen extra para gráficos/tablas que cargan después

        for i, texto_boton in enumerate(clics_en_texto or []):
            try:
                pagina.get_by_text(texto_boton, exact=False).first.click(timeout=8000)
                pagina.wait_for_timeout(2000)
                # captura intermedia, útil para depurar si algo no se ve bien
                pagina.screenshot(
                    path=str(CARPETA_SALIDA / f"{Path(nombre_archivo).stem}_paso{i+1}.png"),
                    full_page=True,
                )
            except Exception as e:
                print(f"[AVISO] No pude hacer clic en '{texto_boton}': {e}")

        ruta_captura = CARPETA_SALIDA / nombre_archivo
        pagina.screenshot(path=str(ruta_captura), full_page=True)

        texto = pagina.inner_text("body")
        navegador.close()
        return texto, ruta_captura


def extraer_valor(texto, palabra_clave, etiqueta, ventana=120):
    valor = extraer_cercano(texto, palabra_clave, ventana=ventana)
    if valor:
        return valor
    print(f"[AVISO] No pude reconocer automáticamente el valor de {etiqueta} en el texto de la página. "
          f"Revisa la captura de pantalla adjunta al correo y ajusta la búsqueda en el script si hace falta.")
    return None


def consultar_dtf():
    """La página de DTF es distinta a la de IBR: hay que desplegar
    'Tasas de interés de captación', hacer clic en 'DTF' y ahí aparece una
    ventana emergente con una TABLA de varias variantes de la tasa
    (semestre anticipado, semestre vencido, trimestre vencido, trimestre
    anticipado, efectiva anual). Devuelve un diccionario {variante: valor}
    y la ruta de la captura de pantalla."""
    valores = {}
    with sync_playwright() as p:
        navegador = _lanzar_navegador(p)
        pagina = navegador.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ))
        pagina.goto(config.URL_DTF, timeout=45000, wait_until="networkidle")
        pagina.wait_for_timeout(3000)

        try:
            pagina.get_by_text("Tasas de interés de captación", exact=False).first.click(timeout=8000)
            pagina.wait_for_timeout(1500)
            pagina.get_by_text("DTF", exact=True).first.click(timeout=8000)
            pagina.wait_for_timeout(2000)
        except Exception as e:
            print(f"[AVISO] No pude abrir la ventana de DTF: {e}")

        ruta_captura = CARPETA_SALIDA / "dtf.png"
        pagina.screenshot(path=str(ruta_captura), full_page=True)

        try:
            filas = pagina.query_selector_all("table tr")
            for fila in filas:
                celdas = fila.query_selector_all("td")
                if len(celdas) >= 4:
                    descripcion = celdas[0].inner_text().strip()
                    valor = celdas[3].inner_text().strip()
                    if descripcion and valor:
                        valores[descripcion] = valor
        except Exception as e:
            print(f"[AVISO] No pude leer la tabla de DTF: {e}")

        navegador.close()
    return valores, ruta_captura


def consultar_ibr():
    """Consulta la página de IBR usando la 'Vista tabla', que trae el
    histórico completo (desde 2008) con una columna por plazo: overnight,
    1 mes, 3 meses, 6 meses y 12 meses. Nos quedamos con la fila más
    reciente que tenga los 5 plazos completos (a veces la última fila
    viene con algún plazo todavía vacío) y devolvemos un diccionario
    {etiqueta: valor} + la fecha de esa fila + la captura de pantalla."""
    ibr_valores = {}
    fecha_ibr = None
    with sync_playwright() as p:
        navegador = _lanzar_navegador(p)
        pagina = navegador.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ))
        pagina.goto(config.URL_IBR, timeout=45000, wait_until="networkidle")
        pagina.wait_for_timeout(3000)

        try:
            pagina.get_by_text("Vista tabla", exact=False).first.click(timeout=8000)
            pagina.wait_for_timeout(2500)
        except Exception as e:
            print(f"[AVISO] No pude cambiar a 'Vista tabla' en la página de IBR: {e}")

        ruta_captura = CARPETA_SALIDA / "ibr.png"
        pagina.screenshot(path=str(ruta_captura), full_page=True)

        try:
            # La página tiene VARIAS tablas (la serie histórica, y también
            # tablas chiquitas de "Cotizaciones participantes" por banco).
            # Si buscamos "table tr" en toda la página se mezclan todas —
            # por eso primero ubicamos la tabla correcta: la que tiene
            # "Periodo" en su encabezado.
            tablas = pagina.locator("table")
            total_tablas = tablas.count()
            tabla_objetivo = None
            for i in range(total_tablas):
                texto_primera_fila = tablas.nth(i).locator("tr").first.inner_text()
                if "periodo" in texto_primera_fila.lower():
                    tabla_objetivo = tablas.nth(i)
                    break

            if tabla_objetivo is None:
                print("[AVISO] No encontré la tabla con encabezado 'Periodo' en la página de IBR.")
            else:
                filas_locator = tabla_objetivo.locator("tr")
                total = filas_locator.count()
                encabezado = [c.inner_text().strip() for c in filas_locator.nth(0).locator("th, td").all()]

                # La tabla trae miles de filas (desde 2008); la más reciente es
                # la última. A veces esa última fila viene con algún plazo aún
                # sin publicar, así que revisamos hacia atrás hasta encontrar
                # una fila con los 5 plazos completos.
                fila_util = None
                limite = max(total - 8, 0)
                for idx in range(total - 1, limite - 1, -1):
                    candidata = [c.inner_text().strip() for c in filas_locator.nth(idx).locator("th, td").all()]
                    if len(candidata) >= 6 and all(candidata[1:6]):
                        fila_util = candidata
                        break
                if fila_util is None:
                    fila_util = [c.inner_text().strip() for c in filas_locator.nth(total - 1).locator("th, td").all()]

                if fila_util:
                    fecha_ibr = fila_util[0]
                    for i, columna in enumerate(encabezado):
                        if i == 0 or i >= len(fila_util):
                            continue
                        col_lower = columna.lower()
                        m = re.search(r"a (\d+) mes", col_lower)
                        if "overnight" in col_lower:
                            etiqueta = "IBR OVERNIGHT"
                        elif m:
                            n = m.group(1)
                            etiqueta = f"IBR {n} MES" + ("ES" if n != "1" else "")
                        else:
                            continue
                        ibr_valores[etiqueta] = fila_util[i]
        except Exception as e:
            print(f"[AVISO] No pude leer la tabla de IBR: {e}")

        navegador.close()
    return ibr_valores, fecha_ibr, ruta_captura


IBR_OFICIALES_CORE = ("IBR 1 MES", "IBR 3 MESES", "IBR 6 MESES")


def fecha_esperada_para(nombre, fecha_esperada):
    """El chequeo de 'fila activa desde el día hábil anterior' solo tiene
    sentido para el IBR (se carga todos los días hábiles). El DTF es
    semanal, así que es normal que su fila activa tenga varios días — para
    esa no aplicamos el chequeo de fecha."""
    return fecha_esperada if nombre in IBR_OFICIALES_CORE else None


# Mapeo confirmado contra la base de datos CORE.TASA_BASE (columna
# TIPO_TASA) -> nombre que usamos internamente para cada tasa.
CODIGOS_TIPO_TASA = {
    336: "DTF efectiva anual",
    1001351: "IBR 1 MES",
    1001352: "IBR 3 MESES",
    1001353: "IBR 6 MESES",
}


def dia_habil_anterior(fecha_base):
    """Devuelve el día hábil anterior a fecha_base (salta sábados y domingos;
    OJO: no tiene en cuenta festivos colombianos, solo fines de semana)."""
    d = fecha_base - timedelta(days=1)
    while d.weekday() >= 5:  # 5 = sábado, 6 = domingo
        d -= timedelta(days=1)
    return d


def _a_fecha(valor):
    """Convierte lo que devuelva ibm_db para una columna DATE (puede llegar
    como date, datetime o string con distintos formatos) a un date de Python."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if hasattr(valor, "year") and hasattr(valor, "month") and hasattr(valor, "day"):
        return valor
    texto = str(valor).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d-%H.%M.%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None


def consultar_core_actual():
    """Consulta en la base de datos de el core (Db2, SOLO LECTURA con el usuario
    'readonly') cuál es el valor actualmente cargado (la fila abierta, sin
    FECHA_FINAL) para cada tasa que nos interesa, junto con la fecha desde la
    que quedó activa esa fila (FECHA_INICIO) — esto permite además avisar si
    parece que se saltó un día de carga. Si algo falla (falta ibm_db, no hay
    VPN, credenciales, permisos, etc.) simplemente devuelve un diccionario
    vacío y el correo sigue enviándose solo con los valores de Banrep."""
    valores_core = {}
    try:
        import ibm_db
    except ImportError:
        print("[AVISO] No tengo instalado 'ibm_db' (pip install ibm_db) — no puedo comparar "
              "contra la base de datos de el core; el correo solo tendrá los valores de Banrep.")
        return valores_core

    # Chequeo rápido de red (10 s) ANTES de usar el driver de Db2, que si no
    # llega al servidor puede quedarse esperando minutos (y en un cron
    # horario eso se acumularía).
    import socket
    try:
        socket.create_connection((config.DB2_HOST, int(config.DB2_PORT)), timeout=10).close()
    except OSError as e:
        print(f"[AVISO] No llego a la base de datos de el core ({config.DB2_HOST}:{config.DB2_PORT}) "
              f"en 10 segundos: {e}\n"
              f"    (revisa DB2_HOST/DB2_PORT en config.py, el firewall o la VPN). "
              f"El correo sigue, solo sin la comparación contra el core.")
        return valores_core

    cadena_conexion = (
        f"DATABASE={config.DB2_DATABASE};HOSTNAME={config.DB2_HOST};PORT={config.DB2_PORT};"
        f"PROTOCOL=TCPIP;UID={config.DB2_USER};PWD={config.DB2_PASSWORD};CONNECTTIMEOUT=20;"
    )
    try:
        conexion = ibm_db.connect(cadena_conexion, "", "")
    except Exception as e:
        print(f"[AVISO] No pude conectarme a la base de datos de el core: {e}\n"
              f"    (revisa si necesitas estar conectado a la VPN/red de la empresa, "
              f"o si la contraseña en config.py está bien).")
        return valores_core

    try:
        placeholders = ",".join(str(c) for c in CODIGOS_TIPO_TASA)
        sql = (
            "SELECT TIPO_TASA, TASA, FECHA_INICIO FROM CORE.TASA_BASE "
            f"WHERE TIPO_TASA IN ({placeholders}) AND FECHA_FINAL IS NULL AND ISACTIVE = 'Y'"
        )
        sentencia = ibm_db.exec_immediate(conexion, sql)
        fila = ibm_db.fetch_assoc(sentencia)
        while fila:
            etiqueta = CODIGOS_TIPO_TASA.get(int(fila["TIPO_TASA"]))
            if etiqueta:
                valores_core[etiqueta] = {
                    "tasa": fila["TASA"],
                    "fecha_inicio": _a_fecha(fila.get("FECHA_INICIO")),
                }
            fila = ibm_db.fetch_assoc(sentencia)
    except Exception as e:
        print(f"[AVISO] Me conecté a la base de datos pero falló la consulta: {e}")
    finally:
        ibm_db.close(conexion)

    return valores_core


def comparar(nombre, valor_banrep, valores_core, fecha_esperada=None):
    """Arma la línea de comparación Banrep vs. lo que ya está en el core, e
    incluye un chequeo de fecha: si la fila activa en el core es más vieja que
    el día hábil anterior, es señal de que pudo faltar cargar algún día."""
    if nombre not in valores_core:
        return f"    - {nombre}: Banrep {valor_banrep}%  |  el core: (no se pudo consultar la base de datos)"
    info = valores_core[nombre]
    valor_core = info["tasa"]
    fecha_core = info.get("fecha_inicio")

    try:
        vb = float(str(valor_banrep).replace(",", "."))
        vw = float(str(valor_core).replace(",", "."))
        al_dia_valor = abs(vb - vw) < 0.0005
        veredicto = "ya está al día — NO hace falta cargar nada" if al_dia_valor \
            else f"pendiente -> hay que cargar {valor_banrep}% en el core"
    except (TypeError, ValueError):
        veredicto = "revisar manualmente (no pude comparar los números)"

    if fecha_core and fecha_esperada:
        if fecha_core == fecha_esperada:
            estado_fecha = f"fecha OK, cargada el {fecha_core} (día hábil anterior)"
        elif fecha_core < fecha_esperada:
            dias = (fecha_esperada - fecha_core).days
            estado_fecha = (f"OJO: la última carga es del {fecha_core}, {dias} día(s) más "
                             f"atrás de lo esperado -> revisa si se saltó una carga")
        else:
            estado_fecha = f"cargada el {fecha_core}"
    else:
        estado_fecha = "(sin fecha de el core disponible)"

    return f"    - {nombre}: Banrep {valor_banrep}% | el core actual {valor_core}% [{estado_fecha}] -> {veredicto}"


def generar_pdf_resumen(dtf_valores, clave_oficial_dtf, ibr_valores, valores_core, fecha_esperada, ruta_salida):
    """Genera el PDF con el comparativo del día (mismo formato que se venía
    mandando manualmente), usando los valores reales de esta corrida."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    hoy = datetime.now().strftime("%Y-%m-%d")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Celda", parent=styles["Normal"], fontSize=9, leading=12))
    styles.add(ParagraphStyle(name="CeldaBold", parent=styles["Celda"], fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="Titulo", parent=styles["Title"], fontSize=15, spaceAfter=6))
    styles.add(ParagraphStyle(name="Subtitulo", parent=styles["Normal"], fontSize=9.5,
                              textColor=colors.HexColor("#555555"), spaceAfter=10))

    doc = SimpleDocTemplate(
        str(ruta_salida), pagesize=letter,
        topMargin=1.6 * cm, bottomMargin=1.6 * cm, leftMargin=1.6 * cm, rightMargin=1.6 * cm,
        title=f"Tasas {hoy}",
    )
    styles.add(ParagraphStyle(name="AccionOk", parent=styles["Celda"], fontName="Helvetica-Bold",
                              textColor=colors.HexColor("#1F7A3D")))
    styles.add(ParagraphStyle(name="AccionCargar", parent=styles["Celda"], fontName="Helvetica-Bold",
                              textColor=colors.HexColor("#8A5A00")))
    styles.add(ParagraphStyle(name="AccionAlerta", parent=styles["Celda"], fontName="Helvetica-Bold",
                              textColor=colors.HexColor("#B00020")))

    COLOR_FILA = {
        "ok": colors.HexColor("#E3F5E8"),
        "pendiente": colors.HexColor("#FFF3CD"),
        "alerta": colors.HexColor("#FDE2E2"),
        "sin_dato": colors.HexColor("#F0F0F0"),
    }
    FRECUENCIA = {
        "DTF efectiva anual": "Semanal",
        "IBR 1 MES": "Diario (hábil)",
        "IBR 3 MESES": "Diario (hábil)",
        "IBR 6 MESES": "Diario (hábil)",
    }

    story = [Paragraph(f"Tasas DTF / IBR &mdash; {hoy}", styles["Titulo"])]
    story.append(Paragraph(
        "La columna \"¿Cargar hoy en el core?\" te dice, para cada tasa, si toca hacer una carga "
        "nueva hoy en Sistemas Cruzados &gt; Configuración &gt; Tasas Bases. La <b>DTF</b> es "
        "<b>semanal</b> (solo cuando Banrep publica un valor distinto al ya cargado); el "
        "<b>IBR</b> es <b>diario</b> (se agrega una fila todos los días hábiles, cambie o no el valor).",
        styles["Subtitulo"],
    ))

    def fila_para(nombre, valor_banrep):
        frecuencia = FRECUENCIA.get(nombre, "")
        info = valores_core.get(nombre)
        fecha_esp_fila = fecha_esperada_para(nombre, fecha_esperada)
        if not info:
            celdas = [
                Paragraph(f"<b>{nombre}</b>", styles["Celda"]),
                Paragraph(frecuencia, styles["Celda"]),
                Paragraph(f"{valor_banrep}%", styles["Celda"]),
                Paragraph("sin dato", styles["Celda"]),
                Paragraph("sin dato", styles["Celda"]),
                Paragraph("No se pudo verificar (sin acceso a el core).", styles["AccionAlerta"]),
            ]
            return celdas, "sin_dato"

        core_txt = f'{info["tasa"]}%'
        fecha_core = info.get("fecha_inicio")
        fecha_txt = str(fecha_core) if fecha_core else "sin dato"
        try:
            vb = float(str(valor_banrep).replace(",", "."))
            vw = float(str(info["tasa"]).replace(",", "."))
            al_dia_valor = abs(vb - vw) < 0.0005
        except (TypeError, ValueError):
            al_dia_valor = None
        fecha_atrasada = bool(fecha_core and fecha_esp_fila and fecha_core < fecha_esp_fila)

        if fecha_atrasada:
            estado = "alerta"
            accion = Paragraph(
                f"SÍ &mdash; cargar {valor_banrep}% (revisar: la última carga es del {fecha_core}, "
                f"puede faltar un día).",
                styles["AccionAlerta"],
            )
        elif al_dia_valor:
            estado = "ok"
            accion = Paragraph("NO &mdash; ya está al día en el core.", styles["AccionOk"])
        else:
            estado = "pendiente"
            accion = Paragraph(f"SÍ &mdash; cargar {valor_banrep}% en el core hoy.", styles["AccionCargar"])

        celdas = [
            Paragraph(f"<b>{nombre}</b>", styles["Celda"]),
            Paragraph(frecuencia, styles["Celda"]),
            Paragraph(f"{valor_banrep}%", styles["Celda"]),
            Paragraph(core_txt, styles["Celda"]),
            Paragraph(fecha_txt, styles["Celda"]),
            accion,
        ]
        return celdas, estado

    encabezados = [Paragraph(t, styles["CeldaBold"]) for t in
                   ("Tasa", "Frecuencia", "Banrep hoy", "Activo en el core", "Fecha activa", "¿Cargar hoy en el core?")]
    filas = [encabezados]
    estados = [None]
    if clave_oficial_dtf:
        celdas, estado = fila_para("DTF efectiva anual", dtf_valores[clave_oficial_dtf])
        filas.append(celdas)
        estados.append(estado)
    for etq in IBR_OFICIALES_CORE:
        if etq in ibr_valores:
            celdas, estado = fila_para(etq, ibr_valores[etq])
            filas.append(celdas)
            estados.append(estado)

    anchos = [2.9 * cm, 2.3 * cm, 2.1 * cm, 2.3 * cm, 2.3 * cm, 6.2 * cm]
    tabla = Table(filas, colWidths=anchos, repeatRows=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F6FB2")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#CCCCCC")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    for i, estado in enumerate(estados):
        if estado:
            estilo.append(("BACKGROUND", (0, i), (-1, i), COLOR_FILA[estado]))
    tabla.setStyle(TableStyle(estilo))
    story.append(tabla)
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "\"Activo en el core\" es la última fila cargada (sin fecha de cierre). Ruta para cargar: "
        "Sistemas Cruzados &gt; Configuración &gt; Tasas Bases &gt; icono nuevo.",
        styles["Celda"],
    ))
    doc.build(story)
    return ruta_salida


RUTA_SNAPSHOT = Path(__file__).parent / "ultimo_envio.json"


def _leer_snapshot():
    """Lee el snapshot del último correo enviado hoy (fecha + valores oficiales),
    para poder comparar en la siguiente corrida de la hora y detectar si Banrep
    cambió algo desde entonces. Si no existe o está corrupto, devuelve None."""
    try:
        with open(RUTA_SNAPSHOT, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _guardar_snapshot(estado):
    datos = {"fecha": datetime.now().date().isoformat(), "valores": estado}
    with open(RUTA_SNAPSHOT, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


def _estado_comparable(dtf_valores, clave_oficial_dtf, ibr_valores):
    """Solo los valores 'oficiales' (los que de verdad se cargan en el core) —
    si alguno de estos cambia respecto al último correo enviado hoy, vale la
    pena reenviar; los cambios en las otras variantes de referencia no."""
    estado = {}
    if clave_oficial_dtf:
        estado["DTF"] = str(dtf_valores[clave_oficial_dtf]).strip()
    for etq in IBR_OFICIALES_CORE:
        if etq in ibr_valores:
            estado[etq] = str(ibr_valores[etq]).strip()
    return estado


MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
            "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _fecha_larga(d):
    return f"{d.day} de {MESES_ES[d.month - 1]} de {d.year}"


def _fmt_tasa(valor):
    """'11.471' / '10,19' / '10.190000%' -> '11,471%' / '10,19%' (coma decimal,
    mínimo 2 decimales, sin ceros de relleno)."""
    try:
        x = float(str(valor).replace("%", "").replace(",", ".").strip())
    except (TypeError, ValueError):
        return str(valor)
    t = f"{x:.3f}".rstrip("0")
    if len(t.split(".")[1]) < 2:
        t = f"{x:.2f}"
    return t.replace(".", ",") + "%"


def _estado_fila(nombre, valor_banrep, valores_core, fecha_esperada):
    """Devuelve (estado, core_txt, desde_txt, accion_txt) para una tasa oficial.
    estado: 'ok' | 'pendiente' | 'alerta' | 'sin_dato'."""
    banrep_txt = _fmt_tasa(valor_banrep)
    info = valores_core.get(nombre)
    if not info:
        return "sin_dato", "sin dato", "—", f"Cargar {banrep_txt} (no se pudo verificar el core)"
    core_txt = _fmt_tasa(info["tasa"])
    fecha_core = info.get("fecha_inicio")
    desde_txt = fecha_core.strftime("%d/%m/%Y") if fecha_core else "—"
    fecha_esp = fecha_esperada_para(nombre, fecha_esperada)
    try:
        al_dia = abs(float(str(valor_banrep).replace(",", ".")) - float(str(info["tasa"]).replace(",", "."))) < 0.0005
    except (TypeError, ValueError):
        al_dia = None
    if fecha_core and fecha_esp and fecha_core < fecha_esp:
        return "alerta", core_txt, desde_txt, (
            f"Cargar {banrep_txt} y revisar: la última carga es del {desde_txt}, puede faltar un día")
    if al_dia:
        return "ok", core_txt, desde_txt, "Al día — nada que hacer"
    return "pendiente", core_txt, desde_txt, f"Cargar {banrep_txt} en el core"


_COLORES_ESTADO = {
    "ok": ("#E3F5E8", "#1F7A3D", "#B7E1C4"),
    "pendiente": ("#FFF3CD", "#8A5A00", "#F0D98A"),
    "alerta": ("#FDE2E2", "#B00020", "#F2B8B8"),
    "sin_dato": ("#F0F0F0", "#555555", "#D5D5D5"),
}


def _html_correo(hoy_fecha, dtf_valores, ibr_valores, fecha_ibr, valores_core, fecha_esperada, es_actualizacion):
    from html import escape as e

    clave_oficial = next((k for k in dtf_valores if "efectiva anual" in k.lower()), None)
    filas = []  # (nombre_mostrado, banrep_txt, estado, core_txt, desde_txt, accion_txt)
    if clave_oficial:
        est, w, d, a = _estado_fila("DTF efectiva anual", dtf_valores[clave_oficial], valores_core, fecha_esperada)
        filas.append(("DTF efectiva anual (semanal)", _fmt_tasa(dtf_valores[clave_oficial]), est, w, d, a))
    for etq, nombre in (("IBR 1 MES", "IBR 1 mes"), ("IBR 3 MESES", "IBR 3 meses"), ("IBR 6 MESES", "IBR 6 meses")):
        if etq in ibr_valores:
            est, w, d, a = _estado_fila(etq, ibr_valores[etq], valores_core, fecha_esperada)
            filas.append((f"{nombre} (diaria)", _fmt_tasa(ibr_valores[etq]), est, w, d, a))

    estados = [f[2] for f in filas]
    if "alerta" in estados:
        general, titulo = "alerta", "REVISAR: puede faltar una carga en el core"
        sub = "La última carga de alguna tasa en el core es anterior a lo esperado. Revisa la tabla y carga lo pendiente."
    elif "pendiente" in estados or "sin_dato" in estados or not filas:
        general, titulo = "pendiente", "HAY TASAS PENDIENTES POR CARGAR EN el core"
        pend = [f[0] for f in filas if f[2] in ("pendiente", "sin_dato")]
        sub = ("Cargar hoy: " + ", ".join(pend) + ".") if pend else "No se pudo verificar el core; revisa manualmente."
    else:
        general, titulo = "ok", "TODO AL DÍA"
        sub = "Las tasas de Banrep ya están cargadas en el core. Hoy no hay nada que hacer."
    bg, fg, borde = _COLORES_ESTADO[general]
    icono = {"ok": "&#10004;", "pendiente": "&#9888;", "alerta": "&#9888;", "sin_dato": "&#9888;"}[general]

    # --- tabla principal
    trs = []
    for nombre, banrep_txt, est, w, d, a in filas:
        fbg, ffg, _ = _COLORES_ESTADO[est]
        trs.append(
            f'<tr>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #E6EAEC;font-weight:600;color:#14322E;">{e(nombre)}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #E6EAEC;text-align:right;font-weight:700;">{e(banrep_txt)}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #E6EAEC;text-align:right;">{e(w)}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #E6EAEC;text-align:center;color:#666;">{e(d)}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #E6EAEC;background:{fbg};color:{ffg};font-weight:700;">{e(a)}</td>'
            f'</tr>'
        )
    th = "padding:9px 12px;background:#1F6FB2;color:#FFFFFF;font-size:12px;text-align:{al};"
    tabla_principal = (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="border-collapse:collapse;border:1px solid #E6EAEC;font-size:14px;">'
        f'<tr><th style="{th.format(al="left")}">Tasa</th>'
        f'<th style="{th.format(al="right")}">Banrep hoy</th>'
        f'<th style="{th.format(al="right")}">Activo en el core</th>'
        f'<th style="{th.format(al="center")}">Activo desde</th>'
        f'<th style="{th.format(al="left")}">¿Qué hacer?</th></tr>'
        + "".join(trs) + '</table>'
    )

    # --- referencia (no se cargan)
    ref = []
    for desc, val in dtf_valores.items():
        if desc != clave_oficial:
            ref.append((desc, _fmt_tasa(val)))
    for etq, nombre in (("IBR OVERNIGHT", "IBR overnight"), ("IBR 12 MESES", "IBR 12 meses")):
        if etq in ibr_valores:
            ref.append((nombre, _fmt_tasa(ibr_valores[etq])))
    tabla_ref = ""
    if ref:
        trs_ref = "".join(
            f'<tr><td style="padding:6px 12px;border-bottom:1px solid #EEF1F2;color:#555;">{e(n)}</td>'
            f'<td style="padding:6px 12px;border-bottom:1px solid #EEF1F2;text-align:right;color:#555;">{e(v)}</td></tr>'
            for n, v in ref
        )
        tabla_ref = (
            '<p style="margin:22px 0 6px 0;font-size:13px;font-weight:700;color:#555;">'
            'Otras tasas de referencia <span style="font-weight:400;">(no se cargan en el core)</span></p>'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            'style="border-collapse:collapse;border:1px solid #EEF1F2;font-size:13px;">' + trs_ref + '</table>'
        )

    # --- fecha del dato IBR
    nota_ibr = ""
    if fecha_ibr:
        try:
            nota_ibr = f" (dato IBR del {_fecha_larga(datetime.strptime(fecha_ibr, '%Y/%m/%d').date())})"
        except ValueError:
            nota_ibr = f" (dato IBR del {e(str(fecha_ibr))})"

    nota_actualizacion = ""
    if es_actualizacion:
        nota_actualizacion = (
            '<div style="margin:0 0 14px 0;padding:10px 14px;background:#FFF3CD;border:1px solid #F0D98A;'
            'border-radius:6px;color:#8A5A00;font-size:13px;"><b>ACTUALIZACIÓN:</b> el Banco de la República '
            'cambió al menos un valor después del último aviso de hoy. Este correo reemplaza al anterior.</div>'
        )

    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#F4F6F7;font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#2A3B3E;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F4F6F7;"><tr><td align="center" style="padding:20px 10px;">
<table role="presentation" width="680" cellpadding="0" cellspacing="0" style="max-width:680px;width:100%;background:#FFFFFF;border-radius:8px;border:1px solid #E6EAEC;">
<tr><td style="padding:22px 26px 6px 26px;">
  <div style="font-size:11px;letter-spacing:1px;color:#10786A;font-weight:700;">COOPERATIVA · TASAS DTF / IBR</div>
  <div style="font-size:22px;font-weight:700;color:#14322E;margin-top:4px;">Tasas del {e(_fecha_larga(hoy_fecha))}</div>
  <div style="font-size:12px;color:#8A9396;margin-top:2px;">Fuente: Banco de la República{nota_ibr}</div>
</td></tr>
<tr><td style="padding:14px 26px 0 26px;">
  {nota_actualizacion}
  <div style="padding:14px 16px;background:{bg};border:1px solid {borde};border-radius:6px;">
    <div style="font-size:16px;font-weight:700;color:{fg};">{icono} {e(titulo)}</div>
    <div style="font-size:13px;color:{fg};margin-top:3px;">{e(sub)}</div>
  </div>
</td></tr>
<tr><td style="padding:18px 26px 0 26px;">
  <p style="margin:0 0 8px 0;font-size:13px;font-weight:700;color:#14322E;">Tasas que se cargan en el core</p>
  {tabla_principal}
  {tabla_ref}
</td></tr>
<tr><td style="padding:20px 26px 0 26px;">
  <div style="padding:12px 14px;background:#EEF4FA;border-radius:6px;font-size:13px;line-height:1.5;">
    <b>Dónde cargar:</b> SISTEMAS CRUZADOS &gt; CONFIGURACIÓN &gt; TASA BASES &gt; icono nuevo.<br>
    <b>Qué se carga:</b> DTF efectiva anual (cada semana) e IBR 1, 3 y 6 meses (todos los días hábiles).
  </div>
</td></tr>
<tr><td style="padding:16px 26px 22px 26px;font-size:12px;color:#8A9396;line-height:1.5;">
  Se adjuntan el PDF resumen del día y capturas de la página de origen para verificación visual.<br>
  Fuentes: <a href="{e(config.URL_DTF)}" style="color:#1F6FB2;">DTF</a> · <a href="{e(config.URL_IBR)}" style="color:#1F6FB2;">IBR</a>
</td></tr>
</table></td></tr></table></body></html>"""


def _html_error(hoy_fecha, detalle_error):
    from html import escape as e
    return f"""<!doctype html>
<html><body style="margin:0;padding:20px;background:#F4F6F7;font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#2A3B3E;">
<div style="max-width:680px;margin:auto;background:#FFFFFF;border:1px solid #E6EAEC;border-radius:8px;padding:22px 26px;">
  <div style="font-size:11px;letter-spacing:1px;color:#10786A;font-weight:700;">COOPERATIVA · TASAS DTF / IBR</div>
  <div style="padding:14px 16px;background:#FDE2E2;border:1px solid #F2B8B8;border-radius:6px;margin-top:12px;">
    <div style="font-size:16px;font-weight:700;color:#B00020;">&#9888; REVISAR: no se pudo consultar Banrep hoy</div>
    <div style="font-size:13px;color:#B00020;margin-top:3px;">Consulta las tasas manualmente y actualiza el core si hace falta ({e(_fecha_larga(hoy_fecha))}).</div>
  </div>
  <p style="font-size:13px;">DTF: <a href="{e(config.URL_DTF)}">{e(config.URL_DTF)}</a><br>
  IBR: <a href="{e(config.URL_IBR)}">{e(config.URL_IBR)}</a><br>
  Ruta en el core: SISTEMAS CRUZADOS &gt; CONFIGURACIÓN &gt; TASA BASES.</p>
  <p style="font-size:11px;color:#8A9396;margin-bottom:4px;">Detalle técnico:</p>
  <pre style="font-size:11px;color:#555;background:#F6F7F8;padding:10px;border-radius:6px;white-space:pre-wrap;">{e(detalle_error or '')}</pre>
</div></body></html>"""



def construir_correo(dtf_valores, ibr_valores, fecha_ibr, valores_core, captura_dtf, captura_ibr, hubo_error, detalle_error="", es_actualizacion=False):
    hoy_fecha = datetime.now().date()
    hoy = hoy_fecha.strftime("%Y-%m-%d")
    fecha_esperada = dia_habil_anterior(hoy_fecha)
    msg = EmailMessage()
    msg["From"] = f"{config.REMITENTE_NOMBRE} <{config.AZURE_REMITENTE}>"
    msg["To"] = ", ".join(config.DESTINATARIOS)

    if hubo_error:
        msg["Subject"] = f"[REVISAR] Tasas DTF/IBR del {hoy} - no se pudo consultar Banrep"
        cuerpo = (
            f"No fue posible consultar automáticamente las tasas hoy ({hoy}).\n\n"
            f"Detalle técnico:\n{detalle_error}\n\n"
            f"Por favor consulta manualmente en:\n"
            f"- DTF: {config.URL_DTF}\n"
            f"- IBR: {config.URL_IBR}\n\n"
            f"y actualiza el core (SISTEMAS CRUZADOS >> CONFIGURACION >> TASA BASES)."
        )
    else:
        # Confirmado por la empresa (13-ago-2026): la variante oficial que se
        # carga en el core es "DTF efectiva anual". Las otras 4 quedan solo de
        # referencia, por si el criterio cambia en el futuro.
        clave_oficial = next((k for k in dtf_valores if "efectiva anual" in k.lower()), None)
        if clave_oficial:
            dtf_oficial = f"    >>> OFICIAL PARA el core: {clave_oficial}: {dtf_valores[clave_oficial]}%\n"
        else:
            dtf_oficial = "    >>> No encontré la variante 'DTF efectiva anual' esta vez, revisa la captura.\n"

        if dtf_valores:
            lineas_dtf = dtf_oficial + "\n".join(
                f"    - {desc}: {val}%" for desc, val in dtf_valores.items() if desc != clave_oficial
            )
        else:
            lineas_dtf = "    (no se reconoció automáticamente, ver captura adjunta)"

        if ibr_valores:
            lineas_ibr = "\n".join(
                f"    - {etq}: {ibr_valores[etq]}%  <-- OFICIAL PARA el core" if etq in IBR_OFICIALES_CORE
                else f"    - {etq}: {ibr_valores[etq]}%  (referencia, NO se carga en el core)"
                for etq in ("IBR OVERNIGHT", "IBR 1 MES", "IBR 3 MESES", "IBR 6 MESES", "IBR 12 MESES")
                if etq in ibr_valores
            )
            nota_fecha_ibr = f" (dato del {fecha_ibr})" if fecha_ibr else ""
        else:
            lineas_ibr = "    (no se reconoció automáticamente, ver captura adjunta)"
            nota_fecha_ibr = ""

        # Comparación Banrep vs. lo que ya está cargado en el core (base de datos)
        lineas_comparacion = []
        hay_pendientes = False
        hay_alerta_fecha = False
        if clave_oficial:
            lineas_comparacion.append(
                comparar("DTF efectiva anual", dtf_valores[clave_oficial], valores_core,
                         fecha_esperada_para("DTF efectiva anual", fecha_esperada))
            )
        for etq in IBR_OFICIALES_CORE:
            if etq in ibr_valores:
                lineas_comparacion.append(comparar(etq, ibr_valores[etq], valores_core,
                                                    fecha_esperada_para(etq, fecha_esperada)))

        for nombre_chk, valor_chk in (
            [("DTF efectiva anual", dtf_valores.get(clave_oficial))] if clave_oficial else []
        ) + [(etq, ibr_valores[etq]) for etq in IBR_OFICIALES_CORE if etq in ibr_valores]:
            info_chk = valores_core.get(nombre_chk)
            if not info_chk:
                continue
            try:
                if abs(float(str(valor_chk).replace(",", ".")) - float(str(info_chk["tasa"]).replace(",", "."))) >= 0.0005:
                    hay_pendientes = True
            except (TypeError, ValueError):
                pass
            fi = info_chk.get("fecha_inicio")
            fecha_esp_chk = fecha_esperada_para(nombre_chk, fecha_esperada)
            if fi and fecha_esp_chk and fi < fecha_esp_chk:
                hay_alerta_fecha = True

        if lineas_comparacion:
            bloque_comparacion = (
                "\n\n¿YA ESTÁ CARGADO EN el core? (comparando contra la base de datos)\n"
                + "\n".join(lineas_comparacion)
            )
        else:
            bloque_comparacion = ""

        if hay_alerta_fecha:
            prefijo_asunto = "[REVISAR FECHA]"
        elif hay_pendientes or not valores_core:
            prefijo_asunto = "[ACCIÓN]"
        else:
            prefijo_asunto = "[AL DÍA]"
        if es_actualizacion:
            msg["Subject"] = f"{prefijo_asunto} (ACTUALIZACIÓN) Tasas DTF/IBR del {hoy} - cambió un valor"
        else:
            msg["Subject"] = f"{prefijo_asunto} Tasas DTF/IBR del {hoy} - Actualizar en el core"

        cuerpo = (
            f"Información de tasas al {hoy} (tomada de la página del Banco de la República):\n\n"
            f"- Tasa DTF (semanal), variantes disponibles:\n{lineas_dtf}\n\n"
            f"- Tasa IBR{nota_fecha_ibr}, valor Nominal por plazo:\n{lineas_ibr}"
            f"{bloque_comparacion}\n\n"
            f"Recuerda actualizar en el core SOLO: DTF efectiva anual (semanal) e IBR 1 mes / "
            f"3 meses / 6 meses (todos los días hábiles).\n"
            f"Ruta: SISTEMAS CRUZADOS >> CONFIGURACION >> TASA BASES >> icono nuevo\n\n"
            f"Se adjuntan capturas de pantalla de la página de origen y un PDF con el resumen "
            f"del día, para verificación visual.\n\n"
            f"Fuentes:\n- DTF: {config.URL_DTF}\n- IBR: {config.URL_IBR}"
        )

        if es_actualizacion:
            cuerpo = (
                "NOTA: este correo reemplaza/actualiza el envío de hoy — el Banco de la República "
                "cambió al menos uno de los valores oficiales después de la última consulta.\n\n"
            ) + cuerpo

    msg.set_content(cuerpo)
    try:
        if hubo_error:
            html_cuerpo = _html_error(hoy_fecha, detalle_error)
        else:
            html_cuerpo = _html_correo(hoy_fecha, dtf_valores, ibr_valores, fecha_ibr,
                                       valores_core, fecha_esperada, es_actualizacion)
        msg.add_alternative(html_cuerpo, subtype="html")
    except Exception as e_html:
        print(f"[AVISO] No pude armar la versión HTML del correo, se envía en texto simple: {e_html}")

    for ruta in (captura_dtf, captura_ibr):
        if ruta and Path(ruta).exists():
            with open(ruta, "rb") as f:
                msg.add_attachment(f.read(), maintype="image", subtype="png", filename=Path(ruta).name)

    if not hubo_error:
        try:
            marca = datetime.now().strftime("%Y-%m-%d_%H-%M")
            carpeta_reporte = CARPETA_REPORTES / (marca + ("_prueba" if MODO_PRUEBA else ""))
            carpeta_reporte.mkdir(parents=True, exist_ok=True)
            ruta_pdf = carpeta_reporte / f"Tasas_{marca}.pdf"
            clave_oficial_dtf = next((k for k in dtf_valores if "efectiva anual" in k.lower()), None)
            generar_pdf_resumen(dtf_valores, clave_oficial_dtf, ibr_valores, valores_core, fecha_esperada, ruta_pdf)
            with open(ruta_pdf, "rb") as f:
                msg.add_attachment(f.read(), maintype="application", subtype="pdf", filename=ruta_pdf.name)
        except Exception as e:
            print(f"[AVISO] No pude generar/adjuntar el PDF de resumen: {e}")

    return msg


def _extraer_partes_correo(msg):
    """A partir del EmailMessage armado por construir_correo(), separa el
    cuerpo de texto y los adjuntos (capturas + PDF) para poder mandarlo por
    Microsoft Graph en vez de SMTP."""
    cuerpo = ""
    cuerpo_html = ""
    adjuntos = []
    for parte in msg.walk():
        if parte.get_content_type() == "text/plain" and not parte.get_filename():
            cuerpo = parte.get_content()
        elif parte.get_content_type() == "text/html" and not parte.get_filename():
            cuerpo_html = parte.get_content()
        elif parte.get_filename():
            adjuntos.append({
                "nombre": parte.get_filename(),
                "tipo": parte.get_content_type(),
                "datos": parte.get_payload(decode=True),
            })
    return cuerpo, cuerpo_html, adjuntos


def _obtener_token_graph():
    """Pide un token de acceso a Microsoft Graph con client credentials,
    usando la app 'empresa-tasas' registrada en Entra ID (permiso de
    aplicación Mail.Send)."""
    url = f"https://login.microsoftonline.com/{config.AZURE_TENANT_ID}/oauth2/v2.0/token"
    datos = urllib.parse.urlencode({
        "client_id": config.AZURE_CLIENT_ID,
        "client_secret": config.AZURE_CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }).encode()
    peticion = urllib.request.Request(url, data=datos, method="POST")
    try:
        with urllib.request.urlopen(peticion, timeout=20) as resp:
            return json.loads(resp.read())["access_token"]
    except urllib.error.HTTPError as e:
        detalle = e.read().decode(errors="replace")
        raise RuntimeError(f"No pude obtener token de Microsoft Graph ({e.code}): {detalle}") from e


def enviar_correo(msg):
    """Envía el correo con Microsoft Graph (API de Microsoft 365), usando la
    app 'empresa-tasas'. Se usa esto en vez de SMTP porque la empresa tiene
    (o puede tener) bloqueado SMTP AUTH en Microsoft 365 por seguridad."""
    token = _obtener_token_graph()
    cuerpo, cuerpo_html, adjuntos = _extraer_partes_correo(msg)

    payload = {
        "message": {
            "subject": msg["Subject"],
            "body": ({"contentType": "HTML", "content": cuerpo_html} if cuerpo_html
                     else {"contentType": "Text", "content": cuerpo}),
            "toRecipients": [{"emailAddress": {"address": d}} for d in config.DESTINATARIOS],
            "attachments": [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": a["nombre"],
                    "contentType": a["tipo"],
                    "contentBytes": base64.b64encode(a["datos"]).decode(),
                }
                for a in adjuntos
            ],
        },
        "saveToSentItems": "true",
    }

    url = f"https://graph.microsoft.com/v1.0/users/{config.AZURE_REMITENTE}/sendMail"
    peticion = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(peticion, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        detalle = e.read().decode(errors="replace")
        raise RuntimeError(f"Microsoft Graph rechazó el envío ({e.code}): {detalle}") from e


def _a_fraccion(valor_str):
    """Convierte un valor tipo '11,230' o '10.1' (que representa un
    porcentaje, ej. 11.230%) a la fracción decimal que espera el Excel
    (0.11230), igual que se ve en las celdas ya bien formateadas del archivo."""
    return round(float(str(valor_str).replace(",", ".")) / 100, 6)


def actualizar_excel(dtf_valores, clave_oficial_dtf, ibr_valores, fecha_ibr_texto):
    """Actualiza el archivo 'FORMATO HISTORICO TASAS COLOCACION Y
    CAPTACION.xlsx' (hojas TASAS IBR y TASAS DTF) con los valores de esta
    corrida, si config.EXCEL_RUTA está configurado. No sobreescribe celdas
    que ya tengan un valor cargado (ver actualizar_excel_tasas.py). Si algo
    falla, devuelve el motivo en vez de interrumpir el resto del script."""
    ruta = getattr(config, "EXCEL_RUTA", None)
    if not ruta:
        return ["EXCEL_RUTA no está configurado en config.py, no actualicé el Excel."]

    try:
        import openpyxl
        from actualizar_excel_tasas import actualizar_ibr, actualizar_dtf
    except ImportError as e:
        return [f"No pude importar lo necesario ({e}). Revisa que 'openpyxl' esté instalado "
                f"(pip install openpyxl) y que actualizar_excel_tasas.py esté en esta misma carpeta."]

    try:
        wb = openpyxl.load_workbook(ruta)
    except Exception as e:
        return [f"No pude abrir '{ruta}': {e}"]

    resultados = []

    # --- IBR (diario) ---
    if all(etq in ibr_valores for etq in IBR_OFICIALES_CORE):
        try:
            fecha_ibr = datetime.strptime(fecha_ibr_texto, "%Y/%m/%d").date()
        except (TypeError, ValueError):
            fecha_ibr = datetime.now().date()
        v1m = _a_fraccion(ibr_valores["IBR 1 MES"])
        v3m = _a_fraccion(ibr_valores["IBR 3 MESES"])
        v6m = _a_fraccion(ibr_valores["IBR 6 MESES"])
        resultados.append("[IBR] " + actualizar_ibr(wb["TASAS IBR"], fecha_ibr, v1m, v3m, v6m))
    else:
        resultados.append("[IBR] Faltan valores de IBR esta corrida, no actualicé la hoja.")

    # --- DTF (semanal: lunes a domingo de la semana actual) ---
    if clave_oficial_dtf:
        hoy = datetime.now().date()
        lunes = hoy - timedelta(days=hoy.weekday())
        domingo = lunes + timedelta(days=6)
        valor_dtf = _a_fraccion(dtf_valores[clave_oficial_dtf])
        resultados.append("[DTF] " + actualizar_dtf(wb["TASAS DTF"], lunes, domingo, valor_dtf))
    else:
        resultados.append("[DTF] No encontré la variante 'DTF efectiva anual' esta corrida, no actualicé la hoja.")

    try:
        wb.save(ruta)
    except Exception as e:
        resultados.append(f"No pude guardar los cambios en '{ruta}': {e}")

    return resultados


def main():
    # Con --solo-ver (o -v) el script SOLO consulta y muestra en pantalla
    # los valores y las capturas de pantalla, sin enviar ningún correo.
    # Útil para probar la parte de la consulta antes de configurar el SMTP.
    solo_ver = any(arg in ("--solo-ver", "-v") for arg in sys.argv[1:])
    # Con --prueba el correo se manda SOLO al remitente (AZURE_REMITENTE), con
    # "[PRUEBA]" en el asunto, sin tocar el Excel ni el registro de "ya enviado
    # hoy" (para no interferir con el envio real programado).
    prueba = "--prueba" in sys.argv[1:]
    global MODO_PRUEBA
    MODO_PRUEBA = prueba

    dtf_valores = {}
    ibr_valores = {}
    fecha_ibr = None
    captura_dtf = captura_ibr = None
    hubo_error = False
    detalle_error = ""

    print("Consultando DTF en:", config.URL_DTF)
    try:
        dtf_valores, captura_dtf = consultar_dtf()
        if dtf_valores:
            print("  -> Variantes de DTF encontradas:")
            for desc, val in dtf_valores.items():
                marca = "  <-- OFICIAL PARA el core" if "efectiva anual" in desc.lower() else ""
                print(f"       {desc}: {val}%{marca}")
        else:
            print("  -> DTF: (no reconocida automáticamente, ver captura)")
        print(f"  -> Captura guardada en: {captura_dtf}")

        print("Consultando IBR en:", config.URL_IBR)
        ibr_valores, fecha_ibr, captura_ibr = consultar_ibr()
        if ibr_valores:
            print(f"  -> Valores de IBR encontrados (dato del {fecha_ibr}):")
            for etq, val in ibr_valores.items():
                marca = "  <-- OFICIAL PARA el core" if etq in IBR_OFICIALES_CORE else "  (referencia, no se carga)"
                print(f"       {etq}: {val}%{marca}")
        else:
            print("  -> IBR: (no reconocida automáticamente, ver captura)")
        print(f"  -> Captura guardada en: {captura_ibr}")
    except Exception:
        hubo_error = True
        detalle_error = traceback.format_exc()
        print("[ERROR] Falló la consulta a la página del Banrep:")
        print(detalle_error)

    fecha_esperada = dia_habil_anterior(datetime.now().date())
    print("\nConsultando valor actual en la base de datos de el core (CORE.TASA_BASE)...")
    valores_core = consultar_core_actual()
    if valores_core:
        print("  -> Valores actuales en el core:")
        for etq, info in valores_core.items():
            print(f"       {etq}: {info['tasa']}%  (activa desde {info.get('fecha_inicio')})")
        print(f"\n  -> Fecha esperada de la última carga (día hábil anterior): {fecha_esperada}")
        print("  -> Comparación Banrep vs. el core:")
        clave_oficial_dtf = next((k for k in dtf_valores if "efectiva anual" in k.lower()), None)
        if clave_oficial_dtf:
            print(comparar("DTF efectiva anual", dtf_valores[clave_oficial_dtf], valores_core,
                            fecha_esperada_para("DTF efectiva anual", fecha_esperada)))
        for etq in IBR_OFICIALES_CORE:
            if etq in ibr_valores:
                print(comparar(etq, ibr_valores[etq], valores_core,
                                fecha_esperada_para(etq, fecha_esperada)))
    else:
        print("  -> No se pudo consultar la base de datos de el core (ver aviso arriba). "
              "El correo se enviará solo con los valores de Banrep, sin comparación.")

    if not hubo_error and not prueba:
        clave_oficial_dtf = next((k for k in dtf_valores if "efectiva anual" in k.lower()), None)
        print("\nActualizando el Excel histórico (TASAS IBR / TASAS DTF)...")
        for linea in actualizar_excel(dtf_valores, clave_oficial_dtf, ibr_valores, fecha_ibr):
            print("  ->", linea)

    if solo_ver:
        print("\n--solo-ver activado: no se envía correo. Abre las capturas de pantalla "
              "de la carpeta 'capturas/' para ver el valor tal como aparece en la página.")
        return

    # --- Chequeo de cambios: pensado para correr este mismo script cada hora
    # (ej. de 11:30am en adelante). La primera corrida del día siempre manda
    # el correo normal. Las siguientes corridas de la misma hora solo vuelven
    # a mandarlo si Banrep cambió alguno de los valores oficiales desde el
    # último envío de hoy — si no cambió nada, no se reenvía (para no llenar
    # la bandeja de correos repetidos). Si hubo un error consultando Banrep,
    # siempre se manda el aviso de error, en cada corrida.
    es_actualizacion = False
    if prueba:
        config.DESTINATARIOS = [config.AZURE_REMITENTE]
        print(f"\n--prueba activado: el correo se manda SOLO a {config.AZURE_REMITENTE}.")
    elif not hubo_error:
        clave_oficial_dtf = next((k for k in dtf_valores if "efectiva anual" in k.lower()), None)
        estado_actual = _estado_comparable(dtf_valores, clave_oficial_dtf, ibr_valores)
        anterior = _leer_snapshot()
        hoy_iso = datetime.now().date().isoformat()
        ya_envio_hoy = bool(anterior) and anterior.get("fecha") == hoy_iso

        if ya_envio_hoy and anterior.get("valores") == estado_actual:
            print("\nNo hay cambios en las tasas desde el último correo de hoy — no se reenvía.")
            return

        es_actualizacion = ya_envio_hoy  # ya se había enviado hoy, pero con otro valor
        _guardar_snapshot(estado_actual)

    msg = construir_correo(
        dtf_valores, ibr_valores, fecha_ibr, valores_core, captura_dtf, captura_ibr, hubo_error, detalle_error,
        es_actualizacion=es_actualizacion,
    )
    if prueba:
        msg.replace_header("Subject", "[PRUEBA] " + msg["Subject"])

    try:
        enviar_correo(msg)
        print("Correo enviado correctamente.")
    except Exception:
        print("[ERROR] No se pudo enviar el correo. Revisa los datos AZURE_* en config.py "
              "(tenant, client id, client secret, remitente).")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
