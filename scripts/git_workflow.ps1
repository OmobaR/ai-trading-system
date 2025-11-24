# scripts/git_workflow.ps1 - Standard Git workflow for AI Trading System

param(
    [string]$FeatureName,
    [string]$CommitMessage,
    [switch]$Hotfix,
    [switch]$Release
)

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Invoke-GitCommand {
    param([string]$Command, [string]$Description)
    Write-ColorOutput "`n🔧 $Description..." "Yellow"
    Invoke-Expression "git $Command"
    if ($LASTEXITCODE -ne 0) {
        Write-ColorOutput "❌ Git command failed: git $Command" "Red"
        exit 1
    }
}

# Main workflow
Write-ColorOutput "🚀 AI Trading System Git Workflow" "Green"
Write-ColorOutput "======================================" "Cyan"

try {
    # Ensure we're on the correct branch
    $currentBranch = git branch --show-current
    
    if ($Hotfix) {
        Write-ColorOutput "🔄 Starting hotfix workflow..." "Red"
        Invoke-GitCommand "checkout main" "Switching to main branch"
        Invoke-GitCommand "pull origin main" "Pulling latest main"
        Invoke-GitCommand "checkout -b hotfix/$FeatureName" "Creating hotfix branch"
    }
    elseif ($Release) {
        Write-ColorOutput "🎯 Starting release workflow..." "Magenta"
        Invoke-GitCommand "checkout develop" "Switching to develop branch"
        Invoke-GitCommand "pull origin develop" "Pulling latest develop"
        Invoke-GitCommand "checkout -b release/$FeatureName" "Creating release branch"
    }
    else {
        Write-ColorOutput "🌿 Starting feature workflow..." "Blue"
        Invoke-GitCommand "checkout develop" "Switching to develop branch"
        Invoke-GitCommand "pull origin develop" "Pulling latest develop"
        Invoke-GitCommand "checkout -b feature/$FeatureName" "Creating feature branch"
    }

    Write-ColorOutput "`n✅ Workflow setup complete!" "Green"
    Write-ColorOutput "Current branch: $(git branch --show-current)" "Cyan"
    
    Write-ColorOutput "`n📝 Next steps:" "Yellow"
    Write-ColorOutput "  1. Make your changes to the code" "White"
    Write-ColorOutput "  2. Stage changes: git add ." "White"
    Write-ColorOutput "  3. Commit changes: git commit -m '$CommitMessage'" "White"
    Write-ColorOutput "  4. Push branch: git push -u origin $(git branch --show-current)" "White"
    
    if ($Hotfix) {
        Write-ColorOutput "  5. Create PR to main and develop branches" "Red"
    }
    elseif ($Release) {
        Write-ColorOutput "  5. Create PR to main branch" "Magenta"
    }
    else {
        Write-ColorOutput "  5. Create PR to develop branch" "Blue"
    }
}
catch {
    Write-ColorOutput "❌ Error in Git workflow: $($_.Exception.Message)" "Red"
    exit 1
}