# scripts/git_setup.ps1 - Git repository initialization and setup

Write-Host "🚀 Setting up Git version control for AI Trading System..." -ForegroundColor Green

# Initialize Git repository if not exists
if (-Not (Test-Path ".git")) {
    Write-Host "Initializing new Git repository..." -ForegroundColor Yellow
    git init
}

# Configure Git
Write-Host "Configuring Git settings..." -ForegroundColor Yellow
git config user.name "AI Trading System"
git config user.email "trading@ai-system.com"
git config core.autocrlf false
git config core.safecrlf true

# Create main branch
Write-Host "Creating main branch structure..." -ForegroundColor Yellow
git checkout -b main

# Add all files
Write-Host "Adding files to Git..." -ForegroundColor Yellow
git add .

# Initial commit
Write-Host "Creating initial commit..." -ForegroundColor Yellow
git commit -m "feat: Initial AI Trading System implementation

- Core market data ingestion with regime detection
- Unified feature store with Redis and TimescaleDB
- NNFX strategy with adaptive regime handling
- Comprehensive testing suite
- Docker development environment
- Monitoring and analytics framework"

Write-Host "✅ Git repository setup completed!" -ForegroundColor Green
Write-Host "📊 Next steps:" -ForegroundColor Cyan
Write-Host "  1. Connect to remote repository: git remote add origin <your-repo-url>"
Write-Host "  2. Push to remote: git push -u origin main"
Write-Host "  3. Create development branch: git checkout -b develop"