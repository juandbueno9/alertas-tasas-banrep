#!/usr/bin/env python3
# -----------------------------------------------------------------------
# Llena automáticamente el formato "FORMATO HISTORICO TASAS COLOCACION Y
# CAPTACION.xlsx" (hojas TASAS IBR y TASAS DTF) con los valores del día /
# de la semana, respetando el formato y las convenciones ya usadas en el
# archivo. NO sobreescribe una celda que ya tenga un valor cargado (para
# no borrar datos históricos sin que alguien lo pida explícitamente).
# -----------------------------------------------------------------------
from datetime import datetime, timedelta

MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
            "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

NO_HABIL = ("DOMINGO", "SABADO", "SÁBADO", "FESTIVO", "DIA FESTIVO", "DÍA FESTIVO")


def mapa_meses_ibr(ws):
    """Escanea la hoja 'TASAS IBR' y devuelve, para cada mes encontrado, la
    columna donde empieza su bloque (MES) y en qué fila está cada día."""
    mapa = {}
    for c in range(2, ws.max_column + 1, 6):
        mes_actual = None
        for r in range(10, ws.max_row + 1):
            val = ws.cell(row=r, column=c).value
            if isinstance(val, str) and val.strip().lower() in MESES_ES:
                mes_actual = val.strip().lower()
                mapa.setdefault(mes_actual, {"col": c, "filas": {}})
                mapa[mes_actual]["col"] = c
            if mes_actual:
                dia_val = ws.cell(row=r, column=c + 1).value
                if isinstance(dia_val, (int, float)):
                    mapa[mes_actual]["filas"][int(dia_val)] = r
    return mapa


def actualizar_ibr(ws, fecha, valor_1m, valor_3m, valor_6m):
    """Escribe el IBR (1/3/6 meses) del día 'fecha' en la hoja TASAS IBR.
    Devuelve un texto describiendo qué pasó (para loguear/revisar)."""
    mapa = mapa_meses_ibr(ws)
    mes = MESES_ES[fecha.month - 1]
    info = mapa.get(mes)
    if not info or fecha.day not in info["filas"]:
        return f"SIN_FILA: la plantilla no tiene fila para {fecha.isoformat()} " \
               f"(hay que extender la hoja para ese mes)."

    fila = info["filas"][fecha.day]
    col_mes = info["col"]
    col_mensual, col_trimestral, col_semestral = col_mes + 2, col_mes + 3, col_mes + 4

    actual = ws.cell(row=fila, column=col_mensual).value
    if isinstance(actual, str) and actual.strip().upper() in NO_HABIL:
        return f"NO_HABIL: {fecha.isoformat()} (fila {fila}) está marcado como '{actual.strip()}', no se carga IBR."
    if actual not in (None, "", " ", "\xa0"):
        return f"YA_TENIA_VALOR: {fecha.isoformat()} (fila {fila}) ya tenía un valor ({actual!r}), no lo toqué."

    for col, valor in ((col_mensual, valor_1m), (col_trimestral, valor_3m), (col_semestral, valor_6m)):
        celda = ws.cell(row=fila, column=col)
        celda.value = valor
        celda.number_format = "0.00%"
    return f"ACTUALIZADO: {fecha.isoformat()} (fila {fila}) con IBR 1m={valor_1m}, 3m={valor_3m}, 6m={valor_6m}."


def actualizar_dtf(ws, fecha_inicio, fecha_fin, valor_ea):
    """Agrega una fila nueva a TASAS DTF para la semana [fecha_inicio, fecha_fin]
    si esa semana todavía no está registrada. No modifica filas existentes.

    OJO: la columna 'No.' viene pre-numerada en la plantilla para varias
    semanas futuras (aunque las fechas y el valor todavía estén vacíos), así
    que para encontrar "la última fila real" hay que buscar la última fila
    que además de un 'No.' tenga ya una FECHA_FINAL y un valor cargados —
    no basta con mirar cuál es la última fila con algo en la columna 'No.'."""
    ultima_fila_con_datos = None
    for r in range(11, ws.max_row + 1):
        fecha_final_existente = ws.cell(row=r, column=4).value
        valor_existente = ws.cell(row=r, column=5).value
        if isinstance(fecha_final_existente, datetime) and fecha_final_existente.date() == fecha_fin:
            return f"YA_EXISTE: la semana hasta {fecha_fin.isoformat()} ya está en la fila {r}, no la toqué."
        if isinstance(fecha_final_existente, datetime) and valor_existente not in (None, "", " "):
            ultima_fila_con_datos = r

    if ultima_fila_con_datos is None:
        return "ERROR: no encontré ninguna fila con datos reales en TASAS DTF para saber dónde continuar."

    nueva_fila = ultima_fila_con_datos + 1
    # El "No." de la fila siguiente normalmente ya viene prellenado en la
    # plantilla; solo lo calculamos nosotros si de verdad falta.
    if ws.cell(row=nueva_fila, column=2).value is None:
        no_anterior = ws.cell(row=ultima_fila_con_datos, column=2).value or 0
        ws.cell(row=nueva_fila, column=2).value = no_anterior + 1

    celda_ini = ws.cell(row=nueva_fila, column=3)
    celda_ini.value = datetime.combine(fecha_inicio, datetime.min.time())
    celda_ini.number_format = ws.cell(row=ultima_fila_con_datos, column=3).number_format

    celda_fin = ws.cell(row=nueva_fila, column=4)
    celda_fin.value = datetime.combine(fecha_fin, datetime.min.time())
    celda_fin.number_format = ws.cell(row=ultima_fila_con_datos, column=4).number_format

    celda_val = ws.cell(row=nueva_fila, column=5)
    celda_val.value = valor_ea
    celda_val.number_format = "0.00%"

    return f"AGREGADO: nueva fila {nueva_fila}, semana {fecha_inicio.isoformat()} a {fecha_fin.isoformat()}, DTF EA={valor_ea}."


if __name__ == "__main__":
    import sys
    import openpyxl

    if len(sys.argv) < 2:
        print("Uso: python actualizar_excel_tasas.py ruta_al_archivo.xlsx")
        sys.exit(1)

    ruta = sys.argv[1]
    wb = openpyxl.load_workbook(ruta)

    # --- Ejemplo/prueba manual: ajusta estos valores antes de correr ---
    fecha_ibr = datetime(2026, 8, 14).date()
    ibr_1m, ibr_3m, ibr_6m = 0.11230, 0.11420, 0.11710

    print(actualizar_ibr(wb["TASAS IBR"], fecha_ibr, ibr_1m, ibr_3m, ibr_6m))

    wb.save(ruta)
    print(f"Guardado: {ruta}")
