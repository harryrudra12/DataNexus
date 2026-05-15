Write-Host "========================================="
Write-Host " DataNexus MVP Validation"
Write-Host "========================================="

$ErrorActionPreference = "Continue"

function Test-Endpoint {
    param(
        [string]$Name,
        [string]$Url
    )

    Write-Host ""
    Write-Host "Checking: $Name"
    Write-Host "URL: $Url"

    try {
        $response = Invoke-RestMethod -Uri $Url -Method GET -TimeoutSec 15
        Write-Host "PASS: $Name" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "FAIL: $Name" -ForegroundColor Red
        Write-Host $_.Exception.Message
        return $false
    }
}

$checks = @()

$checks += Test-Endpoint "Dashboard Live API" "http://localhost:18000/api/v1/dashboard/live"
$checks += Test-Endpoint "Pipelines API" "http://localhost:18000/api/v1/dashboard/pipelines"
$checks += Test-Endpoint "Audit API" "http://localhost:18000/api/v1/dashboard/audit/recent"
$checks += Test-Endpoint "Compliance API" "http://localhost:18000/api/v1/dashboard/compliance/summary"
$checks += Test-Endpoint "Demo Validation API" "http://localhost:18000/api/v1/dashboard/demo/validation"
$checks += Test-Endpoint "Demo Health Check API" "http://localhost:18000/api/v1/dashboard/demo/health-check"
$checks += Test-Endpoint "Pipeline Runs API" "http://localhost:18000/api/v1/dashboard/pipeline-runs/recent"

Write-Host ""
Write-Host "Testing Audit PDF download..."

try {
    Invoke-WebRequest `
        -Uri "http://localhost:18000/api/v1/dashboard/reports/audit.pdf" `
        -OutFile ".\validation_audit_report.pdf" `
        -TimeoutSec 30

    if (Test-Path ".\validation_audit_report.pdf") {
        Write-Host "PASS: Audit PDF downloaded" -ForegroundColor Green
        $checks += $true
    } else {
        Write-Host "FAIL: Audit PDF file not found after download" -ForegroundColor Red
        $checks += $false
    }
} catch {
    Write-Host "FAIL: Audit PDF download" -ForegroundColor Red
    Write-Host $_.Exception.Message
    $checks += $false
}

Write-Host ""
Write-Host "Testing React UI..."

try {
    Invoke-WebRequest `
        -Uri "http://localhost:13001" `
        -UseBasicParsing `
        -TimeoutSec 15 | Out-Null

    Write-Host "PASS: React UI reachable" -ForegroundColor Green
    $checks += $true
} catch {
    Write-Host "FAIL: React UI not reachable" -ForegroundColor Red
    Write-Host $_.Exception.Message
    $checks += $false
}

$passed = ($checks | Where-Object { $_ -eq $true }).Count
$total = $checks.Count

if ($total -gt 0) {
    $score = [math]::Round(($passed / $total) * 100, 1)
} else {
    $score = 0
}

Write-Host ""
Write-Host "========================================="
Write-Host " Validation Result"
Write-Host "========================================="
Write-Host "Passed: $passed / $total"
Write-Host "Score : $score%"

if ($passed -eq $total) {
    Write-Host "STATUS: DEMO READY" -ForegroundColor Green
} elseif ($score -ge 80) {
    Write-Host "STATUS: MOSTLY READY" -ForegroundColor Yellow
} else {
    Write-Host "STATUS: NEEDS FIX" -ForegroundColor Red
}

Write-Host ""
Write-Host "Useful URLs:"
Write-Host "React Dashboard : http://localhost:13001"
Write-Host "FastAPI Swagger : http://localhost:18000/docs"
Write-Host "Legacy UI       : http://localhost:13000"

