import sqlite3
import json
from datetime import datetime
import os

def ver_base(db_name, titulo):
    """Función para visualizar el contenido de una base SQLite"""
    print(f"\n{'='*60}")
    print(f"📁 {titulo}")
    print(f"📄 Archivo: {db_name}")
    print('='*60)
    
    if not os.path.exists(db_name):
        print(f"❌ El archivo {db_name} no existe aún")
        return
    
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row  # Para acceder por nombre de columna
    
    try:
        # Ver metadata
        cur = conn.cursor()
        cur.execute("SELECT * FROM metadata")
        meta = cur.fetchall()
        print("\n📊 METADATA:")
        if meta:
            for key, value in meta:
                try:
                    data = json.loads(value)
                    print(f"  🔑 {key}:")
                    if isinstance(data, dict):
                        for k, v in data.items():
                            print(f"     • {k}: {v}")
                    else:
                        print(f"     {data}")
                except:
                    print(f"  🔑 {key}: {value}")
        else:
            print("  No hay metadata aún")
        
        # Ver estructura de la tabla
        cur.execute("PRAGMA table_info(ventas)")
        columnas = cur.fetchall()
        print(f"\n📋 COLUMNAS ({len(columnas)}):")
        for col in columnas[:5]:  # Mostrar solo primeras 5 columnas para no saturar
            print(f"  • {col['name']} ({col['type']})")
        if len(columnas) > 5:
            print(f"  ... y {len(columnas)-5} columnas más")
        
        # Ver total de registros
        cur.execute("SELECT COUNT(*) as total FROM ventas")
        total = cur.fetchone()['total']
        print(f"\n📈 TOTAL REGISTROS: {total:,}")
        
        if total > 0:
            # Ver distribución por mes (si hay campo Fecha)
            try:
                cur.execute("""
                    SELECT substr(Fecha, 1, 7) as mes, COUNT(*) as cantidad 
                    FROM ventas 
                    WHERE Fecha IS NOT NULL 
                    GROUP BY substr(Fecha, 1, 7) 
                    ORDER BY mes DESC
                    LIMIT 5
                """)
                meses = cur.fetchall()
                if meses:
                    print("\n📅 ÚLTIMOS MESES:")
                    for mes in meses:
                        print(f"  • {mes['mes']}: {mes['cantidad']:,} registros")
            except:
                pass
            
            # Ver primeras filas (ejemplo)
            cur.execute("SELECT * FROM ventas LIMIT 3")
            filas = cur.fetchall()
            print(f"\n🔍 PRIMERAS 3 FACTURAS:")
            for i, fila in enumerate(filas, 1):
                print(f"\n  --- FACTURA {i} ---")
                # Mostrar campos más importantes
                print(f"     N° Factura: {fila['NumeroFactura']}")
                print(f"     Cliente: {fila['NumeroDocumentoCliente']}")
                print(f"     Producto: {str(fila['NombreProducto'])[:50]}...")
                print(f"     Total: ${fila['Total']:,.0f}")
                print(f"     Fecha: {fila['Fecha']}")
    
    except Exception as e:
        print(f"❌ Error leyendo base de datos: {e}")
    
    finally:
        conn.close()

def ver_todo():
    """Ver todas las bases de datos"""
    print("\n" + "★"*60)
    print("🌟  VISOR DE CACHE - VENTAS ESPECIALES  🌟")
    print("★"*60)
    
    # Ver base FIXED (histórica)
    ver_base("cache_fixed.db", "BASE HISTÓRICA (FIXED) - Ene 2026 hasta 10 días antes")
    
    # Ver base RECENT (reciente)
    ver_base("cache_recent.db", "BASE RECIENTE (RECENT) - Últimos 10 días")
    
    print("\n" + "★"*60)
    print("✅ Para actualizar esta información, ejecuta el script nuevamente")
    print("💡 Si las bases están vacías, espera unos minutos mientras se llenan")
    print("★"*60)

def ver_resumen_rapido():
    """Versión resumida para ver rápido"""
    print("\n📊 RESUMEN RÁPIDO:")
    print("-" * 40)
    
    for db_name in ["cache_fixed.db", "cache_recent.db"]:
        if os.path.exists(db_name):
            conn = sqlite3.connect(db_name)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM ventas")
            total = cur.fetchone()[0]
            
            # Última actualización
            cur.execute("SELECT value FROM metadata WHERE key='last_refresh'")
            meta = cur.fetchone()
            if meta:
                try:
                    data = json.loads(meta[0])
                    fecha = data.get('ts', 'desconocida')[:19]
                except:
                    fecha = 'desconocida'
            else:
                fecha = 'nunca'
            
            tipo = "📁 FIXED" if "fixed" in db_name else "🗄️ RECENT"
            print(f"{tipo}: {total:>10,} registros (última act: {fecha})")
            conn.close()
        else:
            print(f"⚠️  {db_name}: no existe")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--resumen":
        ver_resumen_rapido()
    else:
        ver_todo()