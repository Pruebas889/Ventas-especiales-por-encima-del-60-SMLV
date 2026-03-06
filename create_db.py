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
    'host': '192.168.100.63',
    'user': 'posweb',
    'password': 'P0sW3b8842',
    'database': 'posweb',
    'port': 3306
}

QUERY_DETALLE_FACTURAS = """
SELECT 
    f.idComercial,
    f.NumeroFactura,
    f.NumeroDocumentoCliente,
    d.Refe,
    d.NombreProducto,
    d.CantidadUnidades,
    d.CantidadFracciones,
    d.ValorDescuento,
    d.ValorTotal,
    f.Total,
    f.IdTipoVenta,
    tv.Descripcion AS TipoVentaDescripcion,
    f.Fecha
FROM posweb.t_Facturave AS f
INNER JOIN posweb.t_DetalleFacturave AS d 
    ON f.IdFactura = d.IdFactura
LEFT JOIN posweb.m_TipoVenta AS tv
    ON f.IdTipoVenta = tv.IdTipoVenta
ORDER BY f.Fecha DESC, f.NumeroFactura;
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
    if len(sys.argv) > 1:
        try:
            lim = int(sys.argv[1])
        except Exception:
            lim = None
    sys.exit(fetch_and_print(limit=lim))
