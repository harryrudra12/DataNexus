Write-Host "========================================="
Write-Host " Clean Restart DataNexus Era 3 MVP"
Write-Host "========================================="

Set-Location "A:\datanexus-complete"

Write-Host ""
Write-Host "Stopping React UI..."
docker compose -f docker-compose.react.yml down

Write-Host ""
Write-Host "Stopping API containers..."
docker compose -f docker-compose.mvp.yml -f docker-compose.db.yml stop datanexus-api

Write-Host ""
Write-Host "Rebuilding API..."
docker compose -f docker-compose.mvp.yml -f docker-compose.db.yml build datanexus-api

Write-Host ""
Write-Host "Starting DB + API..."
docker compose -f docker-compose.mvp.yml -f docker-compose.db.yml up -d datanexus-db datanexus-api

Write-Host ""
Write-Host "Rebuilding React UI..."
docker compose -f docker-compose.react.yml build --no-cache datanexus-react-ui

Write-Host ""
Write-Host "Starting React UI..."
docker compose -f docker-compose.react.yml up -d datanexus-react-ui

Write-Host ""
Write-Host "Waiting for services..."
Start-Sleep -Seconds 10

Write-Host ""
Write-Host "Running validation..."
.\validate_mvp.ps1

Write-Host ""
Write-Host "Open dashboard:"
Write-Host "http://localhost:13001"
