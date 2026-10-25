@echo off
REM Gera o PSTudo.exe na pasta dist. Precisa do Python 3.12 instalado.
cd /d "%~dp0"

python -m pip install -r requirements.txt pyinstaller==6.22.3
if errorlevel 1 goto erro

python -m PyInstaller --noconfirm --onefile --noconsole --name PSTudo --icon assets\icon.ico --add-data "assets\som_envio.wav;." --add-data "third_party\ps3iso-utils\bin\makeps3iso.exe;." --add-data "third_party\ps3iso-utils\LICENSE;LICENSES\ps3iso-utils" --add-data "LICENSE;LICENSES\PSTudo" --add-data "THIRD_PARTY_NOTICES.md;LICENSES" --collect-data customtkinter --collect-submodules glcontext --collect-submodules moderngl pstudo.py
if errorlevel 1 goto erro

echo.
echo Pronto! O arquivo esta em dist\PSTudo.exe
pause
exit /b 0

:erro
echo.
echo Algo deu errado. Veja as mensagens acima.
pause
exit /b 1
