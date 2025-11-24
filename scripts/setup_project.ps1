# scripts/setup_project.ps1 - Complete project setup script

Write-Host "🚀 AI Trading System - Complete Project Setup" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Cyan

# Check Python installation
Write-Host "`n🔍 Checking Python installation..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "   Please install Python 3.8 or higher from https://python.org" -ForegroundColor Yellow
    exit 1
}
Write-Host "✅ Python found: $pythonVersion" -ForegroundColor Green

# Check Docker installation
Write-Host "`n🐳 Checking Docker installation..." -ForegroundColor Yellow
$dockerVersion = docker --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Docker is not installed or not running" -ForegroundColor Red
    Write-Host "   Please install Docker Desktop from https://docker.com" -ForegroundColor Yellow
    exit 1
}
Write-Host "✅ Docker found: $dockerVersion" -ForegroundColor Green

# Create virtual environment
Write-Host "`n📦 Creating Python virtual environment..." -ForegroundColor Yellow
if (Test-Path "ai_trading_env") {
    Write-Host "⚠️  Virtual environment already exists, recreating..." -ForegroundColor Magenta
    Remove-Item -Recurse -Force ai_trading_env
}
python -m venv ai_trading_env

# Activate virtual environment
Write-Host "`n🔓 Activating virtual environment..." -ForegroundColor Yellow
& .\ai_trading_env\Scripts\Activate.ps1

# Upgrade pip and install dependencies
Write-Host "`n📥 Installing project dependencies..." -ForegroundColor Yellow
python -m pip install --upgrade pip
pip install -r requirements.txt

# Install TA-Lib (Windows specific)
Write-Host "`n📊 Installing TA-Lib (this may take a moment)..." -ForegroundColor Yellow
try {
    pip install ta-lib
    Write-Host "✅ TA-Lib installed successfully" -ForegroundColor Green
}
catch {
    Write-Host "⚠️  TA-Lib installation failed, trying alternative..." -ForegroundColor Yellow
    pip install TA-Lib
}

# Start Docker services
Write-Host "`n🐳 Starting Docker services (TimescaleDB, Redis)..." -ForegroundColor Yellow
docker-compose -f docker/compose/docker-compose.dev.yml up -d

# Wait for services to be ready
Write-Host "`n⏳ Waiting for services to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Initialize database
Write-Host "`n🗄️  Initializing TimescaleDB..." -ForegroundColor Yellow
try {
    # You might need to adjust connection parameters based on your docker-compose
    $env:PGPASSWORD="password"
    psql -h localhost -U postgres -d ai_trading_db -f src/database/timescaledb_setup.sql
    Write-Host "✅ Database initialized successfully" -ForegroundColor Green
}
catch {
    Write-Host "⚠️  Manual database setup required:" -ForegroundColor Yellow
    Write-Host "   Run: psql -h localhost -U postgres -d ai_trading_db -f src/database/timescaledb_setup.sql" -ForegroundColor White
}

# Run tests
Write-Host "`n🧪 Running test suite..." -ForegroundColor Yellow
python -m pytest tests/ -v --tb=short

# Setup Git
Write-Host "`n🔧 Setting up Git version control..." -ForegroundColor Yellow
& .\scripts\git_setup.ps1

Write-Host "`n🎉 AI Trading System setup completed successfully!" -ForegroundColor Green
Write-Host "`n📚 Next steps:" -ForegroundColor Cyan
Write-Host "  1. Configure environment variables in .env file" -ForegroundColor White
Write-Host "  2. Run the system: .\scripts\run_system.ps1" -ForegroundColor White
Write-Host "  3. View monitoring: http://localhost:3000 (Grafana)" -ForegroundColor White
Write-Host "  4. Check logs: docker-compose logs -f" -ForegroundColor White
Write-Host "`n💡 Development workflow:" -ForegroundColor Cyan
Write-Host "  - Use: .\scripts\git_workflow.ps1 -FeatureName 'your-feature' -CommitMessage 'description'" -ForegroundColor White
Write-Host "  - Run tests: .\scripts\run_tests.ps1" -ForegroundColor White
Write-Host "  - Code quality: .\scripts\code_quality.ps1" -ForegroundColor White