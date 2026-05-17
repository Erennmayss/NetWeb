@echo off
:: ============================================================
:: p.bat - Gestionnaire IDS Notifier
:: Options : [1] Installer  [8] Configurer emails  [0] Quitter
:: ============================================================

setlocal enabledelayedexpansion

set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "BLUE=[94m"
set "RESET=[0m"

title IDS Notifier

echo.
echo %BLUE%================================================================%RESET%
echo %BLUE%    🛡️  IDS Alert Notifier - Windows v2.0%RESET%
echo %BLUE%    📧  Notification email aux administrateurs incluse%RESET%
echo %BLUE%================================================================%RESET%
echo.

:: ── 1. Vérifier les droits administrateur ──────────────────────────────────
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%[ERREUR]%RESET% Ce script doit etre execute en tant qu'Administrateur
    echo.
    echo Cliquez droit sur le fichier ^> "Executer en tant qu'administrateur"
    pause
    exit /b 1
)

:: ── 2. Définir les chemins ─────────────────────────────────────────────────
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "NOTIFIER=%SCRIPT_DIR%\notifier.py"
set "RUN_VBS=%SCRIPT_DIR%\run_notifier.vbs"
set "STOP_VBS=%SCRIPT_DIR%\stop_notifier.vbs"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

:: ── 3. Menu principal ──────────────────────────────────────────────────────
:menu
echo.
echo %BLUE% Que souhaitez-vous faire ?%RESET%
echo.
echo    [1] Installer/Reinstaller le notifier
echo    [8] Configurer les emails (administrateurs)
echo    [0] Quitter
echo.
set /p choice="Votre choix: "

if "%choice%"=="1" goto install
if "%choice%"=="8" goto config_email
if "%choice%"=="0" goto end
echo %RED%Choix invalide%RESET%
goto menu


:: ══════════════════════════════════════════════════════════════
:: OPTION 1 — INSTALLATION
:: ══════════════════════════════════════════════════════════════
:install
echo.
echo %BLUE%[CONFIGURATION BASE DE DONNEES]%RESET%
echo.
echo Entrez les parametres de connexion a votre base PostgreSQL.
echo (Appuyez sur Entree pour garder la valeur entre parentheses)
echo.

:: Lire config existante si elle existe
set "CONFIG_DIR_TEMP=%APPDATA%\IDS_Notifier"
set "_DEF_HOST=localhost"
set "_DEF_PORT=5432"
set "_DEF_NAME=ids_db"
set "_DEF_USER="
set "_DEF_PASS="

if exist "%CONFIG_DIR_TEMP%\.env" (
    for /f "tokens=1,* delims==" %%A in (%CONFIG_DIR_TEMP%\.env) do (
        if "%%A"=="DB_HOST"     set "_DEF_HOST=%%B"
        if "%%A"=="DB_PORT"     set "_DEF_PORT=%%B"
        if "%%A"=="DB_NAME"     set "_DEF_NAME=%%B"
        if "%%A"=="DB_USER"     set "_DEF_USER=%%B"
        if "%%A"=="DB_PASSWORD" set "_DEF_PASS=%%B"
    )
)

set /p DB_HOST="  Hote PostgreSQL [!_DEF_HOST!]: "
if "!DB_HOST!"=="" set "DB_HOST=!_DEF_HOST!"

set /p DB_PORT="  Port            [!_DEF_PORT!]: "
if "!DB_PORT!"=="" set "DB_PORT=!_DEF_PORT!"

set /p DB_NAME="  Nom de la base  [!_DEF_NAME!]: "
if "!DB_NAME!"=="" set "DB_NAME=!_DEF_NAME!"

set /p DB_USER="  Utilisateur     [!_DEF_USER!]: "
if "!DB_USER!"=="" set "DB_USER=!_DEF_USER!"

set /p DB_PASS="  Mot de passe    : "
if "!DB_PASS!"=="" set "DB_PASS=!_DEF_PASS!"

echo.
echo %GREEN%✓%RESET% Parametres DB : !DB_HOST!:!DB_PORT! / !DB_NAME! / user: !DB_USER!
echo.

echo.
echo %GREEN%[1/11]%RESET% Verification de l'environnement Python...

where python >nul 2>&1
if errorlevel 1 (
    echo %RED%[ERREUR]%RESET% Python non trouve dans le PATH
    echo.
    echo Telechargez Python depuis: https://www.python.org/downloads/
    echo N'OUBLIEZ PAS de cocher "Add Python to PATH" lors de l'installation
    pause
    goto menu
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "PY_VERSION=%%i"
echo %GREEN%✓%RESET% Python %PY_VERSION% trouve

python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo %RED%[ERREUR]%RESET% Pip non trouve, installation...
    python -m ensurepip --upgrade
)

echo.
echo %GREEN%[2/11]%RESET% Test de connexion a la base de donnees...

set "TEST_SCRIPT=%TEMP%\test_db.py"
(
echo import psycopg2
echo try:
echo     conn = psycopg2.connect(
echo         dbname="!DB_NAME!",
echo         user="!DB_USER!",
echo         password="!DB_PASS!",
echo         host="!DB_HOST!",
echo         port="!DB_PORT!",
echo         connect_timeout=3
echo     )
echo     conn.close()
echo     print("OK")
echo except:
echo     print("FAIL")
) > "%TEST_SCRIPT%"

for /f "delims=" %%i in ('python "%TEST_SCRIPT%" 2^>nul') do set "DB_TEST=%%i"
del "%TEST_SCRIPT%" 2>nul

if "%DB_TEST%"=="OK" (
    echo %GREEN%✓%RESET% Connexion a la base de donnees reussie
) else (
    echo %YELLOW%⚠%RESET% Attention: Impossible de se connecter a la base de donnees
    echo.
    echo    Verifiez que PostgreSQL est accessible sur !DB_HOST!:!DB_PORT!
    echo    Le notifier demarrera quand meme mais ne pourra pas recuperer les alertes
    echo.
    set /p continue="Continuer quand meme (O/N) ? "
    if /i not "!continue!"=="O" goto menu
)

echo.
echo %GREEN%[3/11]%RESET% Installation des dependances Python...
echo.

python -m pip install --upgrade pip --quiet
echo Installation de psycopg2-binary...
python -m pip install --quiet psycopg2-binary
echo Installation de requests...
python -m pip install --quiet requests
echo Installation de plyer...
python -m pip install --quiet plyer
echo Installation de winotify...
python -m pip install --quiet winotify
echo Installation de win10toast-persist...
python -m pip install --quiet win10toast-persist
echo Installation de winrt...
python -m pip install --quiet winrt
echo %GREEN%✓%RESET% Toutes les dependances sont installees

echo.
echo %GREEN%[4/11]%RESET% Creation des scripts de lancement...

(
    echo ' IDS Notifier - Launcher (invisible^)
    echo Set oWS = WScript.CreateObject^("WScript.Shell"^)
    echo sFile = "%NOTIFIER:\=\\%"
    echo sCmd = "pythonw """ ^& sFile ^& """ --db --interval 5 --sound"
    echo oWS.Run sCmd, 0, False
    echo WScript.Sleep 2000
) > "%RUN_VBS%"

(
    echo ' IDS Notifier - Stopper le processus
    echo Set oWS = WScript.CreateObject^("WScript.Shell"^)
    echo oWS.Run "taskkill /F /IM pythonw.exe", 0, False
    echo WScript.Sleep 1000
) > "%STOP_VBS%"

echo %GREEN%✓%RESET% Scripts crees

echo.
echo %GREEN%[5/11]%RESET% Ajout au demarrage Windows...

if exist "%STARTUP%\IDS_Notifier.vbs" del /Q "%STARTUP%\IDS_Notifier.vbs"
if exist "%STARTUP%\IDS_Notifier.lnk" del /Q "%STARTUP%\IDS_Notifier.lnk"
copy /Y "%RUN_VBS%" "%STARTUP%\IDS_Notifier.vbs" >nul
echo %GREEN%✓%RESET% Ajoute au dossier Demarrage

echo.
echo %GREEN%[6/11]%RESET% Creation d'une tache planifiee...

schtasks /delete /tn "IDS_Notifier" /f >nul 2>&1
schtasks /create /tn "IDS_Notifier" /tr "wscript.exe \"%RUN_VBS%\"" /sc onstart /delay 0001:00 /ru "SYSTEM" /f >nul 2>&1
if %errorlevel% equ 0 (
    echo %GREEN%✓%RESET% Tache planifiee creee (demarrage au boot)
) else (
    echo %YELLOW%⚠%RESET% Impossible de creer la tache planifiee
    echo    Le notifier demarrera via le dossier Demarrage uniquement
)

echo.
echo %GREEN%[7/11]%RESET% Configuration de la base de donnees...

set "CONFIG_DIR=%APPDATA%\IDS_Notifier"
if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"

(
    echo # IDS Notifier Configuration
    echo DB_NAME=!DB_NAME!
    echo DB_USER=!DB_USER!
    echo DB_PASSWORD=!DB_PASS!
    echo DB_HOST=!DB_HOST!
    echo DB_PORT=!DB_PORT!
    echo POLL_INTERVAL=5
    echo ENABLE_SOUND=true
    echo MODE=db_direct
) > "%CONFIG_DIR%\notifier.conf"

(
    echo DB_NAME=!DB_NAME!
    echo DB_USER=!DB_USER!
    echo DB_PASSWORD=!DB_PASS!
    echo DB_HOST=!DB_HOST!
    echo DB_PORT=!DB_PORT!
) > "%CONFIG_DIR%\.env"

echo %GREEN%✓%RESET% Configuration creee dans %CONFIG_DIR%

echo.
echo %GREEN%[8/11]%RESET% Configuration email...

set "EMAIL_CONFIG=%CONFIG_DIR%\email_config.json"
if not exist "%EMAIL_CONFIG%" (
    echo %YELLOW%⚠%RESET% Aucune configuration email trouvee
    echo.
    echo Souhaitez-vous configurer l'envoi d'emails maintenant ?
    echo.
    set /p config_email_now="Configurer email (O/N) ? "
    if /i "!config_email_now!"=="O" (
        call :config_email
    ) else (
        echo.
        echo %YELLOW%Vous pourrez configurer les emails plus tard via l'option 8%RESET%
        echo.
    )
) else (
    echo %GREEN%✓%RESET% Configuration email existante
)

echo.
echo %GREEN%[9/11]%RESET% Creation des raccourcis...

set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT=%DESKTOP%\IDS_Notifier.lnk"
powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%SHORTCUT%'); $SC.TargetPath = 'wscript.exe'; $SC.Arguments = '\"%RUN_VBS%\"'; $SC.Description = 'IDS Alert Notifier'; $SC.Save()" 2>nul
if exist "%SHORTCUT%" echo %GREEN%✓%RESET% Raccourci cree sur le bureau

echo.
echo %GREEN%[10/11]%RESET% Demarrage immediat du notifier...

taskkill /F /IM pythonw.exe >nul 2>&1
timeout /t 2 /nobreak >nul
wscript "%RUN_VBS%"

timeout /t 3 /nobreak >nul
tasklist /FI "IMAGENAME eq pythonw.exe" 2>nul | find /I "pythonw.exe" >nul
if %errorlevel% equ 0 (
    echo %GREEN%✓%RESET% Notifier demarre avec succes en arriere-plan
) else (
    echo %RED%✗%RESET% Erreur: Le notifier n'a pas demarre
    echo    Verifiez les logs: %CONFIG_DIR%\notifier.log
)

echo.
echo %GREEN%[11/11]%RESET% Alerte de test dans la base...

set "TEST_ALERT=%TEMP%\create_test_alert.py"
(
echo import psycopg2, json
echo try:
echo     conn = psycopg2.connect(dbname="!DB_NAME!",user="!DB_USER!",password="!DB_PASS!",host="!DB_HOST!",port="!DB_PORT!")
echo     cur = conn.cursor()
echo     cur.execute("""INSERT INTO alertes (attack_type,source_ip,destination_ip,severity,protocol,timestamp,details) VALUES (%%s,%%s,%%s,%%s,%%s,NOW(),%%s)""",("Test Installation - IDS Activee","192.168.1.100","192.168.1.200","low","TCP",json.dumps({"test":"Notification de test","source":"IDS Notifier"})))
echo     conn.commit()
echo     print("Alerte de test creee")
echo     conn.close()
echo except Exception as e:
echo     print(f"Note: {e}")
) > "%TEST_ALERT%"
python "%TEST_ALERT%" 2>nul
del "%TEST_ALERT%" 2>nul

echo.
echo %GREEN%================================================================%RESET%
echo %GREEN%              ✅ INSTALLATION REUSSIE ✅%RESET%
echo %GREEN%================================================================%RESET%
echo.
echo 📡 Base de donnees : !DB_HOST!:!DB_PORT! ^| !DB_NAME! ^| user: !DB_USER!
echo 📁 Logs            : %CONFIG_DIR%\notifier.log
echo 📁 Config          : %CONFIG_DIR%\notifier.conf
if exist "%EMAIL_CONFIG%" (
    echo 📧 Email           : Configure ✅
) else (
    echo 📧 Email           : Non configure ^(option 8^)
)
echo.
pause
goto menu


:: ══════════════════════════════════════════════════════════════
:: OPTION 8 — CONFIGURATION EMAIL
:: ══════════════════════════════════════════════════════════════
:config_email
echo.
echo %BLUE%[CONFIGURATION EMAIL]%RESET%
echo.
echo Les emails seront envoyes aux utilisateurs avec role='admin'
echo ou role='security_admin' et un email valide dans la table 'utilisateur'.
echo.

set "CONFIG_DIR=%APPDATA%\IDS_Notifier"
if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"
set "EMAIL_CONFIG=%CONFIG_DIR%\email_config.json"

if exist "%EMAIL_CONFIG%" (
    echo %GREEN%✓%RESET% Configuration email existante :
    echo.
    type "%EMAIL_CONFIG%"
    echo.
    echo Souhaitez-vous la modifier ?
    echo    [1] Modifier
    echo    [2] Supprimer
    echo    [3] Retour
    echo.
    set /p email_choice="Choix (1-3): "
    if "!email_choice!"=="1" goto edit_email_config
    if "!email_choice!"=="2" (
        del /Q "%EMAIL_CONFIG%" 2>nul
        echo %GREEN%Configuration email supprimee%RESET%
        pause
        goto menu
    )
    if "!email_choice!"=="3" goto menu
)

:edit_email_config
echo.
echo %YELLOW%Configuration SMTP%RESET%
echo.
echo Exemples de serveurs SMTP :
echo    Gmail   : smtp.gmail.com:587
echo    Outlook : smtp-mail.outlook.com:587
echo    Yahoo   : smtp.mail.yahoo.com:587
echo    Orange  : smtp.orange.fr:465
echo.
echo %YELLOW%⚠️  Pour Gmail, utilisez un "Mot de passe d'application" (2FA active)%RESET%
echo.
set /p smtp_server="Serveur SMTP (ex: smtp.gmail.com): "
set /p smtp_port="Port SMTP (587 pour TLS, 465 pour SSL): "
set /p smtp_user="Email expediteur: "
set /p smtp_password="Mot de passe / Cle d'application: "
set /p from_name="Nom affiche (ex: IDS Monitoring): "
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
echo %GREEN%✓%RESET% Configuration email sauvegardee dans %EMAIL_CONFIG%
echo.
echo %YELLOW%⚠️  Le mot de passe est stocke en clair — protegez l'acces a ce dossier.%RESET%
echo.
pause
goto menu


:: ══════════════════════════════════════════════════════════════
:: FIN
:: ══════════════════════════════════════════════════════════════
:end
echo.
echo %BLUE%Au revoir !%RESET%
echo.
exit /b 0