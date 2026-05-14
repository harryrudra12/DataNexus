Write-Host "========================================="
Write-Host " Starting DataNexus Era 3 MVP"
Write-Host "========================================="

Set-Location "A:\datanexus-complete"

Write-Host ""
Write-Host "Starting PostgreSQL + FastAPI..."
docker compose -f docker-compose.mvp.yml -f docker-compose.db.yml up -d datanexus-db datanexus-api

Write-Host ""
Write-Host "Starting React Dashboard..."
docker compose -f docker-compose.react.yml up -d datanexus-react-ui

Write-Host ""
Write-Host "Waiting for services..."
Start-Sleep -Seconds 8

Write-Host ""
Write-Host "Container status:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

Write-Host ""
Write-Host "Validating APIs..."

try {
    Invoke-RestMethod -Uri "http://localhost:18000/api/v1/dashboard/demo/health-check" -Method GET -TimeoutSec 10
    Write-Host "API health check passed." -ForegroundColor Green
} catch {
    Write-Host "API health check failed." -ForegroundColor Red
}

try {
    Invoke-WebRequest -Uri "http://localhost:13001" -UseBasicParsing -TimeoutSec 10 | Out-Null
    Write-Host "React UI reachable." -ForegroundColor Green
} catch {
    Write-Host "React UI not reachable." -ForegroundColor Red
}

Write-Host ""
Write-Host "DataNexus is ready:"
Write-Host "React Dashboard : http://localhost:13001"
Write-Host "FastAPI Swagger : http://localhost:18000/docs"
Write-Host "Legacy UI       : http://localhost:13000"
Write-Host ""
