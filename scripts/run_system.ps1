# scripts/run_system.ps1 - Start the complete AI Trading System

Write-Host "🚀 Starting AI Trading System..." -ForegroundColor Green
Write-Host "==================================" -ForegroundColor Cyan

# Check if virtual environment exists
if (-Not (Test-Path "ai_trading_env")) {
    Write-Host "❌ Virtual environment not found. Run setup_project.ps1 first." -ForegroundColor Red
    exit 1
}

# Activate virtual environment
Write-Host "`n🔓 Activating virtual environment..." -ForegroundColor Yellow
& .\ai_trading_env\Scripts\Activate.ps1

# Check if Docker services are running
Write-Host "`n🐳 Checking Docker services..." -ForegroundColor Yellow
$services = docker-compose -f docker/compose/docker-compose.dev.yml ps --services --filter "status=running"
if ($services.Count -lt 2) {
    Write-Host "⚠️  Starting Docker services..." -ForegroundColor Magenta
    docker-compose -f docker/compose/docker-compose.dev.yml up -d
    Start-Sleep -Seconds 5
}

# Start Market Data Agent
Write-Host "`n📊 Starting Market Data Agent..." -ForegroundColor Yellow
$marketDataJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    & .\ai_trading_env\Scripts\Activate.ps1
    python -m src.market_data.market_data_agent
}

# Start Regime Analysis Dashboard
Write-Host "`n📈 Starting Regime Analysis Dashboard..." -ForegroundColor Yellow
$regimeAnalysisJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    & .\ai_trading_env\Scripts\Activate.ps1
    python -m scripts.analyze_regimes
}

# Start Monitoring (if enabled)
Write-Host "`n🔍 Starting System Monitoring..." -ForegroundColor Yellow
$monitoringJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    & .\ai_trading_env\Scripts\Activate.ps1
    python -m src.monitoring.health_check
}

Write-Host "`n✅ AI Trading System components started!" -ForegroundColor Green
Write-Host "`n📊 Running Services:" -ForegroundColor Cyan
Write-Host "  - Market Data Agent (Job ID: $($marketDataJob.Id))" -ForegroundColor White
Write-Host "  - Regime Analysis (Job ID: $($regimeAnalysisJob.Id))" -ForegroundColor White
Write-Host "  - System Monitoring (Job ID: $($monitoringJob.Id))" -ForegroundColor White

Write-Host "`n🌐 Access Points:" -ForegroundColor Cyan
Write-Host "  - Grafana Dashboard: http://localhost:3000" -ForegroundColor White
Write-Host "  - Redis Commander: http://localhost:8081" -ForegroundColor White
Write-Host "  - TimescaleDB: localhost:5432" -ForegroundColor White

Write-Host "`n⏹️  To stop the system:" -ForegroundColor Yellow
Write-Host "  - Press Ctrl+C to stop all components" -ForegroundColor White
Write-Host "  - Or run: .\scripts\stop_system.ps1" -ForegroundColor White

try {
    # Wait for user interrupt
    Write-Host "`n⏳ System running... Press Ctrl+C to stop" -ForegroundColor Green
    while ($true) {
        Start-Sleep -Seconds 1
    }
}
finally {
    Write-Host "`n🛑 Stopping AI Trading System..." -ForegroundColor Yellow
    
    # Stop all jobs
    $marketDataJob, $regimeAnalysisJob, $monitoringJob | Stop-Job -PassThru | Remove-Job -Force
    
    Write-Host "✅ System stopped successfully!" -ForegroundColor Green
}