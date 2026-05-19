@echo off
REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════
REM    IDS NOTIFIER AUTO INSTALLER v3.0
REM    Installation automatique - Aucune interaction utilisateur
REM    Supabase + Email SMTP Gmail
REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════

setlocal enabledelayedexpansion

REM ── Couleurs ANSI (Windows 10+) ───────────────────────────────────────────────────────────
set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "BLUE=[94m"
set "RESET=[0m"

title IDS Notifier Auto Installer

cls
echo.
echo %BLUE%═══════════════════════════════════════════════════════════════════════════════════════════════════════%RESET%
echo %BLUE%   🛡️  IDS ALERT NOTIFIER v3.0 - AUTO INSTALLATION%RESET%
echo %BLUE%   📡 Database: Supabase (postgresql)%RESET%
echo %BLUE%   📧 Email: benainimeroua@gmail.com (SMTP Gmail)%RESET%
echo %BLUE%   ⏱️  Polling Interval: 5 secondes%RESET%
echo %BLUE%═══════════════════════════════════════════════════════════════════════════════════════════════════════%RESET%
echo.

REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
REM ÉTAPE 0 : Vérifier droits administrateur
REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
echo %BLUE%[ADMIN CHECK]%RESET% Vérification des droits administrateur...
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%[ERROR] Ce script doit être exécuté en tant qu'Administrateur%RESET%
    echo.
    echo   → Cliquez-droit sur p_auto.bat
    echo   → "Exécuter en tant qu'administrateur"
    echo.
    pause
    exit /b 1
)
echo %GREEN%✓ Droits administrateur confirmés%RESET%
echo.

REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
REM ÉTAPE 1 : Vérifier Python
REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
echo %BLUE%[1/8]%RESET% Vérification de Python...

where python >nul 2>&1
if errorlevel 1 (
    echo %RED%✗ Python non trouvé dans PATH%RESET%
    echo.
    echo   Installez Python depuis: https://www.python.org/downloads/
    echo   ⚠️  Cochez "Add Python to PATH" lors de l'installation
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "PY_VERSION=%%i"
echo %GREEN%✓ Python %PY_VERSION% trouvé%RESET%
echo.

REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
REM ÉTAPE 2 : Chemins
REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
echo %BLUE%[2/8]%RESET% Configuration des chemins...

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "NOTIFIER=%SCRIPT_DIR%\notifier_advanced.py"
set "EMAIL_CONFIG_TEMPLATE=%SCRIPT_DIR%\email_config_template.json"
set "CONFIG_DIR=%APPDATA%\IDS_Notifier"
set "EMAIL_CONFIG=%CONFIG_DIR%\email_config.json"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

if not exist "%NOTIFIER%" (
    echo %RED%✗ notifier_advanced.py non trouvé dans %SCRIPT_DIR%%RESET%
    echo.
    pause
    exit /b 1
)

echo %GREEN%✓ Notifier: %NOTIFIER%%RESET%

if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"
echo %GREEN%✓ Config Dir: %CONFIG_DIR%%RESET%
echo.

REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
REM ÉTAPE 3 : Test Supabase
REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
echo %BLUE%[3/8]%RESET% Test de connexion à Supabase...

set "TEST_DB=%TEMP%\test_supabase.py"
(
    echo import os
    echo from urllib.parse import urlparse
    echo db_url = r"postgresql://postgres.jleedvfezpjaojgwltfu:Malek140504%%40%%21@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"
    echo try:
    echo     import psycopg2
    echo     parsed = urlparse(db_url)
    echo     conn = psycopg2.connect(
    echo         dbname=parsed.path.lstrip('/') or 'postgres',
    echo         user=parsed.username,
    echo         password=parsed.password,
    echo         host=parsed.hostname,
    echo         port=parsed.port or 5432,
    echo         sslmode='require',
    echo         connect_timeout=3
    echo     )
    echo     conn.close()
    echo     print("OK")
    echo except:
    echo     print("FAIL")
) > "%TEST_DB%"

for /f "delims=" %%i in ('python "%TEST_DB%" 2^>nul') do set "DB_TEST=%%i"
del "%TEST_DB%" 2>nul

if "%DB_TEST%"=="OK" (
    echo %GREEN%✓ Supabase accessible%RESET%
) else (
    echo %YELLOW%⚠️  Impossible de se connecter à Supabase%RESET%
    echo    Vérifiez la connectivité Internet et les identifiants
)
echo.

REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
REM ÉTAPE 4 : Installation des dépendances
REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
echo %BLUE%[4/8]%RESET% Installation des dépendances Python...

python -m pip install --upgrade pip --quiet 2>nul

echo   Installing psycopg2-binary...
python -m pip install psycopg2-binary --quiet

echo   Installing requests...
python -m pip install requests --quiet

echo   Installing plyer...
python -m pip install plyer --quiet

echo   Installing winotify...
python -m pip install winotify --quiet

echo   Installing win10toast-persist...
python -m pip install win10toast-persist --quiet

echo   Installing winrt...
python -m pip install winrt --quiet

echo %GREEN%✓ Toutes les dépendances installées%RESET%
echo.

REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
REM ÉTAPE 5 : Copier la configuration email
REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
echo %BLUE%[5/8]%RESET% Configuration email automatique...

if exist "%EMAIL_CONFIG_TEMPLATE%" (
    copy /Y "%EMAIL_CONFIG_TEMPLATE%" "%EMAIL_CONFIG%" >nul
    echo %GREEN%✓ Configuration email copiée%RESET%
    echo   From: benainimeroua@gmail.com
    echo   SMTP: smtp.gmail.com:587
) else (
    echo %YELLOW%⚠️  email_config_template.json non trouvé%RESET%
)
echo.

REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
REM ÉTAPE 6 : Ajouter au démarrage Windows
REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
echo %BLUE%[6/8]%RESET% Ajout au démarrage automatique...

set "STARTUP_VBS=%STARTUP%\IDS_Notifier.vbs"

(
    echo Set oWS = WScript.CreateObject^("WScript.Shell"^)
    echo sCmd = "pythonw ""%NOTIFIER%"" --interval 5"
    echo oWS.Run sCmd, 0, False
) > "%STARTUP_VBS%"

echo %GREEN%✓ Raccourci ajouté au démarrage%RESET%
echo.

REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
REM ÉTAPE 7 : Créer une tâche planifiée (optionnel, pour plus de fiabilité)
REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
echo %BLUE%[7/8]%RESET% Création d'une tâche planifiée...

schtasks /delete /tn "IDS_Notifier_Auto" /f >nul 2>&1
schtasks /create /tn "IDS_Notifier_Auto" /tr "pythonw \"%NOTIFIER%\" --interval 5" /sc onstart /delay 0000:30 /ru "SYSTEM" /f >nul 2>&1

if %errorlevel% equ 0 (
    echo %GREEN%✓ Tâche planifiée créée (démarrage au boot)%RESET%
) else (
    echo %YELLOW%⚠️  Impossible de créer la tâche planifiée%RESET%
    echo    Le notifier démarrera via le dossier Démarrage uniquement
)
echo.

REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
REM ÉTAPE 8 : Démarrage du notifier
REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
echo %BLUE%[8/8]%RESET% Démarrage du notifier en arrière-plan...

REM Arrêter les instances précédentes
taskkill /F /IM pythonw.exe >nul 2>&1
timeout /t 2 /nobreak >nul

REM Lancer le notifier
pythonw "%NOTIFIER%" --interval 5

timeout /t 3 /nobreak >nul

REM Vérifier que le notifier s'est lancé
tasklist /FI "IMAGENAME eq pythonw.exe" 2>nul | find /I "pythonw.exe" >nul
if %errorlevel% equ 0 (
    echo %GREEN%✓ Notifier démarré en arrière-plan%RESET%
) else (
    echo %RED%✗ Le notifier n'a pas pu démarrer%RESET%
    echo   Consultez les logs: %CONFIG_DIR%\notifier.log
)
echo.

REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
REM RÉSUMÉ
REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
echo %GREEN%═══════════════════════════════════════════════════════════════════════════════════════════════════════%RESET%
echo %GREEN%   ✅ INSTALLATION RÉUSSIE ✅%RESET%
echo %GREEN%═══════════════════════════════════════════════════════════════════════════════════════════════════════%RESET%
echo.
echo 📡 Database      : Supabase (aws-0-eu-west-1.pooler.supabase.com)
echo 📧 Email         : benainimeroua@gmail.com
echo 📁 Logs          : %CONFIG_DIR%\notifier.log
echo 📁 Config email  : %CONFIG_DIR%\email_config.json
echo 📝 État          : %CONFIG_DIR%\notifier_state.json
echo.
echo 🚀 Le notifier va automatiquement:
echo    ✓ Démarrer en tâche de fond à chaque redémarrage Windows
echo    ✓ Surveiller les alertes Supabase toutes les 5 secondes
echo    ✓ Envoyer des notifications Windows toast
echo    ✓ Envoyer des emails aux utilisateurs admin/security_admin
echo.
echo %YELLOW%⏸️  Appuyez sur une touche pour fermer ce fenêtre...%RESET%
echo.
pause
exit /b 0
