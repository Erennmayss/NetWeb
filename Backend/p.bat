@echo off
:: ============================================================
:: p.bat - Gestionnaire IDS Notifier
:: Configuration entièrement automatique
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
goto :eof


:: ══════════════════════════════════════════════════════════════
:: OPTION 1 — CONFIGURATION DU NOTIFIER (DB + Flask) AUTOMATIQUE
:: ══════════════════════════════════════════════════════════════
:config_notifier
echo.
echo %BLUE%[CONFIGURATION DU NOTIFIER - AUTOMATIQUE]%RESET%
echo.

if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"

:: ── Valeurs automatiques (pas de saisie manuelle) ──────────────────────────
set "db_host=192.168.1.2"
set "db_port=5432"
set "db_name=ids_db"
set "db_user=aya"
set "db_pass=aya"
set "flask_url=http://127.0.0.1:5000"
set "poll_interval=5"

echo %YELLOW%Valeurs utilisees automatiquement :%RESET%
echo    DB Host     : %db_host%
echo    DB Port     : %db_port%
echo    DB Name     : %db_name%
echo    DB User     : %db_user%
echo    Flask URL   : %flask_url%
echo    Intervalle  : %poll_interval%s
echo.

:: ── Sauvegarder la configuration ───────────────────────────────────────────
set "CONF_FILE=%CONFIG_DIR%\notifier.conf"
(
    echo # IDS Notifier Configuration
    echo DB_NAME=%db_name%
    echo DB_USER=%db_user%
    echo DB_PASSWORD=%db_pass%
    echo DB_HOST=%db_host%
    echo DB_PORT=%db_port%
    echo FLASK_URL=%flask_url%
    echo POLL_INTERVAL=%poll_interval%
    echo ENABLE_SOUND=true
    echo MODE=dual
) > "%CONF_FILE%"

(
    echo DB_NAME=%db_name%
    echo DB_USER=%db_user%
    echo DB_PASSWORD=%db_pass%
    echo DB_HOST=%db_host%
    echo DB_PORT=%db_port%
) > "%CONFIG_DIR%\.env"

echo %GREEN%✓%RESET% Configuration sauvegardee dans %CONFIG_DIR%

:: ── Test de connexion DB ────────────────────────────────────────────────────
echo.
echo %YELLOW%Test de connexion a la base de donnees...%RESET%

set "TEST_SCRIPT=%TEMP%\test_db_conn.py"
(
echo import psycopg2
echo try:
echo     conn = psycopg2.connect(dbname="%db_name%",user="%db_user%",password="%db_pass%",host="%db_host%",port="%db_port%",connect_timeout=3)
echo     conn.close()
echo     print("OK")
echo except Exception as e:
echo     print(f"FAIL:{e}")
) > "%TEST_SCRIPT%"

for /f "delims=" %%i in ('python "%TEST_SCRIPT%" 2^>nul') do set "DB_TEST=%%i"
del "%TEST_SCRIPT%" 2>nul

if "%DB_TEST%"=="OK" (
    echo %GREEN%✓%RESET% Connexion DB reussie : %db_host%:%db_port%/%db_name%
) else (
    echo %YELLOW%⚠%RESET% Impossible de se connecter a la DB : %DB_TEST%
    echo    Verifiez que PostgreSQL est accessible sur %db_host%:%db_port%
)

:: ── Test de connexion Flask ─────────────────────────────────────────────────
echo.
echo %YELLOW%Test de connexion a Flask...%RESET%

set "TEST_FLASK=%TEMP%\test_flask_conn.py"
(
echo import urllib.request, urllib.error
echo try:
echo     r = urllib.request.urlopen("%flask_url%/api/health", timeout=3)
echo     print("OK")
echo except Exception as e:
echo     print(f"FAIL:{e}")
) > "%TEST_FLASK%"

for /f "delims=" %%i in ('python "%TEST_FLASK%" 2^>nul') do set "FLASK_TEST=%%i"
del "%TEST_FLASK%" 2>nul

if "%FLASK_TEST%"=="OK" (
    echo %GREEN%✓%RESET% Flask accessible : %flask_url%
) else (
    echo %YELLOW%⚠%RESET% Flask inaccessible : %FLASK_TEST%
    echo    Le notifier surveillera la DB et attendra Flask.
)

echo.
echo %GREEN%================================================================%RESET%
echo %GREEN%  Configuration sauvegardee avec succes%RESET%
echo %GREEN%================================================================%RESET%
echo.
echo    DB      : %db_host%:%db_port%/%db_name% (user: %db_user%)
echo    Flask   : %flask_url%
echo    Logs    : %CONFIG_DIR%\notifier.log
echo    Config  : %CONFIG_DIR%\notifier.conf
echo.
pause
goto :eof


:: ══════════════════════════════════════════════════════════════
:: OPTION 8 — CONFIGURATION EMAIL FIXE (jamais modifiable)
:: ══════════════════════════════════════════════════════════════
:config_email
echo.
echo %BLUE%[CONFIGURATION EMAIL - AUTOMATIQUE]%RESET%
echo.

if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"
set "EMAIL_CONFIG=%CONFIG_DIR%\email_config.json"

:: ── Écrire la config email fixe (toujours la même) ─────────────────────────
(
echo {
echo     "smtp_server": "smtp.gmail.com",
echo     "smtp_port": 587,
echo     "smtp_user": "benainimeroua@gmail.com",
echo     "smtp_password": "Zmjhpprowyimclyf",
echo     "use_tls": true,
echo     "from_email": "benainimeroua@gmail.com",
echo     "from_name": "IDS Monitoring"
echo }
) > "%EMAIL_CONFIG%"

echo %GREEN%✓%RESET% Configuration email appliquee :
echo.
echo    Serveur  : smtp.gmail.com:587
echo    Expediteur: benainimeroua@gmail.com
echo    Nom      : IDS Monitoring
echo    TLS      : active
echo.

:: ── Test d'envoi SMTP ───────────────────────────────────────────────────────
echo %YELLOW%Test de connexion SMTP...%RESET%

set "TEST_SMTP=%TEMP%\test_smtp.py"
(
echo import smtplib
echo try:
echo     s = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
echo     s.ehlo()
echo     s.starttls()
echo     s.ehlo()
echo     s.login("benainimeroua@gmail.com", "Zmjhpprowyimclyf")
echo     s.quit()
echo     print("OK")
echo except Exception as e:
echo     print(f"FAIL:{e}")
) > "%TEST_SMTP%"

for /f "delims=" %%i in ('python "%TEST_SMTP%" 2^>nul') do set "SMTP_TEST=%%i"
del "%TEST_SMTP%" 2>nul

if "%SMTP_TEST%"=="OK" (
    echo %GREEN%✓%RESET% Connexion SMTP reussie - emails prets a etre envoyes
) else (
    echo %YELLOW%⚠%RESET% SMTP : %SMTP_TEST%
    echo    Verifiez la connexion internet et le mot de passe d'application Gmail.
)

echo.
echo %GREEN%================================================================%RESET%
echo %GREEN%  Configuration email sauvegardee avec succes%RESET%
echo %GREEN%================================================================%RESET%
echo.
pause
goto :eof


:: ══════════════════════════════════════════════════════════════
:: FIN
:: ══════════════════════════════════════════════════════════════
:end
echo.
echo %BLUE%Au revoir !%RESET%
echo.
exit /b 0