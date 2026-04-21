@echo off
echo === isort ===
isort zoom_cpe.py tests/
if %errorlevel% neq 0 exit /b %errorlevel%

echo === black ===
black zoom_cpe.py tests/
if %errorlevel% neq 0 exit /b %errorlevel%

echo === pytest + coverage ===
pytest tests/ -v --cov=zoom_cpe --cov-report=term-missing
