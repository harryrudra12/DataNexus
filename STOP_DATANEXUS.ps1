Write-Host "========================================="
Write-Host " Stopping DataNexus Era 3 MVP"
Write-Host "========================================="

Set-Location "A:\datanexus-complete"

Write-Host ""
Write-Host "Stopping React UI..."
docker compose -f docker-compose.react.yml down

Write-Host ""
Write-Host "Stopping API + DB..."
docker compose -f docker-compose.mvp.yml -f docker-compose.db.yml down

Write-Host ""
Write-Host "Current containers:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

Write-Host ""
Write-Host "DataNexus stopped."
