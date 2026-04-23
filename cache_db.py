import sqlite3
import os
from pathlib import Path
from datetime import datetime, date, timedelta, timezone
import json
import re

# Two separate sqlite databases: fixed (historical stable) and recent (last 10 days volatile)
FIXED_DB = 'cache_fixed.db'
RECENT_DB = 'cache_recent.db'

def _db_path(name):
    return Path(__file__).parent.joinpath(name)

def init_db():
    """Create both DB files and basic tables if missing."""
    for fname in (FIXED_DB, RECENT_DB):
        p = _db_path(fname)
        conn = sqlite3.connect(str(p))
        try:
            cur = conn.cursor()
            cur.execute('''
            CREATE TABLE IF NOT EXISTS ventas (
                IDComercial TEXT,
                NumeroFactura TEXT,
                NumeroDocumentoCliente TEXT,
                Apellidos TEXT,
                Nombres TEXT,
                Refe TEXT,
                NombreProducto TEXT,
                CantidadUnidades REAL,
                CantidadFracciones REAL,
                ValorDescuento REAL,
                ValorTotal REAL,
                Total REAL,
                TipoVentaDescripcion TEXT,
                Fecha TEXT,
                NombreFactura TEXT
            )
            ''')
            
            cur.execute('''
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            ''')
            conn.commit()
        finally:
            conn.close()

def _set_meta(dbname, key, value):
    p = _db_path(dbname)
    conn = sqlite3.connect(str(p))
    try:
        cur = conn.cursor()
        cur.execute('REPLACE INTO metadata(key,value) VALUES(?,?)', (key, json.dumps(value)))
        conn.commit()
    finally:
        conn.close()

def _get_meta(dbname, key):
    p = _db_path(dbname)
    conn = sqlite3.connect(str(p))
    try:
        cur = conn.cursor()
        cur.execute('SELECT value FROM metadata WHERE key=?', (key,))
        r = cur.fetchone()
        if not r:
            return None
        return json.loads(r[0])
    finally:
        conn.close()

def _append_date_condition(query, start_iso, end_iso):
    q = query.strip()
    has_where = re.search(r'\bWHERE\b', q, flags=re.I) is not None
    cond = f"f.FechaHora BETWEEN '{start_iso}' AND '{end_iso}'"
    if has_where:
        q = q.rstrip(';') + f' AND {cond};'
    else:
        q = q.rstrip(';') + f' WHERE {cond};'
    return q

def refresh_fixed(mysql_config, base_query, limit=None, start_iso=None, end_iso=None):
    """Refresh historical (fixed) DB from Jan 1 up to cutoff (10 days before today)."""
    try:
        import mysql.connector
    except Exception as e:
        raise RuntimeError('mysql-connector-python no está instalado') from e

    # compute date range
    today = datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=10)
    if not start_iso:
        start_dt = datetime(cutoff.year, 1, 1, 0, 0, 0) if cutoff.year == today.year else datetime(today.year, 1, 1, 0, 0, 0)
        start_iso = start_dt.strftime('%Y-%m-%d %H:%M:%S')
    if not end_iso:
        end_dt = datetime.combine(cutoff, datetime.max.time())
        end_iso = end_dt.strftime('%Y-%m-%d %H:%M:%S')

    q = _append_date_condition(base_query, start_iso, end_iso)
    if limit is not None:
        q = q.rstrip(';') + f' LIMIT {int(limit)};'

    p = _db_path(FIXED_DB)
    conn_sqlite = sqlite3.connect(str(p))
    try:
        cur_sqlite = conn_sqlite.cursor()

        conn_mysql = mysql.connector.connect(
            host=mysql_config['host'],
            user=mysql_config['user'],
            password=mysql_config['password'],
            database=mysql_config['database'],
            port=mysql_config.get('port', 3306),
            charset='utf8mb4'
        )
        cur_mysql = conn_mysql.cursor()
        cur_mysql.execute(q)
        cols = [d[0] for d in cur_mysql.description]
        rows = cur_mysql.fetchall()

        # Eliminar solo los datos del rango específico
        if start_iso and end_iso:
            cur_sqlite.execute('DELETE FROM ventas WHERE Fecha BETWEEN ? AND ?', (start_iso, end_iso))
        else:
            cur_sqlite.execute('DELETE FROM ventas')
    
        insert_sql = 'INSERT INTO ventas VALUES (' + ','.join('?' for _ in cols) + ')'
        norm_rows = []
        for r in rows:
            nr = []
            for v in r:
                if v is None:
                    nr.append(None)
                else:
                    try:
                        if isinstance(v, datetime):
                            nr.append(v.isoformat()); continue
                    except Exception:
                        pass
                    try:
                        from decimal import Decimal
                        if isinstance(v, Decimal):
                            nr.append(float(v)); continue
                    except Exception:
                        pass
                    nr.append(v)
            norm_rows.append(tuple(nr))

        if norm_rows:
            cur_sqlite.executemany(insert_sql, norm_rows)
        conn_sqlite.commit()
        _set_meta(FIXED_DB, 'last_refresh', {'ts': datetime.now(timezone.utc).isoformat(), 'rows': len(norm_rows), 'range': (start_iso, end_iso)})
        return {'rows': len(norm_rows), 'last_refresh': _get_meta(FIXED_DB, 'last_refresh')}
    finally:
        try: cur_mysql.close()
        except Exception: pass
        try: conn_mysql.close()
        except Exception: pass
        try: conn_sqlite.close()
        except Exception: pass

def refresh_recent(mysql_config, base_query, limit=None, start_iso=None, end_iso=None):
    """Refresh recent DB covering last 10 days up to today."""
    try:
        import mysql.connector
    except Exception as e:
        raise RuntimeError('mysql-connector-python no está instalado') from e

    today = datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=10)
    recent_start = cutoff + timedelta(days=1)
    if not start_iso:
        start_iso = datetime.combine(recent_start, datetime.min.time()).strftime('%Y-%m-%d %H:%M:%S')
    if not end_iso:
        end_iso = datetime.combine(today, datetime.max.time()).strftime('%Y-%m-%d %H:%M:%S')

    q = _append_date_condition(base_query, start_iso, end_iso)
    if limit is not None:
        q = q.rstrip(';') + f' LIMIT {int(limit)};'

    p = _db_path(RECENT_DB)
    conn_sqlite = sqlite3.connect(str(p))
    try:
        cur_sqlite = conn_sqlite.cursor()

        conn_mysql = mysql.connector.connect(
            host=mysql_config['host'],
            user=mysql_config['user'],
            password=mysql_config['password'],
            database=mysql_config['database'],
            port=mysql_config.get('port', 3306),
            charset='utf8mb4'
        )
        cur_mysql = conn_mysql.cursor()
        cur_mysql.execute(q)
        cols = [d[0] for d in cur_mysql.description]
        rows = cur_mysql.fetchall()

        # Eliminar solo los datos del rango específico (igual que en refresh_fixed)
        if start_iso and end_iso:
            cur_sqlite.execute('DELETE FROM ventas WHERE Fecha BETWEEN ? AND ?', (start_iso, end_iso))
        else:
            cur_sqlite.execute('DELETE FROM ventas')
    
        insert_sql = 'INSERT INTO ventas VALUES (' + ','.join('?' for _ in cols) + ')'
        norm_rows = []
        for r in rows:
            nr = []
            for v in r:
                if v is None:
                    nr.append(None)
                else:
                    try:
                        if isinstance(v, datetime):
                            nr.append(v.isoformat()); continue
                    except Exception:
                        pass
                    try:
                        from decimal import Decimal
                        if isinstance(v, Decimal):
                            nr.append(float(v)); continue
                    except Exception:
                        pass
                    nr.append(v)
            norm_rows.append(tuple(nr))

        if norm_rows:
            cur_sqlite.executemany(insert_sql, norm_rows)
        conn_sqlite.commit()
        _set_meta(RECENT_DB, 'last_refresh', {'ts': datetime.now(timezone.utc).isoformat(), 'rows': len(norm_rows), 'range': (start_iso, end_iso)})
        return {'rows': len(norm_rows), 'last_refresh': _get_meta(RECENT_DB, 'last_refresh')}
    finally:
        try: cur_mysql.close()
        except Exception: pass
        try: conn_mysql.close()
        except Exception: pass
        try: conn_sqlite.close()
        except Exception: pass

def get_combined_rows(start=None, end=None, limit=None):
    """Devuelve filas combinadas de recent (preferido) y fixed."""
    init_db()
    def _read_db(dbname):
        p = _db_path(dbname)
        conn = sqlite3.connect(str(p))
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            q = 'SELECT * FROM ventas'
            params = []
            if start and end:
                # Si son fechas sin hora (YYYY-MM-DD), añadir hora inicio y fin
                start_param = start if 'T' in start or ' ' in start else start + ' 00:00:00'
                end_param = end if 'T' in end or ' ' in end else end + ' 23:59:59'
                q += ' WHERE Fecha BETWEEN ? AND ?'
                params.extend([start_param, end_param])
            elif start:
                start_param = start if 'T' in start or ' ' in start else start + ' 00:00:00'
                q += ' WHERE Fecha >= ?'
                params.append(start_param)
            elif end:
                end_param = end if 'T' in end or ' ' in end else end + ' 23:59:59'
                q += ' WHERE Fecha <= ?'
                params.append(end_param)
            q += ' ORDER BY Fecha ASC'
            cur.execute(q, params)
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def _row_key(r):
        return (
            str(r.get('NumeroFactura') or '').strip(),
            str(r.get('Refe') or '').strip(),
            str(r.get('CantidadUnidades') or '').strip(),
            str(r.get('CantidadFracciones') or '').strip(),
            str(r.get('ValorTotal') or '').strip()
        )

    combined = []
    seen_keys = set()

    # Agregar filas recientes primero (tienen prioridad si hay solapamiento)
    recent_rows = _read_db(RECENT_DB)
    for r in recent_rows:
        k = _row_key(r)
        if k in seen_keys:
            continue
        seen_keys.add(k)
        combined.append(r)

    fixed_rows = _read_db(FIXED_DB)
    for r in fixed_rows:
        k = _row_key(r)
        if k in seen_keys:
            continue
        seen_keys.add(k)
        combined.append(r)
    try:
        combined.sort(key=lambda x: x.get('Fecha') or '')
    except Exception:
        pass

    if limit:
        combined = combined[:int(limit)]
    return combined

def get_cache_info():
    init_db()
    return {'fixed': _get_meta(FIXED_DB, 'last_refresh'), 'recent': _get_meta(RECENT_DB, 'last_refresh')}