@echo off
cd /d "%~dp0"
echo Verificando dependencias...
pip install -r requirements-manage.txt -q
echo.
echo Abrindo interface no navegador...
start http://localhost:5000
python manage_web.py
pause
