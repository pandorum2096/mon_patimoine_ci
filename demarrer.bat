@echo off
title Mon Patrimoine CI
color 0A
echo.
echo  ==========================================
echo    Mon Patrimoine CI  -- Demarrage
echo  ==========================================
echo.

:: Verifier Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERREUR : Python n'est pas installe.
    echo  Telechargez-le sur https://www.python.org/downloads/
    pause
    exit /b 1
)
echo  OK : Python detecte

:: Installer les paquets essentiels d'abord
echo  Installation : flask, PyJWT, bcrypt, flask-cors, python-dotenv...
pip install flask flask-cors PyJWT bcrypt gunicorn python-dotenv --quiet
if %errorlevel% neq 0 (
    echo  ERREUR lors de l'installation des paquets de base.
    pause
    exit /b 1
)
echo  OK : Paquets de base installes

:: Essayer psycopg2-binary (wheels precompiles uniquement)
echo  Installation : psycopg2-binary (tentative binaire)...
pip install psycopg2-binary --only-binary :all: --quiet 2>nul
if %errorlevel% equ 0 (
    echo  OK : psycopg2-binary installe
) else (
    echo  Info : psycopg2-binary non disponible, utilisation de pg8000...
    pip install pg8000 --quiet
    if %errorlevel% neq 0 (
        echo  ERREUR : impossible d'installer pg8000
        pause
        exit /b 1
    )
    echo  OK : pg8000 installe (alternative pure Python)
)

:: Initialiser la base de donnees
echo  Initialisation de la base de donnees...
python "%~dp0init_db.py"
if %errorlevel% neq 0 (
    echo  ERREUR : echec de l'initialisation de la base.
    pause
    exit /b 1
)

:: Lancer le serveur
echo.
echo  Lancement du serveur...
echo  Laissez cette fenetre ouverte pendant l'utilisation.
echo  Pour arreter : Ctrl+C ou fermer cette fenetre.
echo.
python "%~dp0app.py"
pause
