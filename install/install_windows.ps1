################################################################################
# TradingAgents-CN Install Script (Windows)
# System: Windows 10+, Windows Server 2019+
# Version: 1.0.0-preview
################################################################################

# Stop on error
$ErrorActionPreference = "Stop"

# Color functions
function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warning-Custom {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Error-Custom {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-Header {
    param([string]$Message)
    Write-Host ""
    Write-Host "===============================================================" -ForegroundColor Blue
    Write-Host "  $Message" -ForegroundColor Blue
    Write-Host "===============================================================" -ForegroundColor Blue
    Write-Host ""
}

# Check if running as administrator
function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Check if Docker Desktop is installed
function Test-Docker {
    Write-Info "Checking Docker installation..."
    
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        $dockerVersion = (docker --version) -replace '.*version ([0-9.]+).*', '$1'
        Write-Success "Docker is installed (Version: $dockerVersion)"
        
        # Check if Docker is running
        try {
            docker ps | Out-Null
            Write-Success "Docker service is running"
            return $true
        }
        catch {
            Write-Warning-Custom "Docker is installed but not running"
            Write-Info "Please start Docker Desktop application"
            Read-Host "Press Enter to continue after starting Docker"
            return $true
        }
    }
    else {
        Write-Warning-Custom "Docker is not installed"
        return $false
    }
}

# Install Docker Desktop
function Install-Docker {
    Write-Header "Install Docker Desktop"
    
    Write-Info "Windows requires Docker Desktop"
    Write-Host ""
    Write-Host "Please follow these steps:"
    Write-Host "  1. Visit https://www.docker.com/products/docker-desktop/"
    Write-Host "  2. Download Docker Desktop for Windows"
    Write-Host "  3. Install and start Docker Desktop"
    Write-Host "  4. Wait for Docker to start completely"
    Write-Host ""
    
    $response = Read-Host "Open download page now? (y/n)"
    if ($response -eq 'y' -or $response -eq 'Y') {
        Start-Process "https://www.docker.com/products/docker-desktop/"
    }
    
    Write-Warning-Custom "Please install Docker Desktop and run this script again"
    exit 0
}

# Check Docker Compose
function Test-DockerCompose {
    Write-Info "Checking Docker Compose installation..."
    
    try {
        $composeVersion = (docker compose version) -replace '.*version ([v0-9.]+).*', '$1'
        Write-Success "Docker Compose is installed (Version: $composeVersion)"
        return $true
    }
    catch {
        Write-Error-Custom "Docker Compose is not installed"
        return $false
    }
}

# Create project directory
function New-ProjectDirectory {
    Write-Header "Create Project Directory"
    
    # Default installation directory
    $defaultDir = "$env:USERPROFILE\tradingagents-demo"
    
    $installDir = Read-Host "Enter installation directory [Default: $defaultDir]"
    if ([string]::IsNullOrWhiteSpace($installDir)) {
        $installDir = $defaultDir
    }
    
    if (Test-Path $installDir) {
        Write-Warning-Custom "Directory already exists: $installDir"
        $response = Read-Host "Delete and recreate? (y/n)"
        if ($response -eq 'y' -or $response -eq 'Y') {
            Remove-Item -Path $installDir -Recurse -Force
        }
        else {
            Write-Info "Using existing directory"
        }
    }
    
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
    Set-Location $installDir
    
    Write-Success "Project directory created: $installDir"
    return $installDir
}

# Download configuration files
function Get-ConfigFiles {
    Write-Header "Download Configuration Files"
    
    $githubRaw = "https://raw.githubusercontent.com/hsliuping/TradingAgents-CN/v1.0.0-preview"
    
    Write-Info "Downloading Docker Compose configuration..."
    Invoke-WebRequest -Uri "$githubRaw/docker-compose.hub.nginx.yml" -OutFile "docker-compose.hub.nginx.yml"
    
    Write-Info "Downloading environment configuration..."
    Invoke-WebRequest -Uri "$githubRaw/.env.docker" -OutFile ".env"
    
    Write-Info "Downloading Nginx configuration..."
    New-Item -ItemType Directory -Path "nginx" -Force | Out-Null
    Invoke-WebRequest -Uri "$githubRaw/nginx/nginx.conf" -OutFile "nginx\nginx.conf"
    
    Write-Success "Configuration files downloaded"
}

# Configure API keys
function Set-ApiKeys {
    Write-Header "Configure API Keys"
    
    Write-Info "System requires at least one AI model API key to work properly"
    Write-Host ""
    Write-Host "Supported AI models:"
    Write-Host "  1. Alibaba DashScope - Recommended, Chinese model"
    Write-Host "  2. DeepSeek - Recommended, cost-effective"
    Write-Host "  3. OpenAI - Requires international network"
    Write-Host "  4. Others (Baidu Wenxin, Google Gemini, etc.)"
    Write-Host ""
    
    $response = Read-Host "Configure API keys now? (y/n)"
    
    if ($response -eq 'y' -or $response -eq 'Y') {
        # Alibaba DashScope
        $dashscopeKey = Read-Host "Enter Alibaba DashScope API Key (leave empty to skip)"
        if (![string]::IsNullOrWhiteSpace($dashscopeKey)) {
            (Get-Content .env -Encoding UTF8) -replace 'DASHSCOPE_API_KEY=.*', "DASHSCOPE_API_KEY=$dashscopeKey" | Set-Content .env -Encoding UTF8
            Write-Success "Alibaba DashScope API Key configured"
        }
        
        # DeepSeek
        $deepseekKey = Read-Host "Enter DeepSeek API Key (leave empty to skip)"
        if (![string]::IsNullOrWhiteSpace($deepseekKey)) {
            (Get-Content .env -Encoding UTF8) -replace 'DEEPSEEK_API_KEY=.*', "DEEPSEEK_API_KEY=$deepseekKey" | Set-Content .env -Encoding UTF8
            (Get-Content .env -Encoding UTF8) -replace 'DEEPSEEK_ENABLED=.*', 'DEEPSEEK_ENABLED=true' | Set-Content .env -Encoding UTF8
            Write-Success "DeepSeek API Key configured"
        }
        
        # Tushare
        $tushareToken = Read-Host "Enter Tushare Token (leave empty to skip)"
        if (![string]::IsNullOrWhiteSpace($tushareToken)) {
            (Get-Content .env -Encoding UTF8) -replace 'TUSHARE_TOKEN=.*', "TUSHARE_TOKEN=$tushareToken" | Set-Content .env -Encoding UTF8
            (Get-Content .env -Encoding UTF8) -replace 'TUSHARE_ENABLED=.*', 'TUSHARE_ENABLED=true' | Set-Content .env -Encoding UTF8
            Write-Success "Tushare Token configured"
        }
    }
    else {
        Write-Warning-Custom "Skipped API key configuration, please edit .env file manually later"
    }
}

# Start services
function Start-Services {
    Write-Header "Start Services"
    
    Write-Info "Pulling Docker images..."
    docker compose -f docker-compose.hub.nginx.yml pull
    
    Write-Info "Starting all services..."
    docker compose -f docker-compose.hub.nginx.yml up -d
    
    Write-Info "Waiting for services to start (about 30 seconds)..."
    Start-Sleep -Seconds 30
    
    Write-Success "Services started"
}

# Import initial configuration
function Import-Config {
    Write-Header "Import Initial Configuration"
    
    Write-Info "Importing system configuration and creating admin account..."
    docker exec -it tradingagents-backend python scripts/import_config_and_create_user.py
    
    Write-Success "Initial configuration imported"
}

# Show access information
function Show-AccessInfo {
    param([string]$InstallDir)
    
    Write-Header "Installation Complete"
    
    Write-Host ""
    Write-Success "TradingAgents-CN installed successfully!"
    Write-Host ""
    Write-Host "Access URL:" -ForegroundColor Green
    Write-Host "  http://localhost" -ForegroundColor Blue
    Write-Host ""
    Write-Host "Default login credentials:" -ForegroundColor Green
    Write-Host "  Username: admin" -ForegroundColor Yellow
    Write-Host "  Password: admin123" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Common commands:" -ForegroundColor Green
    Write-Host "  View status: docker compose -f docker-compose.hub.nginx.yml ps" -ForegroundColor Blue
    Write-Host "  View logs: docker compose -f docker-compose.hub.nginx.yml logs -f" -ForegroundColor Blue
    Write-Host "  Stop services: docker compose -f docker-compose.hub.nginx.yml stop" -ForegroundColor Blue
    Write-Host "  Start services: docker compose -f docker-compose.hub.nginx.yml start" -ForegroundColor Blue
    Write-Host "  Restart services: docker compose -f docker-compose.hub.nginx.yml restart" -ForegroundColor Blue
    Write-Host ""
    Write-Info "Installation directory: $InstallDir"
    Write-Host ""
}

# Main function
function Main {
    Clear-Host
    Write-Header "TradingAgents-CN One-Click Installation Script (Windows)"
    
    # Check administrator privileges
    if (!(Test-Administrator)) {
        Write-Warning-Custom "Recommended to run this script as administrator"
        $response = Read-Host "Continue anyway? (y/n)"
        if ($response -ne 'y' -and $response -ne 'Y') {
            exit 1
        }
    }
    
    # Check and install Docker
    if (!(Test-Docker)) {
        Install-Docker
    }
    
    # Check Docker Compose
    if (!(Test-DockerCompose)) {
        Write-Error-Custom "Docker Compose is not installed, please upgrade Docker Desktop to the latest version"
        exit 1
    }
    
    # Create project directory
    $installDir = New-ProjectDirectory
    
    # Download configuration files
    Get-ConfigFiles
    
    # Configure API keys
    Set-ApiKeys
    
    # Start services
    Start-Services
    
    # Import initial configuration
    Import-Config
    
    # Show access information
    Show-AccessInfo -InstallDir $installDir
}

# Run main function
try {
    Main
}
catch {
    Write-Error-Custom "Error during installation: $_"
    exit 1
}