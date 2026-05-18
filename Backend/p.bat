@echo off
:: ============================================================
:: p.bat - IDS Notifier - Installation automatique
:: Un seul bouton : installe + configure email + démarre
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
:: Définir les chemins dès le départ
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
echo %BLUE%║         🛡️  IDS Alert Notifier - Installation v2.0          ║%RESET%
echo %BLUE%║   Base de données : 192.168.1.2:5432  •  Utilisateur : aya  ║%RESET%
echo %BLUE%╚══════════════════════════════════════════════════════════════╝%RESET%
echo.

:: ── Droits administrateur ─────────────────────────────────────────────────
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%[ERREUR]%RESET% Ce script doit etre execute en tant qu'Administrateur.
    echo Cliquez droit ^> "Executer en tant qu'administrateur"
    pause
    exit /b 1
)

:: ════════════════════════════════════════════════════════
:: BOUTON UNIQUE : Installer le notifier
:: ════════════════════════════════════════════════════════
echo %CYAN%  Appuyez sur une touche pour lancer l'installation complète...%RESET%
echo %CYAN%  (notification en arrière-plan + emails admins)%RESET%
echo.
pause
echo.

:: ════════════════════════════════════════════════════════
:: ÉTAPE 1 — Python
:: ════════════════════════════════════════════════════════
echo %GREEN%[1/11]%RESET% Vérification de Python...
where python >nul 2>&1
if errorlevel 1 (
    echo %RED%[ERREUR]%RESET% Python introuvable dans le PATH.
    echo Téléchargez-le sur https://www.python.org/downloads/
    echo (cochez "Add Python to PATH" lors de l'installation^)
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "PY_VERSION=%%i"
echo %GREEN%✓%RESET% Python %PY_VERSION% détecté.

python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo %YELLOW%⚠%RESET% pip absent — installation en cours...
    python -m ensurepip --upgrade
)

:: ════════════════════════════════════════════════════════
:: ÉTAPE 2 — Test connexion DB
:: ════════════════════════════════════════════════════════
echo.
echo %GREEN%[2/11]%RESET% Test de connexion à la base de données...

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
    echo %GREEN%✓%RESET% Connexion à 192.168.1.2:5432 réussie.
) else (
    echo %YELLOW%⚠%RESET% Base de données inaccessible pour l'instant.
    echo    Le notifier se reconnectera automatiquement dès qu'elle sera disponible.
)

:: ════════════════════════════════════════════════════════
:: ÉTAPE 3 — Dépendances Python
:: ════════════════════════════════════════════════════════
echo.
echo %GREEN%[3/11]%RESET% Installation des dépendances Python...

python -m pip install --upgrade pip --quiet
for %%P in (psycopg2-binary requests flask plyer winotify win10toast-persist winrt) do (
    echo    → %%P
    python -m pip install --quiet %%P
)
echo %GREEN%✓%RESET% Toutes les dépendances installées.

:: ════════════════════════════════════════════════════════
:: ÉTAPE 4 — Scripts VBS (lanceur invisible)
:: ════════════════════════════════════════════════════════
echo.
echo %GREEN%[4/11]%RESET% Création des scripts de lancement...

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

echo %GREEN%✓%RESET% Scripts VBS créés.

:: ════════════════════════════════════════════════════════
:: ÉTAPE 5 — Dossier démarrage Windows
:: ════════════════════════════════════════════════════════
echo.
echo %GREEN%[5/11]%RESET% Ajout au démarrage Windows (dossier Startup)...

if exist "%STARTUP%\IDS_Notifier.vbs" del /Q "%STARTUP%\IDS_Notifier.vbs"
if exist "%STARTUP%\IDS_Notifier.lnk" del /Q "%STARTUP%\IDS_Notifier.lnk"
copy /Y "%RUN_VBS%" "%STARTUP%\IDS_Notifier.vbs" >nul
echo %GREEN%✓%RESET% Démarrage automatique configuré.

:: ════════════════════════════════════════════════════════
:: ÉTAPE 6 — Tâche planifiée (boot SYSTEM)
:: ════════════════════════════════════════════════════════
echo.
echo %GREEN%[6/11]%RESET% Création de la tâche planifiée (boot système)...

schtasks /delete /tn "IDS_Notifier" /f >nul 2>&1
schtasks /create /tn "IDS_Notifier" /tr "wscript.exe \"%RUN_VBS%\"" /sc onstart /delay 0001:00 /ru "SYSTEM" /f >nul 2>&1
if %errorlevel% equ 0 (
    echo %GREEN%✓%RESET% Tâche planifiée créée.
) else (
    echo %YELLOW%⚠%RESET% Tâche planifiée non créée (le notifier démarre via Startup quand même^).
)

:: ════════════════════════════════════════════════════════
:: ÉTAPE 7 — Fichiers de configuration DB
:: ════════════════════════════════════════════════════════
echo.
echo %GREEN%[7/11]%RESET% Écriture de la configuration base de données...

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

echo %GREEN%✓%RESET% Configuration DB écrite dans %CONFIG_DIR%

:: ════════════════════════════════════════════════════════
:: ÉTAPE 8 — Configuration email automatique (OPTION 8 intégrée)
:: ════════════════════════════════════════════════════════
echo.
echo %GREEN%[8/11]%RESET% Configuration de l'envoi d'emails aux admins...
echo.

if exist "%EMAIL_CONFIG%" (
    echo %GREEN%✓%RESET% Configuration email déjà existante — conservée.
    goto :email_done
)

echo %CYAN%  Les emails seront envoyés aux admins (role=admin / security_admin^)%RESET%
echo %CYAN%  depuis la table 'utilisateur' de la base de données.%RESET%
echo.
echo %YELLOW%  Serveurs SMTP courants :%RESET%
echo    Gmail   : smtp.gmail.com       port 587
echo    Outlook : smtp-mail.outlook.com port 587
echo    Yahoo   : smtp.mail.yahoo.com  port 587
echo.
echo %YELLOW%  ⚠  Pour Gmail : utilisez un "Mot de passe d'application" (2FA requis^)%RESET%
echo.

set /p smtp_server="  Serveur SMTP (ex: smtp.gmail.com) : "
set /p smtp_port="  Port SMTP (587 TLS / 465 SSL)      : "
set /p smtp_user="  Email expéditeur                   : "
set /p smtp_password="  Mot de passe / clé d'application   : "
set /p from_name="  Nom affiché (Entrée = IDS Monitoring): "
if "!from_name!"=="" set "from_name=IDS Monitoring System"

(
echo {
echo     "smtp_server": "!smtp_server!",
echo     "smtp_port": !smtp_port!,
echo     "smtp_user": "!smtp_user!",
echo     "smtp_password": "!smtp_password!",
echo     "use_tls": true,
echo     "from_email": "!smtp_user!",
echo     "from_name": "!from_name!"
echo }
) > "%EMAIL_CONFIG%"

echo.
echo %GREEN%✓%RESET% Email configuré : !smtp_user! → admins de la base.
echo %YELLOW%  ⚠  Le mot de passe est stocké en clair — protégez %CONFIG_DIR%%RESET%

:email_done

:: ════════════════════════════════════════════════════════
:: ÉTAPE 9 — Raccourci bureau
:: ════════════════════════════════════════════════════════
echo.
echo %GREEN%[9/11]%RESET% Création d'un raccourci sur le bureau...

set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT=%DESKTOP%\IDS_Notifier.lnk"
powershell -Command "$WS=New-Object -ComObject WScript.Shell; $SC=$WS.CreateShortcut('%SHORTCUT%'); $SC.TargetPath='wscript.exe'; $SC.Arguments='\"%RUN_VBS%\"'; $SC.Description='IDS Alert Notifier'; $SC.Save()" 2>nul
if exist "%SHORTCUT%" echo %GREEN%✓%RESET% Raccourci créé sur le bureau.

:: ════════════════════════════════════════════════════════
:: ÉTAPE 10 — Démarrage immédiat du notifier en arrière-plan
:: ════════════════════════════════════════════════════════
echo.
echo %GREEN%[10/11]%RESET% Démarrage du notifier en arrière-plan...

taskkill /F /IM pythonw.exe >nul 2>&1
timeout /t 2 /nobreak >nul
wscript "%RUN_VBS%"
timeout /t 3 /nobreak >nul

tasklist /FI "IMAGENAME eq pythonw.exe" 2>nul | find /I "pythonw.exe" >nul
if %errorlevel% equ 0 (
    echo %GREEN%✓%RESET% Notifier démarré en arrière-plan (notifications + emails admins^).
) else (
    echo %RED%✗%RESET% Notifier non démarré. Vérifiez : %CONFIG_DIR%\notifier.log
)

:: ════════════════════════════════════════════════════════
:: ÉTAPE 11 — Alerte de test dans la base
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
echo %GREEN%║              ✅  INSTALLATION TERMINÉE ✅                   ║%RESET%
echo %GREEN%╚══════════════════════════════════════════════════════════════╝%RESET%
echo.
echo   📡 Base de données  : 192.168.1.2:5432 ^| ids_db ^| aya
echo   🔔 Notifications    : Actives en arrière-plan (Windows Toast^)
if exist "%EMAIL_CONFIG%" (
    echo   📧 Emails admins    : Configurés ✅
) else (
    echo   📧 Emails admins    : Non configurés
)
echo   📁 Logs             : %CONFIG_DIR%\notifier.log
echo   📁 Config           : %CONFIG_DIR%\notifier.conf
echo   🖥️  Raccourci        : Bureau → IDS_Notifier
echo.
echo   Le notifier surveille la base toutes les 5 secondes.
echo   Il redémarre automatiquement à chaque démarrage Windows.
echo.
pause



exit /b 0