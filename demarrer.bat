@echo off
title Mon Patrimoine CI
color 0A
echo.
echo  ==========================================
echo    💰  Mon Patrimoine CI  — Demarrage
echo  ==========================================
echo.

:: Vérifier Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ❌ Python n'est pas installe.
    echo  Telechargez-le sur https://www.python.org/downloads/
    pause
    exit /b 1
)

echo  ✅ Python detecte
echo  ⏳ Installation des dependances...
pip install -r "%~dp0requirements.txt" --quiet

echo  ⏳ Initialisation de la base de donnees...
python "%~dp0init_db.py"

echo.
echo  ⏳ Lancement du serveur local...
echo  L'application va s'ouvrir dans votre navigateur.
echo  Laissez cette fenetre ouverte pendant l'utilisation.
echo  Pour arreter : fermez cette fenetre ou faites Ctrl+C
echo.

python "%~dp0app.py"
pause
