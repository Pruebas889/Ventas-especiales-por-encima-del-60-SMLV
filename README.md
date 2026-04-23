# Ventas Especiales

Pequeña app Flask que muestra una página "Ventas Especiales" y consulta una base MySQL remota para devolver dos reportes: `rechazados` y `general`.

Requisitos
- Python 3.8+
- Instalar dependencias: `pip install -r requirements.txt`

Ejecutar (Windows PowerShell):

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python ventasespeciales.py
```

La app servirá en http://localhost:5050. La API está en `/api/ventas` y acepta parámetros opcionales `start` y `end` (formato `YYYY-MM-DD` o `YYYY-MM-DD HH:MM:SS`).

Notas
- El archivo `ventasespeciales.py` contiene la configuración `DB_CONFIG` con las credenciales/host proporcionadas. Si prefieres no almacenar credenciales en el código, usa variables de entorno o un archivo de configuración.
- `create_db.py` crea una base SQLite local de ejemplo; la app principal está configurada para usar MySQL remoto.
# Ventas Especiales

Pequeña aplicación Flask que muestra una página estilizada "Ventas Especiales" y una API que devuelve las ofertas desde una base de datos SQLite.

Pasos rápidos:

1. Crear y activar un entorno virtual (opcional pero recomendado):

```powershell
python -m venv .venv; .\.venv\Scripts\Activate
```

2. Instalar dependencias:

```powershell
pip install -r requirements.txt
```

3. Crear la base de datos de ejemplo:

```powershell
python create_db.py
```

4. Ejecutar la app:

```powershell
python ventasespeciales.py
```

Abrir en el navegador: http://127.0.0.1:5050

Notas:
- La app usa `ventas.db` en el mismo directorio. El script `create_db.py` crea una tabla `ventas` y agrega filas de ejemplo.
- La página carga los datos cada 10 segundos y permite actualizar manualmente.
