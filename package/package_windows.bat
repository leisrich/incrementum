@echo off
echo Packaging Incrementum for Windows...
python package.py --platform windows --clean
echo.
echo If the packaging was successful, you can find the executable at:
echo     dist\Incrementum.exe
echo.
pause 