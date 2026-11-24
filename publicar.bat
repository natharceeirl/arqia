@echo off
REM Publica los cambios de esta carpeta en GitHub (natharceeirl/arqia).
REM Render vuelve a desplegar la aplicacion automaticamente despues de cada publicacion.
cd /d "%~dp0"
where git >nul 2>&1
if errorlevel 1 (
  echo Git no esta instalado. Descargalo de https://git-scm.com e intenta de nuevo.
  pause
  exit /b 1
)
if not exist ".git" (
  echo Preparando la carpeta por primera vez...
  git init -b main
  git remote add origin https://github.com/natharceeirl/arqia.git
  git fetch origin
  git reset --soft origin/main
)
git config user.name >nul 2>&1 || git config user.name "Patrick"
git config user.email >nul 2>&1 || git config user.email "natharce.eirl@gmail.com"
git add -A
git commit -m "Actualizacion de ARQIA %date% %time%"
git pull --rebase origin main
git push -u origin main
if errorlevel 1 (
  echo.
  echo No se pudo publicar. Revisa el mensaje de arriba y avisale a Claude.
) else (
  echo.
  echo Listo. Render publicara la nueva version en unos minutos.
)
pause
