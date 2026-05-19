@echo off
REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════
REM    IDS NOTIFIER - TEST RAPIDE
REM    Valide l'installation et teste les notifications
REM ═══════════════════════════════════════════════════════════════════════════════════════════════════════

setlocal enabledelayedexpansion

set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "BLUE=[94m"
set "RESET=[0m"

title IDS Notifier - Test Rapide

echo.
echo %BLUE%═══════════════════════════════════════════════════════════════════════════════════════════════════════%RESET%
echo %BLUE%   🧪 IDS ALERT NOTIFIER - TEST RAPIDE%RESET%
echo %BLUE%═══════════════════════════════════════════════════════════════════════════════════════════════════════%RESET%
echo.

REM ───────────────────────────────────────────────────────────────────────────────────────────────────────
REM TEST 1 : Python
REM ───────────────────────────────────────────────────────────────────────────────────────────────────────
echo %BLUE%[1/7] Test Python...%RESET%

where python >nul 2>&1
if errorlevel 1 (
    echo %RED%✗ Python introuvable%RESET%
    goto :end_error
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "PY_VERSION=%%i"
echo %GREEN%✓ Python %PY_VERSION%OK%RESET%
echo.

REM ───────────────────────────────────────────────────────────────────────────────────────────────────────
REM TEST 2 : Dépendances
REM ───────────────────────────────────────────────────────────────────────────────────────────────────────
echo %BLUE%[2/7] Test des dépendances Python...%RESET%

python -c "import psycopg2" 2>nul
if errorlevel 1 (
    echo %RED%✗ psycopg2 introuvable%RESET%
    echo   → Installez: pip install psycopg2-binary
    goto :end_error
)
echo %GREEN%✓ psycopg2%RESET%

python -c "import requests" 2>nul
if errorlevel 1 (
    echo %RED%✗ requests introuvable%RESET%
    goto :end_error
)
echo %GREEN%✓ requests%RESET%

python -c "import winotify" 2>nul
if errorlevel 1 (
    echo %RED%✗ winotify introuvable%RESET%
    goto :end_error
)
echo %GREEN%✓ winotify%RESET%

echo.

REM ───────────────────────────────────────────────────────────────────────────────────────────────────────
REM TEST 3 : Supabase
REM ───────────────────────────────────────────────────────────────────────────────────────────────────────
echo %BLUE%[3/7] Test connexion Supabase...%RESET%

set "TEST_DB=%TEMP%\test_supabase_quick.py"
(
    echo import os, json
    echo from urllib.parse import urlparse
    echo try:
    echo     with open('.env', 'r') as f:
    echo         for line in f:
    echo             if line.startswith('DATABASE_URL='):
    echo                 db_url = line.split('=', 1)[1].strip()
    echo                 break
    echo     import psycopg2
    echo     parsed = urlparse(db_url)
    echo     conn = psycopg2.connect(dbname=parsed.path.lstrip('/') or 'postgres',
    echo                             user=parsed.username, password=parsed.password,
    echo                            host=parsed.hostname, port=5432, sslmode='require',
    echo                             connect_timeout=3)
    echo     conn.close()
    echo     print('OK')
    echo except Exception as e:
    echo     print(f'FAIL:{e}')
) > "%TEST_DB%"

cd Backend
for /f "delims=" %%i in ('python "%TEST_DB%" 2^>nul') do set "DB_TEST=%%i"
cd ..

if "!DB_TEST:~0,2!"=="OK" (
    echo %GREEN%✓ Supabase accessible%RESET%
) else (
    echo %YELLOW%⚠️  Impossible de se connecter à Supabase%RESET%
    echo   → Vérifiez la connexion Internet et .env
)
del "%TEST_DB%" 2>nul
echo.

REM ───────────────────────────────────────────────────────────────────────────────────────────────────────
REM TEST 4 : Email Config
REM ───────────────────────────────────────────────────────────────────────────────────────────────────────
echo %BLUE%[4/7] Test configuration email...%RESET%

set "CONFIG_DIR=%APPDATA%\IDS_Notifier"
set "EMAIL_CONFIG=%CONFIG_DIR%\email_config.json"

if exist "%EMAIL_CONFIG%" (
    echo %GREEN%✓ Configuration email trouvée%RESET%
    python -c "import json; f=open(r'%EMAIL_CONFIG%'); cfg=json.load(f); print(f'   SMTP: {cfg.get(\"smtp_server\")}'); print(f'   From: {cfg.get(\"from_email\")}')"
) else (
    echo %YELLOW%⚠️  Configuration email non trouvée%RESET%
    echo   → Lancez p_auto.bat pour configurer
)
echo.

REM ───────────────────────────────────────────────────────────────────────────────────────────────────────
REM TEST 5 : Notifier files
REM ───────────────────────────────────────────────────────────────────────────────────────────────────────
echo %BLUE%[5/7] Test fichiers notifier...%RESET%

cd Backend
if exist notifier_advanced.py (
    echo %GREEN%✓ notifier_advanced.py%RESET%
) else (
    echo %RED%✗ notifier_advanced.py manquant%RESET%
)

if exist snort_alert_processor.py (
    echo %GREEN%✓ snort_alert_processor.py%RESET%
) else (
    echo %RED%✗ snort_alert_processor.py manquant%RESET%
)

if exist Snort\Recuperation.py (
    echo %GREEN%✓ Snort/Recuperation.py%RESET%
) else (
    echo %RED%✗ Snort/Recuperation.py manquant%RESET%
)

if exist email_config_template.json (
    echo %GREEN%✓ email_config_template.json%RESET%
) else (
    echo %RED%✗ email_config_template.json manquant%RESET%
)

cd ..
echo.

REM ───────────────────────────────────────────────────────────────────────────────────────────────────────
REM TEST 6 : Notifier process
REM ───────────────────────────────────────────────────────────────────────────────────────────────────────
echo %BLUE%[6/7] État du notifier...%RESET%

tasklist /FI "IMAGENAME eq pythonw.exe" 2>nul | find /I "pythonw.exe" >nul
if %errorlevel% equ 0 (
    echo %GREEN%✓ Notifier en cours d'exécution%RESET%
) else (
    echo %YELLOW%⚠️  Notifier non lancé%RESET%
    echo   → Pour démarrer: pythonw Backend\notifier_advanced.py
)
echo.

REM ───────────────────────────────────────────────────────────────────────────────────────────────────────
REM TEST 7 : Test alert insertion (optionnel)
REM ───────────────────────────────────────────────────────────────────────────────────────────────────────
echo %BLUE%[7/7] Insertion d'une alerte de test (optionnel)...%RESET%
echo.
echo Voulez-vous insérer une alerte de test pour vérifier les notifications?
set /p test_alert="Taper 'OUI' pour continuer: "

if /i "%test_alert%"=="OUI" (
    echo.
    echo %YELLOW%⏳ Insertion d'une alerte de test...%RESET%
    
    set "TEST_ALERT=%TEMP%\create_test_alert.py"
    (
        echo import json
        echo from urllib.parse import urlparse
        echo try:
        echo     with open('Backend\.env', 'r') as f:
        echo         for line in f:
        echo             if line.startswith('DATABASE_URL='):
        echo                 db_url = line.split('=', 1)[1].strip()
        echo                 break
        echo     import psycopg2
        echo     parsed = urlparse(db_url)
        echo     conn = psycopg2.connect(dbname=parsed.path.lstrip('/') or 'postgres',
        echo                             user=parsed.username, password=parsed.password,
        echo                             host=parsed.hostname, port=5432, sslmode='require')
        echo     cur = conn.cursor()
        echo     cur.execute("""INSERT INTO alertes (source_ip, destination_ip, attack_type, severity, protocol, details)
        echo                    VALUES (%%s, %%s, %%s, %%s, %%s, %%s)""",
        echo                  ('192.168.1.100', '192.168.1.200', 'Test Alert - IDS Notifier',
        echo                   'critical', 'TCP', json.dumps({"test": True, "source": "Test"})))
        echo     conn.commit()
        echo     conn.close()
        echo     print('OK')
        echo except Exception as e:
        echo     print(f'FAIL:{e}')
    ) > "%TEST_ALERT%"
    
    for /f "delims=" %%i in ('python "%TEST_ALERT%" 2^>nul') do set "ALERT_TEST=%%i"
    del "%TEST_ALERT%" 2>nul
    
    if "!ALERT_TEST:~0,2!"=="OK" (
        echo %GREEN%✓ Alerte de test insérée%RESET%
        echo.
        echo   📧 Vérifiez votre email dans les 10 secondes (benainimeroua@gmail.com)
        echo   📬 Vérifiez aussi les notifications Windows
        echo.
        timeout /t 10 /nobreak
    ) else (
        echo %RED%✗ Erreur insertion alerte: !ALERT_TEST!%RESET%
    )
) else (
    echo Skipped.
)
echo.

REM ───────────────────────────────────────────────────────────────────────────────────────────────────────
REM RÉSUMÉ
REM ───────────────────────────────────────────────────────────────────────────────────────────────────────
echo %GREEN%═══════════════════════════════════════════════════════════════════════════════════════════════════════%RESET%
echo %GREEN%   ✅ TESTS COMPLÉTÉS ✅%RESET%
echo %GREEN%═══════════════════════════════════════════════════════════════════════════════════════════════════════%RESET%
echo.
echo 📁 Logs:      %APPDATA%\IDS_Notifier\notifier.log
echo 📧 Config:    %APPDATA%\IDS_Notifier\email_config.json
echo 🚀 Démarrer:  pythonw Backend\notifier_advanced.py
echo.
pause
exit /b 0

:end_error
echo.
echo %RED%═══════════════════════════════════════════════════════════════════════════════════════════════════════%RESET%
echo %RED%   ❌ TEST ÉCHOUÉ ❌%RESET%
echo %RED%═══════════════════════════════════════════════════════════════════════════════════════════════════════%RESET%
echo.
echo Exécutez: p_auto.bat
echo.
pause
exit /b 1
