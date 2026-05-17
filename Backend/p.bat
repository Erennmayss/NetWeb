@echo off
:: ============================================================
:: p.bat - Gestionnaire IDS Notifier
:: Options : [1] Configurer  [8] Configurer emails  [0] Quitter
:: ============================================================

setlocal enabledelayedexpansion

set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "BLUE=[94m"
set "RESET=[0m"

title IDS Notifier v2.1 - Configuration

echo.
echo %BLUE%================================================================%RESET%
echo %BLUE%    IDS Alert Notifier - Windows v2.1%RESET%
echo %BLUE%================================================================%RESET%
echo.

:: ── Vérifier les droits administrateur ─────────────────────────────────────
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%[ERREUR]%RESET% Ce script doit etre execute en tant qu'Administrateur
    echo.
    echo Cliquez droit sur le fichier ^> "Executer en tant qu'administrateur"
    pause
    exit /b 1
)

:: ── Définir les chemins ─────────────────────────────────────────────────────
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "NOTIFIER=%SCRIPT_DIR%\notifier.py"
set "CONFIG_DIR=%APPDATA%\IDS_Notifier"

:: ── Menu principal ──────────────────────────────────────────────────────────
:menu
echo.
echo %BLUE% Que souhaitez-vous faire ?%RESET%
echo.
echo    [1] Configurer le notifier (DB + Flask)
echo    [8] Configurer les emails (administrateurs)
echo    [0] Quitter
echo.
set /p choice="Votre choix: "

if "%choice%"=="1" goto config_notifier
if "%choice%"=="8" goto config_email
if "%choice%"=="0" goto end
echo %RED%Choix invalide%RESET%
goto menu


:: ══════════════════════════════════════════════════════════════
:: OPTION 1 — CONFIGURATION DU NOTIFIER (DB + Flask)
:: ══════════════════════════════════════════════════════════════
:config_notifier
echo.
echo %BLUE%[CONFIGURATION DU NOTIFIER]%RESET%
echo.

if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"

:: ── Afficher la configuration actuelle si elle existe ──────────────────────
set "CONF_FILE=%CONFIG_DIR%\notifier.conf"
if exist "%CONF_FILE%" (
    echo %GREEN%Configuration actuelle :%RESET%
    echo.
    type "%CONF_FILE%"
    echo.
    set /p modify="Modifier la configuration (O/N) ? "
    if /i not "!modify!"=="O" goto menu
    echo.
)

:: ── Saisie de la configuration DB ──────────────────────────────────────────
echo %YELLOW%--- Base de donnees PostgreSQL ---%RESET%
echo.
set /p db_host="Hote DB (ex: 192.168.1.2): "
if "!db_host!"=="" set "db_host=192.168.1.2"

set /p db_port="Port DB (defaut 5432): "
if "!db_port!"=="" set "db_port=5432"

set /p db_name="Nom de la base (ex: ids_db): "
if "!db_name!"=="" set "db_name=ids_db"

set /p db_user="Utilisateur DB: "
if "!db_user!"=="" set "db_user=aya"

set /p db_pass="Mot de passe DB: "
if "!db_pass!"=="" set "db_pass=aya"

echo.
echo %YELLOW%--- API Flask ---%RESET%
echo.
set /p flask_url="URL Flask (defaut http://127.0.0.1:5000): "
if "!flask_url!"=="" set "flask_url=http://127.0.0.1:5000"

set /p poll_interval="Intervalle de polling en secondes (defaut 5): "
if "!poll_interval!"=="" set "poll_interval=5"

:: ── Sauvegarder la configuration ───────────────────────────────────────────
(
    echo # IDS Notifier Configuration
    echo DB_NAME=!db_name!
    echo DB_USER=!db_user!
    echo DB_PASSWORD=!db_pass!
    echo DB_HOST=!db_host!
    echo DB_PORT=!db_port!
    echo FLASK_URL=!flask_url!
    echo POLL_INTERVAL=!poll_interval!
    echo ENABLE_SOUND=true
    echo MODE=dual
) > "%CONF_FILE%"

(
    echo DB_NAME=!db_name!
    echo DB_USER=!db_user!
    echo DB_PASSWORD=!db_pass!
    echo DB_HOST=!db_host!
    echo DB_PORT=!db_port!
) > "%CONFIG_DIR%\.env"

echo.
echo %GREEN%✓%RESET% Configuration sauvegardee dans %CONFIG_DIR%

:: ── Test de connexion DB ────────────────────────────────────────────────────
echo.
echo %YELLOW%Test de connexion a la base de donnees...%RESET%

set "TEST_SCRIPT=%TEMP%\test_db_conn.py"
(
echo import psycopg2
echo try:
echo     conn = psycopg2.connect(dbname="!db_name!",user="!db_user!",password="!db_pass!",host="!db_host!",port="!db_port!",connect_timeout=3)
echo     conn.close()
echo     print("OK")
echo except Exception as e:
echo     print(f"FAIL:{e}")
) > "%TEST_SCRIPT%"

for /f "delims=" %%i in ('python "%TEST_SCRIPT%" 2^>nul') do set "DB_TEST=%%i"
del "%TEST_SCRIPT%" 2>nul

if "!DB_TEST!"=="OK" (
    echo %GREEN%✓%RESET% Connexion DB reussie : !db_host!:!db_port!/!db_name!
) else (
    echo %YELLOW%⚠%RESET% Impossible de se connecter a la DB : !DB_TEST!
    echo    Verifiez les parametres et que PostgreSQL est accessible.
)

:: ── Test de connexion Flask ─────────────────────────────────────────────────
echo.
echo %YELLOW%Test de connexion a Flask...%RESET%

set "TEST_FLASK=%TEMP%\test_flask_conn.py"
(
echo import urllib.request, urllib.error
echo try:
echo     r = urllib.request.urlopen("!flask_url!/api/health", timeout=3)
echo     print("OK")
echo except Exception as e:
echo     print(f"FAIL:{e}")
) > "%TEST_FLASK%"

for /f "delims=" %%i in ('python "%TEST_FLASK%" 2^>nul') do set "FLASK_TEST=%%i"
del "%TEST_FLASK%" 2>nul

if "!FLASK_TEST!"=="OK" (
    echo %GREEN%✓%RESET% Flask accessible : !flask_url!
) else (
    echo %YELLOW%⚠%RESET% Flask inaccessible : !FLASK_TEST!
    echo    Le notifier surveillera la DB et attendra Flask.
)

echo.
echo %GREEN%================================================================%RESET%
echo %GREEN%  Configuration sauvegardee avec succes%RESET%
echo %GREEN%================================================================%RESET%
echo.
echo    DB      : !db_host!:!db_port!/!db_name! (user: !db_user!)
echo    Flask   : !flask_url!
echo    Logs    : %CONFIG_DIR%\notifier.log
echo    Config  : %CONFIG_DIR%\notifier.conf
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

if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"
set "EMAIL_CONFIG=%CONFIG_DIR%\email_config.json"

if exist "%EMAIL_CONFIG%" (
    echo %GREEN%✓%RESET% Configuration email existante :
    echo.
    type "%EMAIL_CONFIG%"
    echo.
    echo    [1] Modifier
    echo    [2] Supprimer
    echo    [0] Retour
    echo.
    set /p email_choice="Choix (1/2/0): "
    if "!email_choice!"=="1" goto edit_email_config
    if "!email_choice!"=="2" (
        del /Q "%EMAIL_CONFIG%" 2>nul
        echo %GREEN%Configuration email supprimee%RESET%
        pause
        goto menu
    )
    if "!email_choice!"=="0" goto menu
    goto menu
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
echo %YELLOW%Pour Gmail, utilisez un "Mot de passe d'application" (2FA active)%RESET%
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
echo %YELLOW%Le mot de passe est stocke en clair — protegez l'acces a ce dossier.%RESET%
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