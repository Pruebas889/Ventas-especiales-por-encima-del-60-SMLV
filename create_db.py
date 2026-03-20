import os
import sys
from datetime import datetime

try:
    import mysql.connector
    from mysql.connector import Error
except Exception:
    print('Necesitas instalar mysql-connector-python. Ejecuta: pip install mysql-connector-python')
    raise

# ESTE ARCHIVO ES PARA LA VERIFICACIÓN DE LA CARGA DE LA BASE DE DATOS.
# NO ES PARTE DE LA APLICACIÓN WEB, SOLO UN SCRIPT DE PRUEBA PARA CONECTAR Y MOSTRAR LOS DATOS EN CONSOLA.


# Usar la misma configuración que en ventasespeciales.py
DB_CONFIG = {
    'host': 'siidb.copservir.com',
    'user': 'jperdomolc',
    'password': '!fG6kyc809:6',
    'database': 'sii',
    'port': 3306
}

QUERY_DETALLE_FACTURAS = """
SELECT DISTINCT
    f.IDComercial, 
    f.NumeroFactura, 
    f.NumeroDocumentoCliente, 
    d.Refe,
    p.NombreProducto,
    d.CantidadUnidades,
    d.CantidadFracciones,
    d.ValorDescuento,
    d.ValorTotal,
    f.Total, 
    tv.Descripcion AS TipoVentaDescripcion, 
    f.FechaHora AS Fecha,
    CONCAT('Factura-', r.Prefijo, f.NumeroFactura, '.pdf') AS NombreFactura
FROM sii.pos_t_Factura f
INNER JOIN sii.pos_t_DetalleFactura AS d 
    ON f.IDComercial = d.IDComercial 
   AND f.NumeroCaja = d.NumeroCaja 
   AND f.NumeroFactura = d.NumeroFactura
LEFT JOIN sii.m_Producto AS p 
    ON d.Refe = p.Refe
LEFT JOIN sii.pos_m_TipoVenta tv 
    ON f.IdTipoVenta = tv.IdTipoVenta
LEFT JOIN sii.pos_m_Resolucion r 
    ON f.IDComercial = r.IDComercial 
   AND f.NumeroCaja = r.NumeroCaja 
   AND f.NumeroFactura BETWEEN r.InicioFactura AND r.FinFactura
WHERE 
  f.FechaHora >= '2026-03-05 00:00:00' 
  AND f.Total >= 1050543;
"""


def format_value(v):
    if v is None:
        return ''
    try:
        from decimal import Decimal
        if isinstance(v, Decimal):
            return str(float(v))
    except Exception:
        pass
    if isinstance(v, (datetime,)):
        return v.isoformat()
    return str(v)


def fetch_and_print(limit=None):
    """Conecta a MySQL, ejecuta la consulta y muestra los resultados en consola.

    limit: opcional, número máximo de filas a imprimir (None = todas)
    """
    try:
        conn = mysql.connector.connect(
            host=DB_CONFIG['host'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            database=DB_CONFIG['database'],
            port=DB_CONFIG.get('port', 3306),
            charset='utf8mb4'
        )
    except Error as e:
        print('Error conectando a MySQL:', e)
        return 1

    cur = conn.cursor()
    try:
        cur.execute(QUERY_DETALLE_FACTURAS)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()

        total = len(rows)
        print(f"Filas obtenidas: {total}")

        # Si hay límite, recortar la lista para impresión
        to_print = rows if limit is None else rows[:limit]

        # Calcular anchos de columna para un render simple
        col_widths = [len(c) for c in cols]
        for r in to_print:
            for i, v in enumerate(r):
                s = format_value(v)
                if len(s) > col_widths[i]:
                    col_widths[i] = min(len(s), 60)  # limitar ancho razonable

        # Encabezado
        hdr = ' | '.join(cols[i].ljust(col_widths[i]) for i in range(len(cols)))
        sep = '-+-'.join('-' * col_widths[i] for i in range(len(cols)))
        print(hdr)
        print(sep)

        for r in to_print:
            line = ' | '.join(format_value(r[i]).ljust(col_widths[i])[:col_widths[i]] for i in range(len(cols)))
            print(line)

        if limit is not None and total > limit:
            print(f"... (mostradas {limit} filas de {total})")

        # Opcional: permitir exportar a CSV
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
    return 0


if __name__ == '__main__':
    # Argumento opcional: número de filas a mostrar
    lim = None
    # argumentos:
    #   fixed  -> refrescar base fija (desde 2026-01-01 hasta hoy-10d)
    #   recent -> refrescar base reciente (últimos 10 días)
    #   both   -> refrescar ambas (por defecto si no se indica)
    mode = 'both'
    if len(sys.argv) > 1:
        a = sys.argv[1].lower()
        if a in ('fixed', 'recent', 'both'):
            mode = a
        else:
            # si es número, lo interpretamos como limit
            try:
                lim = int(sys.argv[1])
            except Exception:
                lim = None

    try:
        from cache_db import refresh_fixed, refresh_recent
        if mode == 'fixed':
            print('Refrescando base FIXED...')
            res = refresh_fixed(DB_CONFIG, QUERY_DETALLE_FACTURAS, limit=lim)
            print('Fixed updated:', res)
            sys.exit(0)
        elif mode == 'recent':
            print('Refrescando base RECENT...')
            res = refresh_recent(DB_CONFIG, QUERY_DETALLE_FACTURAS, limit=lim)
            print('Recent updated:', res)
            sys.exit(0)
        else:
            print('Refrescando ambas bases (FIXED y RECENT)...')
            rf = refresh_fixed(DB_CONFIG, QUERY_DETALLE_FACTURAS, limit=lim)
            rr = refresh_recent(DB_CONFIG, QUERY_DETALLE_FACTURAS, limit=lim)
            print('Fixed:', rf)
            print('Recent:', rr)
            sys.exit(0)
    except Exception as e:
        print('No se pudo usar cache_db (o ocurrió error):', e)
        print('Haciendo fetch directo en consola como fallback...')
        sys.exit(fetch_and_print(limit=lim))
