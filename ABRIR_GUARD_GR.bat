@echo off
echo Iniciando Guard GR v1.0...
cd /d "%~dp0"
py -m streamlit run main.py
pause
