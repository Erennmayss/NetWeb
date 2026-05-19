@echo off
:: ============================================================
:: p.bat - IDS Notifier - Installation 100% automatique
:: Aucun menu, aucune saisie, email fixe hardcode
:: ============================================================

setlocal enabledelayedexpansion

set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "BLUE=[94m"
set "CYAN=[96m"
set "RESET=[0m"

title IDS Notifier - Installation automatique

:: ════════════════════════════════════════════════════════
:: Chemins
:: ════════════════════════════════════════════════════════
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "NOTIFIER=%SCRIPT_DIR%\notifier.py"
set "RUN_VBS=%SCRIPT_DIR%\run_notifier.vbs"
set "STOP_VBS=%SCRIPT_DIR%\stop_notifier.vbs"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "CONFIG_DIR=%APPDATA%\IDS_Notifier"
set "EMAIL_CONFIG=%CONFIG_DIR%\email_config.json"

cls
echo.
echo %BLUE%╔══════════════════════════════════════════════════════════════╗%RESET%
echo %BLUE%║         IDS Alert Notifier - Installation v2.0              ║%RESET%
echo %BLUE%║   Base : 192.168.1.2:5432  ^|  Utilisateur : aya            ║%RESET%
echo %BLUE%╚══════════════════════════════════════════════════════════════╝%RESET%
echo.

:: ── Droits administrateur ──────────────────────────────────────────────────
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%[ERREUR]%RESET% Ce script doit etre execute en tant qu'Administrateur.
    echo Cliquez droit sur le fichier ^> "Executer en tant qu'administrateur"
    pause
    exit /b 1
)

:: ════════════════════════════════════════════════════════
:: ÉTAPE 1 — Python
:: ════════════════════════════════════════════════════════
echo %GREEN%[1/11]%RESET% Verification de Python...
where python >nul 2>&1
if errorlevel 1 (
    echo %RED%[ERREUR]%RESET% Python introuvable dans le PATH.
    echo Telechargez-le sur https://www.python.org/downloads/
    echo (cochez "Add Python to PATH" lors de l'installation^)
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "PY_VERSION=%%i"
echo %GREEN%OK%RESET% Python %PY_VERSION% detecte.

python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo %YELLOW%pip absent - installation en cours...%RESET%
    python -m ensurepip --upgrade
)

:: ════════════════════════════════════════════════════════
:: ÉTAPE 2 — Test connexion DB
:: ════════════════════════════════════════════════════════
echo.
echo %GREEN%[2/11]%RESET% Test de connexion a la base de donnees...

set "TEST_SCRIPT=%TEMP%\ids_test_db.py"
(
echo import psycopg2
echo try:
echo     conn = psycopg2.connect(dbname="ids_db",user="aya",password="aya",host="192.168.1.2",port="5432",connect_timeout=3)
echo     conn.close()
echo     print("OK")
echo except:
echo     print("FAIL")
) > "%TEST_SCRIPT%"

for /f "delims=" %%i in ('python "%TEST_SCRIPT%" 2^>nul') do set "DB_TEST=%%i"
del "%TEST_SCRIPT%" 2>nul

if "%DB_TEST%"=="OK" (
    echo %GREEN%OK%RESET% Connexion a 192.168.1.2:5432 reussie.
) else (
    echo %YELLOW%AVERT%RESET% Base inaccessible pour l'instant - le notifier reessaiera automatiquement.
)

:: ════════════════════════════════════════════════════════
:: ÉTAPE 3 — Dépendances Python
:: ════════════════════════════════════════════════════════
echo.
echo %GREEN%[3/11]%RESET% Installation des dependances Python...

python -m pip install --upgrade pip --quiet
for %%P in (psycopg2-binary requests flask plyer winotify win10toast-persist winrt) do (
    echo    - %%P
    python -m pip install --quiet %%P
)
echo %GREEN%OK%RESET% Toutes les dependances installees.

:: ════════════════════════════════════════════════════════
:: ÉTAPE 4 — Scripts VBS
:: ════════════════════════════════════════════════════════
echo.
echo %GREEN%[4/11]%RESET% Creation des scripts de lancement...

(
    echo ' IDS Notifier - Launcher invisible
    echo Set oWS = WScript.CreateObject^("WScript.Shell"^)
    echo sFile = "%NOTIFIER:\=\\%"
    echo sCmd = "pythonw """ ^& sFile ^& """ --db --interval 5 --sound"
    echo oWS.Run sCmd, 0, False
    echo WScript.Sleep 2000
) > "%RUN_VBS%"

(
    echo ' IDS Notifier - Stopper
    echo Set oWS = WScript.CreateObject^("WScript.Shell"^)
    echo oWS.Run "taskkill /F /IM pythonw.exe", 0, False
    echo WScript.Sleep 1000
) > "%STOP_VBS%"

echo %GREEN%OK%RESET% Scripts VBS crees.

:: ════════════════════════════════════════════════════════
:: ÉTAPE 5 — Dossier Startup Windows
:: ════════════════════════════════════════════════════════
echo.
echo %GREEN%[5/11]%RESET% Ajout au demarrage Windows...

if exist "%STARTUP%\IDS_Notifier.vbs" del /Q "%STARTUP%\IDS_Notifier.vbs"
if exist "%STARTUP%\IDS_Notifier.lnk" del /Q "%STARTUP%\IDS_Notifier.lnk"
copy /Y "%RUN_VBS%" "%STARTUP%\IDS_Notifier.vbs" >nul
echo %GREEN%OK%RESET% Demarrage automatique configure.

:: ════════════════════════════════════════════════════════
:: ÉTAPE 6 — Tâche planifiée
:: ════════════════════════════════════════════════════════
echo.
echo %GREEN%[6/11]%RESET% Creation de la tache planifiee...

schtasks /delete /tn "IDS_Notifier" /f >nul 2>&1
schtasks /create /tn "IDS_Notifier" /tr "wscript.exe \"%RUN_VBS%\"" /sc onstart /delay 0001:00 /ru "SYSTEM" /f >nul 2>&1
if %errorlevel% equ 0 (
    echo %GREEN%OK%RESET% Tache planifiee creee.
) else (
    echo %YELLOW%AVERT%RESET% Tache planifiee non creee - le notifier demarrera via Startup.
)

:: ════════════════════════════════════════════════════════
:: ÉTAPE 7 — Configuration DB (hardcodée)
:: ════════════════════════════════════════════════════════
echo.
echo %GREEN%[7/11]%RESET% Ecriture de la configuration base de donnees...

if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"

(
    echo # IDS Notifier Configuration
    echo DB_NAME=ids_db
    echo DB_USER=aya
    echo DB_PASSWORD=aya
    echo DB_HOST=192.168.1.2
    echo DB_PORT=5432
    echo POLL_INTERVAL=5
    echo ENABLE_SOUND=true
    echo MODE=db_direct
) > "%CONFIG_DIR%\notifier.conf"

(
    echo DB_NAME=ids_db
    echo DB_USER=aya
    echo DB_PASSWORD=aya
    echo DB_HOST=192.168.1.2
    echo DB_PORT=5432
) > "%CONFIG_DIR%\.env"

echo %GREEN%OK%RESET% Configuration DB ecrite dans %CONFIG_DIR%

:: ════════════════════════════════════════════════════════
:: ÉTAPE 8 — Email hardcodé (toujours écrasé avec les bons paramètres)
:: ════════════════════════════════════════════════════════
echo.
echo %GREEN%[8/11]%RESET% Configuration email automatique (smtp.gmail.com)...

(
echo {
echo     "smtp_server": "smtp.gmail.com",
echo     "smtp_port": 587,
echo     "smtp_user": "benainimeroua@gmail.com",
echo     "smtp_password": "Zmjhpprowyj mclyf",
echo     "use_tls": true,
echo     "from_email": "benainimeroua@gmail.com",
echo     "from_name": "IDS Monitoring"
echo }
) > "%EMAIL_CONFIG%"

echo %GREEN%OK%RESET% Email configure : benainimeroua@gmail.com

:: ════════════════════════════════════════════════════════
:: ÉTAPE 9 — Raccourci bureau
:: ════════════════════════════════════════════════════════
echo.
echo %GREEN%[9/11]%RESET% Creation du raccourci sur le bureau...

set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT=%DESKTOP%\IDS_Notifier.lnk"
powershell -Command "$WS=New-Object -ComObject WScript.Shell; $SC=$WS.CreateShortcut('%SHORTCUT%'); $SC.TargetPath='wscript.exe'; $SC.Arguments='\"%RUN_VBS%\"'; $SC.Description='IDS Alert Notifier'; $SC.Save()" 2>nul
if exist "%SHORTCUT%" echo %GREEN%OK%RESET% Raccourci cree sur le bureau.

:: ════════════════════════════════════════════════════════
:: ÉTAPE 10 — Démarrage immédiat du notifier
:: ════════════════════════════════════════════════════════
echo.
echo %GREEN%[10/11]%RESET% Demarrage du notifier en arriere-plan...

taskkill /F /IM pythonw.exe >nul 2>&1
timeout /t 2 /nobreak >nul
wscript "%RUN_VBS%"
timeout /t 3 /nobreak >nul

tasklist /FI "IMAGENAME eq pythonw.exe" 2>nul | find /I "pythonw.exe" >nul
if %errorlevel% equ 0 (
    echo %GREEN%OK%RESET% Notifier demarre en arriere-plan.
) else (
    echo %RED%ERREUR%RESET% Notifier non demarre. Verifiez : %CONFIG_DIR%\notifier.log
)

:: ════════════════════════════════════════════════════════
:: ÉTAPE 11 — Alerte de test
:: ════════════════════════════════════════════════════════
echo.
echo %GREEN%[11/11]%RESET% Envoi d'une alerte de test en base...

set "TEST_ALERT=%TEMP%\ids_create_test_alert.py"
(
echo import psycopg2, json
echo try:
echo     conn = psycopg2.connect(dbname="ids_db",user="aya",password="aya",host="192.168.1.2",port="5432")
echo     cur = conn.cursor()
echo     cur.execute("INSERT INTO alertes (attack_type,source_ip,destination_ip,severity,protocol,timestamp,details) VALUES (%%s,%%s,%%s,%%s,%%s,NOW(),%%s)",("Test Installation - IDS Activee","192.168.1.100","192.168.1.200","basse","TCP",json.dumps({"test":"Notification de test","source":"IDS Notifier v2"})))
echo     conn.commit()
echo     print("OK")
echo     conn.close()
echo except Exception as e:
echo     print(f"NOTE: {e}")
) > "%TEST_ALERT%"
python "%TEST_ALERT%" 2>nul
del "%TEST_ALERT%" 2>nul

:: ════════════════════════════════════════════════════════
:: RÉSUMÉ FINAL
:: ════════════════════════════════════════════════════════
echo.
echo %GREEN%╔══════════════════════════════════════════════════════════════╗%RESET%
echo %GREEN%║              INSTALLATION TERMINEE                          ║%RESET%
echo %GREEN%╚══════════════════════════════════════════════════════════════╝%RESET%
echo.
echo   Base de donnees  : 192.168.1.2:5432 ^| ids_db ^| aya
echo   Notifications    : Actives en arriere-plan (Windows Toast)
echo   Emails admins    : benainimeroua@gmail.com (configure)
echo   Logs             : %CONFIG_DIR%\notifier.log
echo   Config           : %CONFIG_DIR%\notifier.conf
echo   Raccourci        : Bureau -^> IDS_Notifier
echo.
echo   Le notifier surveille la base toutes les 5 secondes.
echo   Il redemarre automatiquement a chaque demarrage Windows.
echo.
pause
exit /b 0