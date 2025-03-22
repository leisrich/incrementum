@echo off
echo Building Incrementum for Windows...

:: Clean any previous build artifacts
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del Incrementum.spec 2>nul

:: Run PyInstaller with all necessary options
pyinstaller ^
  --name Incrementum ^
  --icon assets\icons\incrementum.ico ^
  --windowed ^
  --onefile ^
  --clean ^
  --noconfirm ^
  --add-data "assets;assets" ^
  --hidden-import core.knowledge_base.database ^
  --hidden-import core.knowledge_base.database_migration ^
  --exclude-module PyQt5 ^
  --exclude-module tkinter ^
  --exclude-module PySide2 ^
  --exclude-module PySide6 ^
  main.py

if %ERRORLEVEL% EQU 0 (
  echo Build completed successfully!
  echo Executable created at: dist\Incrementum.exe
  
  :: Create data directory for database
  mkdir dist\data 2>nul
  
  echo.
  echo To run the application:
  echo   Double-click dist\Incrementum.exe
) else (
  echo Build failed!
)

pause 