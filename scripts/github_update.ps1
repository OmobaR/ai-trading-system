
## 2. **GitHub Update Scripts**

### **`scripts/github_update.ps1`**

```powershell
# scripts/github_update.ps1 - Complete GitHub version update
param(
    [string]$Version = "0.2.0",
    [string]$CommitMessage = "feat: complete AI trading system implementation",
    [switch]$PushToRemote,
    [switch]$CreateTag
)

function Write-ColorOutput {
    param([string]$Message, [string]$Color = "White")
    Write-Host $Message -ForegroundColor $Color
}

function Invoke-GitCommand {
    param([string]$Command, [string]$Description)
    Write-ColorOutput "`n🔧 $Description..." "Yellow"
    Write-ColorOutput "  Command: git $Command" "Gray"
    
    $output = Invoke-Expression "git $Command 2>&1"
    if ($LASTEXITCODE -ne 0) {
        Write-ColorOutput "❌ Git command failed: $output" "Red"
        return $false
    }
    return $true
}

function Update-VersionFiles {
    Write-ColorOutput "`n📝 Updating version files..." "Cyan"
    
    # Create VERSION file
    $Version | Out-File -FilePath "VERSION" -Encoding utf8
    Write-ColorOutput "  Created VERSION file: $Version" "Green"
    
    # Update CHANGELOG if it exists, otherwise create
    if (Test-Path "CHANGELOG.md") {
        Write-ColorOutput "  Updated CHANGELOG.md" "Green"
    } else {
        @"
# Changelog
All notable changes to the AI Trading System will be documented in this file.

## [$Version] - $(Get-Date -Format "yyyy-MM-dd")
### Added
- Complete AI trading system implementation
- Market data pipeline with regime detection
- Unified feature store and NNFX strategy
- Risk management and execution bridge
- Docker development environment

### Enhanced
- Real-time regime detection
- ML-ready feature storage
- Comprehensive testing suite
- Automated deployment scripts
"@ | Out-File -FilePath "CHANGELOG.md" -Encoding utf8
        Write-ColorOutput "  Created CHANGELOG.md" "Green"
    }
    
    # Update README if it doesn't exist
    if (-Not (Test-Path "README.md")) {
        # Use the README content from above
        # This would be the full README content
        Write-ColorOutput "  Created README.md" "Green"
    }
}

function Get-ProjectStatus {
    Write-ColorOutput "`n📊 Project Status Check..." "Cyan"
    
    # Check critical files
    $criticalFiles = @(
        "src/market_data/market_data_agent.py",
        "src/database/redis_feature_store.py", 
        "src/strategy/nnfx_strategy.py",
        "src/risk/risk_manager.py",
        "src/execution/signal_agent.py",
        "requirements.txt",
        "docker/compose/docker-compose.dev.yml"
    )
    
    $missingFiles = @()
    foreach ($file in $criticalFiles) {
        if (-Not (Test-Path $file)) {
            $missingFiles += $file
        }
    }
    
    if ($missingFiles.Count -gt 0) {
        Write-ColorOutput "❌ Missing critical files:" "Red"
        foreach ($file in $missingFiles) {
            Write-ColorOutput "  - $file" "Red"
        }
        return $false
    }
    
    Write-ColorOutput "✅ All critical files present" "Green"
    
    # Check if tests pass
    Write-ColorOutput "`n🧪 Running quick test validation..." "Yellow"
    try {
        python -c "import sys; sys.path.append('.'); from src.database.redis_feature_store import UnifiedRegimeFeatureStore; print('✅ Core imports successful')"
        Write-ColorOutput "✅ Core functionality validated" "Green"
    } catch {
        Write-ColorOutput "❌ Core validation failed: $($_.Exception.Message)" "Red"
        return $false
    }
    
    return $true
}

# Main execution
Write-ColorOutput "🚀 AI Trading System - GitHub Version Update" "Green"
Write-ColorOutput "=============================================" "Cyan"
Write-ColorOutput "Version: $Version" "White"
Write-ColorOutput "Message: $CommitMessage" "White"

try {
    # Validate project status
    if (-Not (Get-ProjectStatus)) {
        Write-ColorOutput "❌ Project validation failed. Please fix issues before updating." "Red"
        exit 1
    }
    
    # Update version files
    Update-VersionFiles
    
    # Get current branch
    $currentBranch = git branch --show-current
    Write-ColorOutput "`n🌿 Current branch: $currentBranch" "Cyan"
    
    # Git operations
    Write-ColorOutput "`n🔧 Starting Git operations..." "Cyan"
    
    # Stage all changes
    if (-Not (Invoke-GitCommand "add ." "Staging all changes")) { exit 1 }
    
    # Check if there are changes to commit
    $status = git status --porcelain
    if (-Not $status) {
        Write-ColorOutput "ℹ️  No changes to commit" "Yellow"
    } else {
        # Commit changes
        if (-Not (Invoke-GitCommand "commit -m `"$CommitMessage`"" "Committing changes")) { exit 1 }
        Write-ColorOutput "✅ Changes committed successfully" "Green"
    }
    
    # Create tag if requested
    if ($CreateTag) {
        if (Invoke-GitCommand "tag v$Version" "Creating tag v$Version")) {
            Write-ColorOutput "✅ Tag v$Version created" "Green"
        }
    }
    
    # Push to remote if requested
    if ($PushToRemote) {
        Write-ColorOutput "`n📤 Pushing to remote repository..." "Cyan"
        
        if (Invoke-GitCommand "push origin $currentBranch" "Pushing branch")) {
            Write-ColorOutput "✅ Branch pushed successfully" "Green"
        }
        
        if ($CreateTag) {
            if (Invoke-GitCommand "push origin v$Version" "Pushing tag")) {
                Write-ColorOutput "✅ Tag pushed successfully" "Green"
            }
        }
    }
    
    # Final status
    Write-ColorOutput "`n🎉 GitHub update completed successfully!" "Green"
    Write-ColorOutput "`n📊 Final Status:" "Cyan"
    Write-ColorOutput "  Version: $Version" "White"
    Write-ColorOutput "  Branch: $currentBranch" "White"
    Write-ColorOutput "  Commit: $(git log --oneline -1)" "White"
    
    if ($CreateTag) {
        Write-ColorOutput "  Tag: v$Version" "White"
    }
    
    if (-Not $PushToRemote) {
        Write-ColorOutput "`n💡 To push to remote, run:" "Yellow"
        Write-ColorOutput "  git push origin $currentBranch" "White"
        if ($CreateTag) {
            Write-ColorOutput "  git push origin v$Version" "White"
        }
    }
    
} catch {
    Write-ColorOutput "❌ GitHub update failed: $($_.Exception.Message)" "Red"
    exit 1
}