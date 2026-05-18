@echo off
:: ============================================================
:: p.bat - IDS Notifier - Execution 100% automatique
:: Usage depuis Flask : p.bat 1   ou   p.bat 8
:: Aucune saisie utilisateur - tout est pre-configure
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
echo %BLUE% Que souhaitez-vous faire ?%RESET%
echo.
echo    [1] Configurer le notifier (DB + Flask)
echo    [8] Configurer les emails (administrateurs)
echo    [0] Quitter
echo.

:: ── Definir les chemins
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "NOTIFIER=%SCRIPT_DIR%\notifier.py"
set "CONFIG_DIR=%APPDATA%\IDS_Notifier"

:: ── Choix automatique via argument passe par Flask (p.bat 1 ou p.bat 8)
set "choice=%~1"

if "%choice%"=="" (
    echo Votre choix: [automatique - configuration complete]
    echo.
    call :do_config_notifier
    call :do_config_email
    goto :fin
)

echo Votre choix: %choice%
echo.

if "%choice%"=="1" ( call :do_config_notifier & goto :fin )
if "%choice%"=="8" ( call :do_config_email    & goto :fin )
if "%choice%"=="0" ( goto :fin )

echo %RED%Argument invalide : %choice%%RESET%
goto :fin


:: ============================================================
:: OPTION 1 - Configuration DB + Flask (valeurs fixes)
:: ============================================================
:do_config_notifier
echo.
echo %BLUE%[CONFIGURATION DU NOTIFIER]%RESET%
echo.

if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"

set "db_host=192.168.1.2"
set "db_port=5432"
set "db_name=ids_db"
set "db_user=aya"
set "db_pass=aya"
set "flask_url=http://127.0.0.1:5000"
set "poll_interval=5"

echo %YELLOW%Valeurs appliquees automatiquement :%RESET%
echo    DB Host    : %db_host%
echo    DB Port    : %db_port%
echo    DB Name    : %db_name%
echo    DB User    : %db_user%
echo    Flask URL  : %flask_url%
echo    Intervalle : %poll_interval%s
echo.

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
) > "%CONFIG_DIR%\notifier.conf"

(
    echo DB_NAME=%db_name%
    echo DB_USER=%db_user%
    echo DB_PASSWORD=%db_pass%
    echo DB_HOST=%db_host%
    echo DB_PORT=%db_port%
) > "%CONFIG_DIR%\.env"

echo %GREEN%[OK]%RESET% notifier.conf et .env sauvegardes

call :do_write_email_json

echo.
echo %YELLOW%Test connexion DB...%RESET%
set "T=%TEMP%\ids_db.py"
(
echo import psycopg2,sys
echo try:
echo  c=psycopg2.connect(dbname="%db_name%",user="%db_user%",password="%db_pass%",host="%db_host%",port="%db_port%",connect_timeout=3)
echo  c.close();print("OK")
echo except Exception as e:print(f"FAIL:{e}")
) > "%T%"
for /f "delims=" %%i in ('python "%T%" 2^>nul') do set "DBR=%%i"
del "%T%" 2>nul
if "!DBR!"=="OK" ( echo %GREEN%[OK]%RESET% DB connectee : %db_host%:%db_port%/%db_name%
) else ( echo %YELLOW%[AV]%RESET% DB : !DBR! )

echo.
echo %YELLOW%Test connexion Flask...%RESET%
set "T=%TEMP%\ids_flask.py"
(
echo import urllib.request,sys
echo try:
echo  urllib.request.urlopen("%flask_url%/api/health",timeout=3);print("OK")
echo except Exception as e:print(f"FAIL:{e}")
) > "%T%"
for /f "delims=" %%i in ('python "%T%" 2^>nul') do set "FLR=%%i"
del "%T%" 2>nul
if "!FLR!"=="OK" ( echo %GREEN%[OK]%RESET% Flask accessible : %flask_url%
) else ( echo %YELLOW%[AV]%RESET% Flask : !FLR! )

echo.
echo %GREEN%================================================================%RESET%
echo %GREEN%  Configuration DB+Flask terminee%RESET%
echo %GREEN%================================================================%RESET%
echo    DB     : %db_host%:%db_port%/%db_name%
echo    Flask  : %flask_url%
echo    Config : %CONFIG_DIR%\notifier.conf
echo.
goto :eof


:: ============================================================
:: OPTION 8 - Email fixe (jamais modifiable)
:: ============================================================
:do_config_email
echo.
echo %BLUE%[CONFIGURATION EMAIL]%RESET%
echo.

if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"

call :do_write_email_json

echo %GREEN%[OK]%RESET% Configuration email appliquee :
echo.
echo    Serveur    : smtp.gmail.com:587
echo    Expediteur : benainimeroua@gmail.com
echo    Nom        : IDS Monitoring
echo    TLS        : active
echo.

echo %YELLOW%Test SMTP Gmail...%RESET%
set "T=%TEMP%\ids_smtp.py"
(
echo import smtplib
echo try:
echo  s=smtplib.SMTP("smtp.gmail.com",587,timeout=10)
echo  s.ehlo();s.starttls();s.ehlo()
echo  s.login("benainimeroua@gmail.com","ZmjhpproWyjmclyf")
echo  s.quit();print("OK")
echo except Exception as e:print(f"FAIL:{e}")
) > "%T%"
for /f "delims=" %%i in ('python "%T%" 2^>nul') do set "SR=%%i"
del "%T%" 2>nul
if "!SR!"=="OK" ( echo %GREEN%[OK]%RESET% Gmail SMTP OK
) else ( echo %YELLOW%[AV]%RESET% SMTP : !SR! )

echo.
echo %GREEN%================================================================%RESET%
echo %GREEN%  Configuration email terminee%RESET%
echo %GREEN%================================================================%RESET%
echo.
goto :eof


:: ── Ecrire email_config.json (sous-routine partagee)
:do_write_email_json
(
echo {
echo     "smtp_server": "smtp.gmail.com",
echo     "smtp_port": 587,
echo     "smtp_user": "benainimeroua@gmail.com",
echo     "smtp_password": "ZmjhpproWyjmclyf",
echo     "use_tls": true,
echo     "from_email": "benainimeroua@gmail.com",
echo     "from_name": "IDS Monitoring"
echo }
) > "%CONFIG_DIR%\email_config.json"
goto :eof


:: ============================================================
:fin
echo.
echo %BLUE%Au revoir !%RESET%
echo.
exit /b 0