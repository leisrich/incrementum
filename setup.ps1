# setup.ps1 - PowerShell script to set up and run Incrementum

# Function to check if a command exists
function Test-Command($Command) {
    return [bool](Get-Command -Name $Command -ErrorAction SilentlyContinue)
}

# Function to check if Python is installed
function Test-Python {
    try {
        $pythonVersion = python --version
        if ($pythonVersion) {
            Write-Host "Python is installed: $pythonVersion"
            return $true
        }
    }
    catch {
        return $false
    }
    return $false
}

# Check if Git is installed
if (-not (Test-Command "git")) {
    Write-Host "Git is not installed. Please install Git and try again."
    exit 1
}

# Check if Python is installed
if (-not (Test-Python)) {
    Write-Host "Python 3 is required but not found. Please install Python 3 and try again."
    exit 1
}

# Create a temporary directory for the setup
$tempDir = Join-Path $env:TEMP "incrementum-setup"
if (Test-Path $tempDir) {
    Remove-Item -Path $tempDir -Recurse -Force
}
New-Item -ItemType Directory -Path $tempDir | Out-Null
Set-Location $tempDir

# Clone the repository
Write-Host "Cloning Incrementum repository..."
git clone https://github.com/melpomenex/incrementum.git .
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to clone repository. Please check your internet connection and try again."
    exit 1
}

# Create and activate virtual environment
Write-Host "Setting up virtual environment..."
python -m venv incrementum-env
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to create virtual environment. Please check your Python installation."
    exit 1
}

# Activate virtual environment
$activateScript = Join-Path $tempDir "incrementum-env\Scripts\Activate.ps1"
. $activateScript

# Run dependency check
Write-Host "Checking dependencies..."
python fix_dependencies.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to set up dependencies. Please check the error messages above."
    exit 1
}

# Fix DOCX dependency
Write-Host "Fixing DOCX dependency..."
python fix_docx.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to fix DOCX dependency. Please check the error messages above."
    exit 1
}

# Initialize database if needed
$dbPath = python -c "import appdirs; import os; print(os.path.join(appdirs.user_data_dir('Incrementum', 'Incrementum'), 'incrementum.db'))"
if (-not (Test-Path $dbPath)) {
    Write-Host "Initializing database..."
    python init_db.py
}

# Run the application
Write-Host "Starting Incrementum..."
python main.py

# Clean up
Write-Host "Setup complete! The application is now running." 