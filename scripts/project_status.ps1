# scripts/project_status.ps1 - Comprehensive project status report

function Write-ColorOutput {
    param([string]$Message, [string]$Color = "White")
    Write-Host $Message -ForegroundColor $Color
}

function Test-Component {
    param([string]$Component, [string]$TestCommand, [string]$SuccessMessage, [string]$FailureMessage)
    
    try {
        Invoke-Expression $TestCommand | Out-Null
        Write-ColorOutput "  ✅ $SuccessMessage" "Green"
        return $true
    } catch {
        Write-ColorOutput "  ❌ $FailureMessage" "Red"
        Write-ColorOutput "     Error: $($_.Exception.Message)" "Gray"
        return $false
    }
}

Write-ColorOutput "`n🔍 AI Trading System - Project Status Report" "Green"
Write-ColorOutput "=============================================" "Cyan"
Write-ColorOutput "Generated: $(Get-Date)" "White"
Write-ColorOutput "Project: $(Split-Path (Get-Location) -Leaf)" "White"

# Git Status
Write-ColorOutput "`n📊 Git Status:" "Cyan"
$branch = git branch --show-current 2>$null
$commit = git log --oneline -1 2>$null
$changes = git status --porcelain 2>$null

if ($branch) {
    Write-ColorOutput "  Branch: $branch" "White"
    Write-ColorOutput "  Latest Commit: $commit" "White"
    
    if ($changes) {
        Write-ColorOutput "  Uncommitted Changes: $($changes.Count) files" "Yellow"
    } else {
        Write-ColorOutput "  Working Directory: Clean" "Green"
    }
} else {
    Write-ColorOutput "  ❌ Not a Git repository" "Red"
}

# Component Status
Write-ColorOutput "`n🏗️  Component Status:" "Cyan"

# Core Components
$components = @(
    @{
        Name = "Market Data Agent"
        Test = "python -c `"import sys; sys.path.append('.'); from src.market_data.market_data_agent import MarketDataAgent; print('OK')`""
    },
    @{
        Name = "Redis Feature Store" 
        Test = "python -c `"import sys; sys.path.append('.'); from src.database.redis_feature_store import UnifiedRegimeFeatureStore; print('OK')`""
    },
    @{
        Name = "NNFX Strategy"
        Test = "python -c `"import sys; sys.path.append('.'); from src.strategy.nnfx_strategy import NNFXStrategy; print('OK')`""
    },
    @{
        Name = "Risk Manager"
        Test = "python -c `"import sys; sys.path.append('.'); from src.risk.risk_manager import RiskManagerAgent; print('OK')`""
    },
    @{
        Name = "Signal Agent"
        Test = "python -c `"import sys; sys.path.append('.'); from src.execution.signal_agent import SignalAgent; print('OK')`""
    },
    @{
        Name = "Event Store"
        Test = "python -c `"import sys; sys.path.append('.'); from src.events.event_store import EventStore; print('OK')`""
    }
)

$workingComponents = 0
foreach ($component in $components) {
    if (Test-Component -Component $component.Name -TestCommand $component.Test -SuccessMessage $component.Name -FailureMessage "$($component.Name) - Import failed") {
        $workingComponents++
    }
}

# Docker Status
Write-ColorOutput "`n🐳 Docker Status:" "Cyan"
try {
    $dockerRunning = docker info 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-ColorOutput "  ✅ Docker is running" "Green"
        
        # Check containers
        $containers = docker ps --format "table {{.Names}}\t{{.Status}}" 2>$null
        if ($containers) {
            Write-ColorOutput "  Running Containers:" "White"
            $containers | ForEach-Object { Write-ColorOutput "    $_" "White" }
        } else {
            Write-ColorOutput "  ℹ️  No containers running" "Yellow"
        }
    } else {
        Write-ColorOutput "  ❌ Docker is not running" "Red"
    }
} catch {
    Write-ColorOutput "  ❌ Docker is not available" "Red"
}

# Test Status
Write-ColorOutput "`n🧪 Test Status:" "Cyan"
try {
    $testResult = python -m pytest tests/ --tb=no -q 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-ColorOutput "  ✅ All tests passing" "Green"
    } else {
        Write-ColorOutput "  ❌ Some tests failing" "Red"
    }
} catch {
    Write-ColorOutput "  ❌ Tests cannot be executed" "Red"
}

# File Structure Check
Write-ColorOutput "`n📁 Critical Files:" "Cyan"
$criticalFiles = @(
    "requirements.txt",
    "src/market_data/market_data_agent.py", 
    "src/database/redis_feature_store.py",
    "src/strategy/nnfx_strategy.py",
    "src/risk/risk_manager.py",
    "src/execution/signal_agent.py",
    "src/events/event_store.py",
    "docker/compose/docker-compose.dev.yml",
    "scripts/setup_project.ps1",
    "tests/unit/test_market_data_agent.py",
    "tests/unit/test_redis_feature_store.py",
    "tests/unit/test_nnfx_strategy.py"
)

$missingFiles = @()
foreach ($file in $criticalFiles) {
    if (Test-Path $file) {
        Write-ColorOutput "  ✅ $file" "Green"
    } else {
        Write-ColorOutput "  ❌ $file" "Red"
        $missingFiles += $file
    }
}

# Summary
Write-ColorOutput "`n📈 Project Summary:" "Cyan"
Write-ColorOutput "  Components Working: $workingComponents/$($components.Count)" "White"
Write-ColorOutput "  Critical Files Missing: $($missingFiles.Count)" "White"
Write-ColorOutput "  Git Status: $(if ($changes) { 'Dirty' } else { 'Clean' })" "White"

if ($workingComponents -eq $components.Count -and $missingFiles.Count -eq 0 -and -not $changes) {
    Write-ColorOutput "`n🎉 Project is READY for deployment!" "Green"
} else {
    Write-ColorOutput "`n⚠️  Project needs attention before deployment" "Yellow"
    
    if ($missingFiles.Count -gt 0) {
        Write-ColorOutput "  Missing files need to be created" "Yellow"
    }
    if ($workingComponents -lt $components.Count) {
        Write-ColorOutput "  Some components have import issues" "Yellow" 
    }
    if ($changes) {
        Write-ColorOutput "  Uncommitted changes exist" "Yellow"
    }
}

Write-ColorOutput "`n💡 Recommended next steps:" "Cyan"
Write-ColorOutput "  .\scripts\github_update.ps1 -Version 0.2.0 -CreateTag" "White"
Write-ColorOutput "  .\scripts\run_tests.ps1" "White"
Write-ColorOutput "  .\scripts\run_system.ps1" "White"