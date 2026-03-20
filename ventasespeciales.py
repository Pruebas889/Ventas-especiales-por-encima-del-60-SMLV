from flask import Flask, render_template, jsonify, g, request, send_file, abort
import os
from datetime import datetime, timedelta, date, timezone
from datetime import date, timezone  # Asegúrate de importar timezone
import mysql.connector
from mysql.connector import Error
import logging
import threading
import time
import calendar

# Configurar logging para ver mejor los mensajes
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Import cache helper (local SQLite cache)
try:
    from cache_db import refresh_fixed, refresh_recent, get_combined_rows, get_cache_info, init_db
except Exception as e:
    logging.warning(f"Error importando cache_db: {e}")
    refresh_fixed = None
    refresh_recent = None
    get_combined_rows = None
    get_cache_info = None
    init_db = None

app = Flask(__name__, static_folder='static', template_folder='templates')

# Configuración de la base de datos
DB_CONFIG = {
    'host': 'siidb.copservir.com',
    'user': 'jperdomolc',
    'password': '!fG6kyc809:6',
    'database': 'sii',
    'port': 3306
}

FILES_DIR = r"C:\Users\ymongui\Documents\MisFacturas"

# Query base (sin filtro de fecha)
QUERY_BASE = """
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
  f.Total >= 1050543
"""

def get_month_queries():
    """
    Genera consultas por cada mes desde enero 2026 hasta el mes actual
    """
    today = datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=10)
    
    logging.info(f"Generando consultas por mes hasta: {cutoff}")
    
    queries = []
    current_date = date(2026, 1, 1)
    
    while current_date <= cutoff:
        last_day = calendar.monthrange(current_date.year, current_date.month)[1]
        month_start = current_date
        month_end = date(current_date.year, current_date.month, last_day)
        
        if month_end > cutoff:
            month_end = cutoff
        
        month_query = QUERY_BASE + f" AND f.FechaHora BETWEEN '{month_start} 00:00:00' AND '{month_end} 23:59:59'"
        queries.append({
            'month': f"{current_date.year}-{current_date.month:02d}",
            'start': f"{month_start} 00:00:00",
            'end': f"{month_end} 23:59:59",
            'query': month_query
        })
        
        if current_date.month == 12:
            current_date = date(current_date.year + 1, 1, 1)
        else:
            current_date = date(current_date.year, current_date.month + 1, 1)
    
    logging.info(f"Generadas {len(queries)} consultas mensuales")
    return queries

def refresh_fixed_by_month(mysql_config, specific_month=None, limit_per_query=1000):  # ← Límite por defecto
    """
    Refresca la base FIXED consultando mes por mes
    """
    if refresh_fixed is None:
        logging.error("refresh_fixed no está disponible")
        return None
    
    all_queries = get_month_queries()
    
    if specific_month:
        month_queries = [q for q in all_queries if q['month'] == specific_month]
        if not month_queries:
            logging.warning(f"Mes {specific_month} no encontrado")
            return None
    else:
        month_queries = all_queries
    
    total_rows = 0
    results = []
    months_processed = []
    
    for i, month_info in enumerate(month_queries):
        try:
            logging.info(f"Ejecutando consulta para mes {month_info['month']} ({i+1}/{len(month_queries)})")
            
            current_query = month_info['query']
            if limit_per_query:
                current_query = current_query.rstrip(';') + f' LIMIT {int(limit_per_query)};'
            
            result = refresh_fixed(
                mysql_config, 
                current_query,
                start_iso=month_info['start'],
                end_iso=month_info['end'],
                limit=limit_per_query
            )
            
            if result and 'rows' in result:
                month_rows = result.get('rows', 0)
                total_rows += month_rows
                results.append(result)
                months_processed.append(month_info['month'])
                logging.info(f"Mes {month_info['month']}: {month_rows} filas")
            else:
                logging.warning(f"Mes {month_info['month']} sin resultados")
            
        except Exception as e:
            logging.error(f"Error en mes {month_info['month']}: {e}")
    
    return {
        'rows': total_rows,
        'months_processed': months_processed,
        'periods': len(results),
        'last_refresh': datetime.now(timezone.utc).isoformat()
    }
    

def get_weekly_queries_for_month(year, month):
    """
    Divide un mes en consultas semanales para evitar timeouts
    """
    queries = []
    
    # Determinar el último día del mes
    last_day = calendar.monthrange(year, month)[1]
    
    # Semana 1: días 1-7
    week1_end = min(7, last_day)
    queries.append({
        'period': f"{year}-{month:02d}-semana1",
        'start': f"{year}-{month:02d}-01 00:00:00",
        'end': f"{year}-{month:02d}-{week1_end} 23:59:59",
        'query': QUERY_BASE + f" AND f.FechaHora BETWEEN '{year}-{month:02d}-01 00:00:00' AND '{year}-{month:02d}-{week1_end} 23:59:59'"
    })
    
    # Semana 2: días 8-14
    if last_day >= 8:
        week2_end = min(14, last_day)
        queries.append({
            'period': f"{year}-{month:02d}-semana2",
            'start': f"{year}-{month:02d}-08 00:00:00",
            'end': f"{year}-{month:02d}-{week2_end} 23:59:59",
            'query': QUERY_BASE + f" AND f.FechaHora BETWEEN '{year}-{month:02d}-08 00:00:00' AND '{year}-{month:02d}-{week2_end} 23:59:59'"
        })
    
    # Semana 3: días 15-21
    if last_day >= 15:
        week3_end = min(21, last_day)
        queries.append({
            'period': f"{year}-{month:02d}-semana3",
            'start': f"{year}-{month:02d}-15 00:00:00",
            'end': f"{year}-{month:02d}-{week3_end} 23:59:59",
            'query': QUERY_BASE + f" AND f.FechaHora BETWEEN '{year}-{month:02d}-15 00:00:00' AND '{year}-{month:02d}-{week3_end} 23:59:59'"
        })
    
    # Semana 4: días 22-fin del mes
    if last_day >= 22:
        queries.append({
            'period': f"{year}-{month:02d}-semana4",
            'start': f"{year}-{month:02d}-22 00:00:00",
            'end': f"{year}-{month:02d}-{last_day} 23:59:59",
            'query': QUERY_BASE + f" AND f.FechaHora BETWEEN '{year}-{month:02d}-22 00:00:00' AND '{year}-{month:02d}-{last_day} 23:59:59'"
        })
    
    logging.info(f"Mes {year}-{month:02d} dividido en {len(queries)} semanas")
    return queries

def refresh_fixed_by_week(mysql_config, year, month, limit_per_query=200):
    """
    Refresca un mes específico dividido por semanas
    """
    if refresh_fixed is None:
        logging.error("refresh_fixed no está disponible")
        return None
    
    weekly_queries = get_weekly_queries_for_month(year, month)
    total_rows = 0
    weeks_processed = []
    
    for i, week_info in enumerate(weekly_queries):
        try:
            logging.info(f"Ejecutando {week_info['period']} ({i+1}/{len(weekly_queries)})")
            
            current_query = week_info['query']
            if limit_per_query:
                current_query = current_query.rstrip(';') + f' LIMIT {int(limit_per_query)};'
            
            result = refresh_fixed(
                mysql_config, 
                current_query,
                start_iso=week_info['start'],
                end_iso=week_info['end'],
                limit=limit_per_query
            )
            
            if result and 'rows' in result:
                week_rows = result.get('rows', 0)
                total_rows += week_rows
                weeks_processed.append(week_info['period'])
                logging.info(f"{week_info['period']}: {week_rows} filas")
            else:
                logging.warning(f"{week_info['period']} sin resultados")
            
            # Pequeña pausa entre semanas para no saturar
            time.sleep(2)
            
        except Exception as e:
            logging.error(f"Error en {week_info['period']}: {e}")
    
    return {
        'rows': total_rows,
        'weeks_processed': weeks_processed,
        'month': f"{year}-{month:02d}",
        'last_refresh': datetime.now(timezone.utc).isoformat()
    }
    
    
    
def get_date_range_for_fixed():
    """
    Obtiene el rango de fechas para Fixed: desde 2026-01-01 hasta 10 días antes de hoy
    """
    today = datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=10)
    start_date = date(2026, 1, 1)
    
    return start_date, cutoff

def get_dates_to_load():
    """
    Determina qué días faltan por cargar en Fixed
    Por ahora, como no tenemos metadata de días, cargamos todos
    """
    start_date, end_date = get_date_range_for_fixed()
    dates_to_load = []
    current_date = start_date
    
    while current_date <= end_date:
        dates_to_load.append(current_date)
        current_date += timedelta(days=1)
    
    logging.info(f"Total de días a cargar: {len(dates_to_load)} (desde {start_date} hasta {end_date})")
    return dates_to_load

def refresh_fixed_by_day(mysql_config, target_date=None, limit_per_day=500):
    """
    Refresca la base FIXED día por día
    """
    if refresh_fixed is None:
        logging.error("refresh_fixed no está disponible")
        return None
    
    if target_date:
        dates_to_load = [target_date]
    else:
        dates_to_load = get_dates_to_load()
    
    if not dates_to_load:
        return {'rows': 0, 'days_processed': [], 'message': 'No hay días para cargar'}
    
    logging.info(f"Iniciando carga de {len(dates_to_load)} días")
    
    total_rows = 0
    days_processed = []
    errors = []
    
    for i, day in enumerate(dates_to_load):
        try:
            day_str = day.strftime('%Y-%m-%d')
            logging.info(f"Cargando día {day_str} ({i+1}/{len(dates_to_load)})")
            
            # IMPORTANTE: QUITAR el "AND" extra porque refresh_fixed ya lo agrega
            # Solo pasamos la condición sin la palabra AND
            date_condition = f"f.FechaHora BETWEEN '{day_str} 00:00:00' AND '{day_str} 23:59:59'"
            
            result = refresh_fixed(
                mysql_config,
                QUERY_BASE,  # Pasamos la consulta base sin modificar
                start_iso=f"{day_str} 00:00:00",
                end_iso=f"{day_str} 23:59:59",
                limit=limit_per_day
            )
            
            if result and 'rows' in result:
                day_rows = result.get('rows', 0)
                total_rows += day_rows
                days_processed.append(day_str)
                
                if day_rows > 0:
                    logging.info(f"✅ Día {day_str}: {day_rows} filas")
                else:
                    logging.info(f"📭 Día {day_str}: sin datos")
            
            time.sleep(1)
            
        except Exception as e:
            error_msg = f"Error cargando día {day_str}: {e}"
            logging.error(error_msg)
            errors.append(error_msg)
    
    return {
        'rows': total_rows,
        'days_processed': days_processed,
        'errors': errors,
        'total_days': len(dates_to_load),
        'last_refresh': datetime.now(timezone.utc).isoformat()
    }
    
def background_refresh_task_daily():
    """
    Versión mejorada que carga día por día gradualmente
    """
    consecutive_errors = 0
    max_errors = 5
    
    # Esperar 1 minuto al inicio
    time.sleep(60)
    
    while True:
        try:
            now = datetime.now(timezone.utc)
            
            # REFRESCAR RECENT (cada 5 minutos)
            if refresh_recent is not None:
                try:
                    logging.info("Ejecutando refresco RECENT")
                    two_days_ago = (now - timedelta(days=2)).strftime('%Y-%m-%d')
                    today_end = now.strftime('%Y-%m-%d 23:59:59')
                    
                    recent_query = QUERY_BASE + f" AND f.FechaHora BETWEEN '{two_days_ago}' AND '{today_end}'"
                    
                    refresh_recent(DB_CONFIG, recent_query, limit=2000)
                    logging.info("✅ Refresco RECENT completado")
                    consecutive_errors = 0
                except Exception as e:
                    consecutive_errors += 1
                    logging.error(f"Error RECENT: {e}")
            
            # CARGAR FIXED DÍA POR DÍA (cada 30 minutos, 1 día a la vez)
            if now.minute % 30 == 0:  # Cada 30 minutos
                logging.info("Ejecutando carga incremental de FIXED (1 día)")
                try:
                    # Obtener días pendientes
                    all_dates = get_dates_to_load()
                    
                    # Aquí idealmente deberías verificar qué días ya cargaste
                    # Por ahora, cargamos el primer día pendiente
                    if all_dates:
                        # Por simplicidad, cargamos el día más antiguo pendiente
                        # En una versión futura, deberías guardar qué días ya cargaste
                        target_day = all_dates[0]
                        
                        result = refresh_fixed_by_day(DB_CONFIG, target_date=target_day, limit_per_day=500)
                        
                        if result and result.get('rows', 0) > 0:
                            logging.info(f"✅ Día {target_day} cargado: {result.get('rows')} filas")
                        else:
                            logging.info(f"📭 Día {target_day} sin datos")
                            
                except Exception as e:
                    logging.error(f"Error en carga incremental: {e}")
            
            # Manejo de errores consecutivos
            if consecutive_errors >= max_errors:
                logging.warning("Demasiados errores, esperando 30 minutos")
                time.sleep(1800)
                consecutive_errors = 0
            else:
                time.sleep(300)  # 5 minutos
            
        except Exception as e:
            logging.error(f"Error en tarea de fondo: {e}")
            time.sleep(60)

def start_background_refresh():
    """Inicia el nuevo sistema de carga diaria"""
    if refresh_recent is not None and refresh_fixed is not None:
        thread = threading.Thread(target=background_refresh_task_daily, daemon=True)
        thread.start()
        logging.info("✅ SISTEMA DE CARGA DIARIA INICIADO")
        logging.info("⏳ RECENT: cada 5 minutos")
        logging.info("⏳ FIXED: 1 día cada 30 minutos")
        logging.info("💡 Los días se cargarán gradualmente SIN TIMEOUTS")
    else:
        logging.warning("⚠️ Cache no disponible, no se inicia hilo de refresco")

# Inicializar bases de datos
if init_db is not None:
    try:
        init_db()
        logging.info("✅ Bases de datos SQLite inicializadas")
    except Exception as e:
        logging.error(f"Error inicializando bases de datos: {e}")

# ... (resto del código igual, desde get_mysql_conn hasta el final)

# Resto de funciones de conexión y formato (sin cambios significativos)
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

@app.teardown_appcontext
def close_connection(exception):
    conn = getattr(g, '_mysql_conn', None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass

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
                from decimal import Decimal
                if isinstance(v, Decimal):
                    out[cols[i]] = float(v)
                else:
                    out[cols[i]] = v
            except Exception:
                out[cols[i]] = str(v)
    return out

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

def default_date_range_for_yesterday():
    # Rango completo del día anterior
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    start = datetime.combine(yesterday, datetime.min.time())
    end = datetime.combine(yesterday, datetime.max.time())
    return start.strftime('%Y-%m-%d %H:%M:%S'), end.strftime('%Y-%m-%d %H:%M:%S')

@app.route('/api/ventas')
def api_ventas():
    """Ejecuta las consultas usando el rango de fechas y devuelve JSON."""
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

    # Opción: usar cache local (SQLite) con dos DBs: fixed + recent
    force = request.args.get('force_refresh')
    month = request.args.get('month')  # Para refrescar un mes específico
    rows = None
    
    # Si hay función de cache disponible
    if get_combined_rows is not None:
        # Forzar refresco según parámetro
        try:
            if force:
                if force.lower() == 'recent' and refresh_recent is not None:
                    logging.info('Forzando refresco RECENT')
                    refresh_recent(DB_CONFIG, QUERY_BASE)
                elif force.lower() == 'fixed' and refresh_fixed is not None:
                    if month:
                        logging.info(f'Forzando refresco FIXED para mes {month}')
                        refresh_fixed_by_month(DB_CONFIG, specific_month=month)
                    else:
                        logging.info('Forzando refresco FIXED completo (por meses)')
                        refresh_fixed_by_month(DB_CONFIG)
                else:
                    # cualquier otro valor intenta refrescar ambos
                    if refresh_recent is not None:
                        refresh_recent(DB_CONFIG, QUERY_BASE)
                    if refresh_fixed is not None:
                        refresh_fixed_by_month(DB_CONFIG)
        except Exception as e:
            logging.exception('Error refrescando cache: %s', e)

        # intentar leer filas combinadas (recent tiene precedencia)
        try:
            rows = get_combined_rows(start=start, end=end)
        except Exception as e:
            logging.exception('Error leyendo cache combinada: %s', e)

    # Si no hay cache o devolvió None/empty, caer de nuevo a consulta remota
    if not rows:
        conn = get_mysql_conn()
        cur = conn.cursor()
        try:
            # Usar la consulta base con filtro de fecha
            query_with_date = QUERY_BASE + f" AND f.FechaHora BETWEEN '{start}' AND '{end}'"
            cur.execute(query_with_date)
            rows = [format_row(cur, r) for r in cur.fetchall()]
            
            # Intentar poblar la cache en segundo plano (sin bloquear la respuesta)
            def background_update():
                try:
                    if refresh_recent is not None:
                        refresh_recent(DB_CONFIG, QUERY_BASE)
                except Exception as e:
                    logging.exception('Error en actualización background: %s', e)
            
            thread = threading.Thread(target=background_update, daemon=True)
            thread.start()
            
        finally:
            try:
                cur.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

    # Calcular suma de Totales por factura única
    unique_totals = {}
    seen = set()
    for r in rows:
        nf_raw = r.get('NumeroFactura')
        if nf_raw is None:
            continue
        nf = str(nf_raw).strip()
        if nf == '' or nf in seen:
            continue
        try:
            val = r.get('Total')
            if val is None:
                continue
            valf = float(val)
        except Exception:
            continue
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

@app.route('/api/cache/info')
def cache_info():
    """Endpoint para ver información del estado de la cache"""
    if get_cache_info is not None:
        try:
            info = get_cache_info()
            
            # Agregar información de meses disponibles
            months_info = get_month_queries()
            info['available_months'] = [m['month'] for m in months_info]
            
            return jsonify(info)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Cache no disponible'}), 404

@app.route('/api/cache/refresh/<db_type>')
def refresh_cache(db_type):
    """Endpoint para forzar refresco manual de la cache"""
    if db_type not in ['fixed', 'recent', 'both']:
        return jsonify({'error': 'Tipo inválido'}), 400
    
    month = request.args.get('month')  # Parámetro opcional para mes específico
    
    try:
        if db_type == 'recent' and refresh_recent is not None:
            result = refresh_recent(DB_CONFIG, QUERY_BASE)
            return jsonify({'status': 'ok', 'result': result})
        
        elif db_type == 'fixed' and refresh_fixed is not None:
            if month:
                result = refresh_fixed_by_month(DB_CONFIG, specific_month=month)
                return jsonify({'status': 'ok', 'month': month, 'result': result})
            else:
                result = refresh_fixed_by_month(DB_CONFIG)
                return jsonify({'status': 'ok', 'result': result})
        
        elif db_type == 'both':
            recent_result = refresh_recent(DB_CONFIG, QUERY_BASE) if refresh_recent else None
            fixed_result = refresh_fixed_by_month(DB_CONFIG) if refresh_fixed else None
            return jsonify({
                'status': 'ok', 
                'recent': recent_result,
                'fixed': fixed_result
            })
        else:
            return jsonify({'error': 'Función no disponible'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cache/months')
def list_months():
    """Lista todos los meses disponibles para consulta"""
    months = get_month_queries()
    return jsonify({
        'months': [{'month': m['month'], 'start': m['start'], 'end': m['end']} for m in months],
        'total': len(months)
    })


@app.route('/api/cache/rows')
def api_cache_rows():
    """Devuelve las filas combinadas desde las bases SQLite (fixed + recent).
    Parámetros opcionales: start, end (fechas en formato 'YYYY-MM-DD' o 'YYYY-MM-DD HH:MM:SS'), limit (int).
    """
    if get_combined_rows is None:
        return jsonify({'error': 'Cache no disponible'}), 404

    start = request.args.get('start')
    end = request.args.get('end')
    limit = request.args.get('limit', type=int)

    try:
        rows = get_combined_rows(start=start, end=end, limit=limit)
    except Exception as e:
        app.logger.exception('Error leyendo cache combinada: %s', e)
        return jsonify({'error': str(e)}), 500

    # Calcular suma de Totales por factura única (como hace /api/ventas)
    unique_totals = {}
    seen = set()
    for r in rows:
        nf_raw = r.get('NumeroFactura')
        if nf_raw is None:
            continue
        nf = str(nf_raw).strip()
        if nf == '' or nf in seen:
            continue
        try:
            val = r.get('Total')
            if val is None:
                continue
            valf = float(val)
        except Exception:
            continue
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


@app.route('/api/cache/refresh/fixed/weekly')
def refresh_fixed_weekly():
    """Endpoint para cargar FIXED por semanas (evita timeouts)"""
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    
    if not year or not month:
        return jsonify({'error': 'Se requiere year y month (ej: ?year=2026&month=1)'}), 400
    
    try:
        # Reducir límite a 200 para evitar timeouts
        result = refresh_fixed_by_week(DB_CONFIG, year, month, limit_per_query=200)
        return jsonify({'status': 'ok', 'result': result})
    except Exception as e:
        logging.error(f"Error en refresh semanal: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cache/refresh/fixed/all-months')
def refresh_fixed_all_months():
    """Carga todos los meses (enero, febrero, marzo) por semanas"""
    months_to_load = [
        (2026, 1),  # Enero
        (2026, 2),  # Febrero
        (2026, 3),  # Marzo
    ]
    
    results = []
    total_rows = 0
    
    for year, month in months_to_load:
        logging.info(f"\n{'='*50}")
        logging.info(f"CARGANDO MES: {year}-{month:02d}")
        logging.info(f"{'='*50}")
        
        try:
            result = refresh_fixed_by_week(DB_CONFIG, year, month, limit_per_query=200)
            if result:
                total_rows += result.get('rows', 0)
                results.append(result)
                logging.info(f"✅ Mes {year}-{month:02d} completado: {result.get('rows', 0)} filas")
            
            # Pausa entre meses
            time.sleep(5)
            
        except Exception as e:
            logging.error(f"Error cargando mes {year}-{month:02d}: {e}")
            results.append({'month': f"{year}-{month:02d}", 'error': str(e)})
    
    return jsonify({
        'status': 'ok',
        'total_rows': total_rows,
        'results': results
    })


# Funciones para manejo de archivos PDF (sin cambios)
def _find_best_file_match(nombre):
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

@app.route('/api/cache/refresh/fixed/day')
def refresh_fixed_day():
    """Carga un día específico (útil para pruebas)"""
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'error': 'Se requiere fecha (YYYY-MM-DD)'}), 400
    
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        result = refresh_fixed_by_day(DB_CONFIG, target_date=target_date)
        return jsonify({'status': 'ok', 'result': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cache/refresh/fixed/all-days')
def refresh_fixed_all_days():
    """FUERZA la carga de TODOS los días (puede tomar varios minutos)"""
    try:
        result = refresh_fixed_by_day(DB_CONFIG, target_date=None)
        return jsonify({'status': 'ok', 'result': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cache/status/days')
def cache_days_status():
    """Muestra el estado de los días pendientes"""
    try:
        start_date, end_date = get_date_range_for_fixed()
        total_days = (end_date - start_date).days + 1
        
        # Aquí podrías calcular días ya cargados si tuvieras metadata
        # Por ahora, mostramos solo el rango total
        
        return jsonify({
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'total_days': total_days,
            'estimated_time_minutes': total_days * 0.1,  # ~6 segundos por día
            'note': 'Usa /api/cache/refresh/fixed/all-days para cargar todos'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/file/view')
def file_view():
    nombre = request.args.get('nombre')
    if not nombre:
        abort(400, 'missing nombre')
    path = _find_best_file_match(nombre)
    if not path or not os.path.isfile(path):
        abort(404, 'file not found')
    try:
        return send_file(path, mimetype='application/pdf')
    except Exception:
        abort(500, 'error sending file')

@app.route('/file/download')
def file_download():
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
    # Iniciar el hilo de refresco en segundo plano
    start_background_refresh()
    
    # Ejecutar la aplicación
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)