import sqlite3

# Conectar a la base FIXED
conn = sqlite3.connect('cache_fixed.db')
cursor = conn.cursor()

# Contar total de registros
cursor.execute("SELECT COUNT(*) FROM ventas")
total = cursor.fetchone()[0]

print(f"📊 TOTAL REGISTROS EN FIXED: {total}")

# Ver distribución por fecha (opcional)
cursor.execute("""
    SELECT substr(Fecha, 1, 10) as dia, COUNT(*) 
    FROM ventas 
    GROUP BY substr(Fecha, 1, 10) 
    ORDER BY dia
""")
print("\n📅 Distribución por día:")
for dia, count in cursor.fetchall():
    print(f"  {dia}: {count} registros")

conn.close()