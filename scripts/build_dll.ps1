# scripts/build_dll.ps1
Write-Host "🔧 Building AI Trading Bridge DLL..." -ForegroundColor Green

# Check if CMake is available
$cmakeCheck = Get-Command cmake -ErrorAction SilentlyContinue
if (-not $cmakeCheck) {
    Write-Host "❌ CMake is not installed or not in PATH" -ForegroundColor Red
    Write-Host "   Please install CMake from https://cmake.org" -ForegroundColor Yellow
    exit 1
}

# Check if Visual Studio build tools are available
$msbuildCheck = Get-Command msbuild -ErrorAction SilentlyContinue
if (-not $msbuildCheck) {
    Write-Host "❌ MSBuild is not available" -ForegroundColor Red
    Write-Host "   Please install Visual Studio Build Tools" -ForegroundColor Yellow
    exit 1
}

# Create build directory
if (Test-Path "build") {
    Remove-Item -Recurse -Force build
}
New-Item -ItemType Directory -Path build | Out-Null

# Configure with CMake
Write-Host "`n📦 Configuring project with CMake..." -ForegroundColor Yellow
Set-Location build
cmake .. -G "Visual Studio 17 2022" -A x64

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ CMake configuration failed" -ForegroundColor Red
    exit 1
}

# Build the project
Write-Host "`n🏗️ Building DLL..." -ForegroundColor Yellow
cmake --build . --config Release

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Build failed" -ForegroundColor Red
    exit 1
}

# Check if DLL was created
if (Test-Path "Release/bridge_dll.dll") {
    Write-Host "✅ DLL built successfully: build/Release/bridge_dll.dll" -ForegroundColor Green
    
    # Copy to MT5 directory (adjust path as needed)
    $mt5Path = "C:/Users/olugb/AppData/Roaming/MetaQuotes/Terminal/DEV_ID/MQL5/Libraries/bridge_dll.dll"
    if (Test-Path (Split-Path $mt5Path)) {
        Copy-Item "Release/bridge_dll.dll" $mt5Path -Force
        Write-Host "✅ DLL copied to MT5 Libraries directory" -ForegroundColor Green
    } else {
        Write-Host "⚠️ MT5 directory not found, manual copy required" -ForegroundColor Yellow
    }
} else {
    Write-Host "❌ DLL was not created" -ForegroundColor Red
}

Set-Location ..
Write-Host "`n🎉 Build process completed!" -ForegroundColor Green