from flask import Flask, render_template, jsonify, g, request, send_file, abort
import os
from datetime import datetime, timedelta
from datetime import date
import mysql.connector
from mysql.connector import Error

#ESTE ARCHIVO ES LA APLICACIÓN WEB PRINCIPAL, QUE SE CONECTA A LA BASE DE DATOS,
# EJECUTA LAS CONSULTAS, Y SIRVE LAS PÁGINAS HTML Y LOS ARCHIVOS PDF DE FACTURAS. POR MEDIO DE CONEXIÓN API.

#esta linea hace que Flask busque los archivos estáticos (CSS, JS) en la carpeta 'static' y las plantillas HTML en la carpeta 'templates', ambas ubicadas en el mismo directorio que este script.
app = Flask(__name__, static_folder='static', template_folder='templates')

# Configuración de la base de datos (proporcionada por el usuario)
DB_CONFIG = {
	'host': '192.168.100.63',  # Ej: 'localhost' o '192.168.x.x'
	'user': 'posweb',
	'password': 'P0sW3b8842',
	'database': 'posweb',
	'port': 3306  # Ajusta si usas otro puerto
}

# Carpeta donde están los PDFs de facturas en el equipo local
# Ajusta si tu ruta es otra
FILES_DIR = r"C:\Users\ymongui\Documents\MisFacturas"


# Query solicitada por el usuario — detalle de facturas y sus líneas
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
    tv.Descripcion AS TipoVentaDescripcion,
    f.Fecha,
    f.NombreFactura
FROM posweb.t_Facturave AS f
INNER JOIN posweb.t_DetalleFacturave AS d 
    ON f.IdFactura = d.IdFactura
LEFT JOIN posweb.m_TipoVenta AS tv
    ON f.IdTipoVenta = tv.IdTipoVenta
ORDER BY f.Fecha DESC, f.NumeroFactura;
"""

# la siguiente función se puede usar para obtener una conexión a MySQL en cualquier parte del código, y se encarga de manejar errores de conexión y logging.
def get_mysql_conn():
	"""Crea una nueva conexión a MySQL usando DB_CONFIG."""
	try:
		conn = mysql.connector.connect(
			host=DB_CONFIG['host'],
			user=DB_CONFIG['user'],
			password=DB_CONFIG['password'],
			database=DB_CONFIG['database'],
			port=DB_CONFIG.get('port', 3306),
			charset='utf8mb4'
		)
		return conn
	except Error as e:
		app.logger.error('Error conectando a MySQL: %s', e)
		raise

# esta función se asegura de cerrar la conexión a MySQL al finalizar cada request, evitando conexiones abiertas innecesarias.
@app.teardown_appcontext
def close_connection(exception):
	conn = getattr(g, '_mysql_conn', None)
	if conn is not None:
		try:
			conn.close()
		except Exception:
			pass

# esta función convierte una fila de resultado de MySQL en un diccionario usando los nombres de las columnas, y maneja tipos especiales como fechas y decimales para que sean JSON serializables.
def format_row(cursor, row):
	"""Convierte una fila de cursor en dict usando nombres de columnas."""
	if not row:
		return None
	cols = [d[0] for d in cursor.description]
	out = {}
	for i in range(len(cols)):
		v = row[i]
		if isinstance(v, (datetime, date)):
			out[cols[i]] = v.isoformat()
		else:
			try:
				# mysql-connector devuelve Decimal para algunos campos; jsonify maneja bien, pero cast a float si es Decimal
				from decimal import Decimal
				if isinstance(v, Decimal):
					out[cols[i]] = float(v)
				else:
					out[cols[i]] = v
			except Exception:
				out[cols[i]] = str(v)
	return out

# llamamos a el index.html para mostrar la página principal, que luego hará llamadas AJAX a /api/ventas para obtener los datos de las ventas.
@app.route('/')
def index():
	return render_template('index.html')


@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')


def default_date_range_for_yesterday():
	# Rango completo del día anterior
	today = datetime.utcnow().date()
	yesterday = today - timedelta(days=1)
	start = datetime.combine(yesterday, datetime.min.time())
	end = datetime.combine(yesterday, datetime.max.time())
	# Formato compatible con MySQL DATETIME
	return start.strftime('%Y-%m-%d %H:%M:%S'), end.strftime('%Y-%m-%d %H:%M:%S')


@app.route('/api/ventas')
def api_ventas():
	"""Ejecuta las dos consultas usando el rango de fechas (start,end) y devuelve JSON.

	Parámetros opcionales GET: start, end (formato YYYY-MM-DD o YYYY-MM-DD HH:MM:SS).
	Si no se proveen, se toma el día anterior completo.
	"""
	start = request.args.get('start')
	end = request.args.get('end')
	if not start or not end:
		start, end = default_date_range_for_yesterday()

	# Si el usuario pasa solo la fecha (YYYY-MM-DD), ampliar a día completo
	try:
		if len(start) == 10:
			start = start + ' 00:00:00'
		if len(end) == 10:
			end = end + ' 23:59:59'
	except Exception:
		pass

	# Conectar y ejecutar
	conn = get_mysql_conn()
	cur = conn.cursor()
	try:


		cur.execute(QUERY_DETALLE_FACTURAS)
		rows = [format_row(cur, r) for r in cur.fetchall()]

		# Calcular suma de Totales por factura única (ignorar líneas duplicadas por NumeroFactura)
		# Normalizamos NumeroFactura (strip) y solo contamos la primera aparición de cada numero.
		unique_totals = {}
		seen = set()
		for r in rows:
			nf_raw = r.get('NumeroFactura')
			# ignorar filas sin NumeroFactura definido
			if nf_raw is None:
				continue
			nf = str(nf_raw).strip()
			if nf == '':
				continue
			# si ya vimos este numero, saltar (evita sumar varias líneas de la misma factura)
			if nf in seen:
				continue
			try:
				val = r.get('Total')
				if val is None:
					continue
				# Convertir a float si viene como Decimal o string
				valf = float(val)
			except Exception:
				# si no puede convertirse, saltar
				continue
			# registrar y marcar como visto
			unique_totals[nf] = valf
			seen.add(nf)

		sum_total_unique = sum(unique_totals.values())
		distinct_count = len(unique_totals)

		return jsonify({
			'count': len(rows),
			'distinct_facturas_count': distinct_count,
			'sum_total_unique_facturas': sum_total_unique,
			'rows': rows
		})
	finally:
		try:
			cur.close()
		except Exception:
			pass
		try:
			conn.close()
		except Exception:
			pass


def _find_best_file_match(nombre):
	"""Buscar el archivo dentro de FILES_DIR que mejor empareje con el nombre provisto.
	Estrategia:
	- Intentar coincidencia exacta con/without extensión (.pdf)
	- Luego buscar fichero cuyo nombre (sin extensión) contenga el nombre (sin extensión) o viceversa
	- Finalmente, usar ratio de similitud (difflib.SequenceMatcher) y devolver el mejor si supera umbral
	"""
	import difflib
	if not nombre:
		return None
	target = os.path.splitext(nombre)[0].lower()
	try:
		files = os.listdir(FILES_DIR)
	except Exception:
		return None

	
	for f in files:
		if f.lower() == nombre.lower() or f.lower() == (nombre.lower().rstrip('.pdf')):
			return os.path.join(FILES_DIR, f)

	
	candidates = []
	for f in files:
		base = os.path.splitext(f)[0].lower()
		if target in base or base in target:
			candidates.append(os.path.join(FILES_DIR, f))
	if len(candidates) == 1:
		return candidates[0]
	elif len(candidates) > 1:
		# elegir el más corto o el que tenga mayor ratio
		best = None
		best_ratio = 0.0
		for p in candidates:
			base = os.path.splitext(os.path.basename(p))[0].lower()
			r = difflib.SequenceMatcher(None, target, base).ratio()
			if r > best_ratio:
				best_ratio = r
				best = p
		if best_ratio > 0.4:
			return best

	# 3) fallback: comparar con todos por similitud
	best = None
	best_ratio = 0.0
	for f in files:
		base = os.path.splitext(f)[0].lower()
		r = difflib.SequenceMatcher(None, target, base).ratio()
		if r > best_ratio:
			best_ratio = r
			best = os.path.join(FILES_DIR, f)
	if best_ratio > 0.45:
		return best
	return None


@app.route('/file/view')
def file_view():
	"""Devuelve el PDF para visualizar en el navegador.
	Parámetros GET: nombre (el campo f.NombreFactura) opcionalmente numero.
	"""
	nombre = request.args.get('nombre')
	if not nombre:
		abort(400, 'missing nombre')
	path = _find_best_file_match(nombre)
	if not path or not os.path.isfile(path):
		abort(404, 'file not found')
	# Enviar como inline para que el navegador lo muestre
	try:
		return send_file(path, mimetype='application/pdf')
	except Exception:
		abort(500, 'error sending file')


@app.route('/file/download')
def file_download():
	"""Forzar descarga del archivo (attachment)."""
	nombre = request.args.get('nombre')
	if not nombre:
		abort(400, 'missing nombre')
	path = _find_best_file_match(nombre)
	if not path or not os.path.isfile(path):
		abort(404, 'file not found')
	try:
		return send_file(path, as_attachment=True)
	except Exception:
		abort(500, 'error sending file')


if __name__ == '__main__':
	# Run in debug mode for development. In production use a WSGI server.
	app.run(host='0.0.0.0', port=5000, debug=True)

