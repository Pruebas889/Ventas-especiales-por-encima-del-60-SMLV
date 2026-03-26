Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "CARGA COMPLETA DE DATOS 2026-01-01 AL 2026-03-16" -ForegroundColor Cyan
Write-Host "(FIXED: hasta 10 dias antes de hoy - 26/03/2026)" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "ANTES DE CONTINUAR:" -ForegroundColor Yellow
Write-Host "1. Deten la aplicacion (Ctrl+C)" -ForegroundColor White
Write-Host "2. Elimina manualmente los archivos:" -ForegroundColor White
Write-Host "   - cache_fixed.db" -ForegroundColor White
Write-Host "   - cache_recent.db" -ForegroundColor White
Write-Host "3. Vuelve a ejecutar: python ventasespeciales.py" -ForegroundColor White
Write-Host ""
Write-Host "Presiona Enter cuando hayas hecho esto..." -ForegroundColor Green
Read-Host

# Verificar que la aplicación esté corriendo
Write-Host "`nVerificando servidor..." -ForegroundColor Yellow
try {
    $test = Invoke-WebRequest -Uri "http://localhost:5050/api/cache/status/days" -UseBasicParsing -TimeoutSec 5
    Write-Host "  Servidor OK" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: No se puede conectar al servidor" -ForegroundColor Red
    Write-Host "  Asegurate que ventasespeciales.py este corriendo" -ForegroundColor Red
    exit 1
}

# Mes: Enero 2026
Write-Host "`n--- ENERO 2026 ---" -ForegroundColor Magenta
for ($dia = 1; $dia -le 31; $dia++) {
    $fecha = "2026-01-{0:D2}" -f $dia
    Write-Host "Cargando $fecha..." -NoNewline
    $response = Invoke-WebRequest -Uri "http://localhost:5050/api/cache/refresh/fixed/day?date=$fecha" -UseBasicParsing
    $result = $response.Content | ConvertFrom-Json
    Write-Host " $($result.result.rows) registros" -ForegroundColor Green
    Start-Sleep -Seconds 1
}

# Mes: Febrero 2026
Write-Host "`n--- FEBRERO 2026 ---" -ForegroundColor Magenta
for ($dia = 1; $dia -le 28; $dia++) {
    $fecha = "2026-02-{0:D2}" -f $dia
    Write-Host "Cargando $fecha..." -NoNewline
    $response = Invoke-WebRequest -Uri "http://localhost:5050/api/cache/refresh/fixed/day?date=$fecha" -UseBasicParsing
    $result = $response.Content | ConvertFrom-Json
    Write-Host " $($result.result.rows) registros" -ForegroundColor Green
    Start-Sleep -Seconds 1
}

# Mes: Marzo 2026 (hasta el 16 de marzo - corte FIXED)
Write-Host "`n--- MARZO 2026 (HASTA DIA 16 - CORTE FIXED) ---" -ForegroundColor Magenta
for ($dia = 1; $dia -le 16; $dia++) {
    $fecha = "2026-03-{0:D2}" -f $dia
    Write-Host "Cargando $fecha..." -NoNewline
    $response = Invoke-WebRequest -Uri "http://localhost:5050/api/cache/refresh/fixed/day?date=$fecha" -UseBasicParsing
    $result = $response.Content | ConvertFrom-Json
    Write-Host " $($result.result.rows) registros" -ForegroundColor Green
    Start-Sleep -Seconds 1
}

# Opcional: Los días 17-26 los manejará RECENT automáticamente
Write-Host "`n--- NOTA ---" -ForegroundColor Cyan
Write-Host "Los días 17 al 26 de marzo seran manejados por RECENT automaticamente" -ForegroundColor Yellow
Write-Host "(cada 5 minutos se actualiza con los ultimos 2 dias)" -ForegroundColor Yellow

# Verificar resultados
Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host "VERIFICANDO RESULTADOS" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

python ver_cache.py --resumen

Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host "CARGA COMPLETADA" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan