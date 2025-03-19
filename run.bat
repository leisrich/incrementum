@echo off
REM run.bat - Script to run the Incrementum application on Windows

REM Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Python 3 is required but not found. Please install Python 3 and try again.
    exit /b 1
)

REM Check for virtual environment
if not exist "incrementum-env" (
    echo Creating virtual environment...
    python -m venv incrementum-env
    
    if errorlevel 1 (
        echo Failed to create virtual environment. Please install Python 3 and try again.
        exit /b 1
    )
)

REM Activate virtual environment
call incrementum-env\Scripts\activate.bat

REM Run dependency check
echo Checking dependencies...
python fix_dependencies.py

if errorlevel 1 (
    echo Failed to set up dependencies. Please check the error messages above.
    exit /b 1
)

REM Fix DOCX dependency specifically
echo Fixing DOCX dependency...
python fix_docx.py

if errorlevel 1 (
    echo Failed to fix DOCX dependency. Please check the error messages above.
    exit /b 1
)

REM Initialize database if needed
python -c "import appdirs; import os; print(os.path.join(appdirs.user_data_dir('Incrementum', 'Incrementum'), 'incrementum.db'))" > temp_path.txt
set /p DB_PATH=<temp_path.txt
del temp_path.txt

if not exist "%DB_PATH%" (
    echo Initializing database...
    python init_db.py
)

REM Run the application
echo Starting Incrementum...
python main.py 