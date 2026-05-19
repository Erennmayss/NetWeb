═══════════════════════════════════════════════════════════════════════════════════════════════════════
    IDS ALERT NOTIFIER v3.0 - INSTALLATION ET UTILISATION
    Supabase + Email Gmail SMTP + Notifications Windows Toast
═══════════════════════════════════════════════════════════════════════════════════════════════════════

📋 CONTENU DU PACKAGE
═══════════════════════════════════════════════════════════════════════════════════════════════════════

  notifier_advanced.py           → Notifier principal (surveillance Supabase + notifications)
  snort_alert_processor.py       → Processeur d'alertes Snort (notifications instantanées)
  Recuperation.py (modifié)      → Intégration Snort (envoie les alertes au processeur)
  p_auto.bat                     → Installation automatisée (sans menus)
  email_config_template.json     → Configuration SMTP Gmail (pré-remplie)


⚡ INSTALLATION RAPIDE (1 CLIC)
═══════════════════════════════════════════════════════════════════════════════════════════════════════

  1. Ouvrez un invite de commande comme ADMINISTRATEUR
  2. Naviguez vers le dossier Backend:
     
     cd C:\Users\ADM\Desktop\ids_1\NetWeb\Backend

  3. Lancez l'installation automatique:
     
     p_auto.bat

  ✓ L'installation va:
    - Vérifier Python
    - Tester la connexion Supabase
    - Installer toutes les dépendances
    - Configurer l'email automatiquement
    - Ajouter le notifier au démarrage Windows
    - Démarrer le notifier en arrière-plan


🔧 CONFIGURATION (DÉJÀ FAITE)
═══════════════════════════════════════════════════════════════════════════════════════════════════════

DATABASE (Supabase)
───────────────────
  • URL Supabase automatiquement lue depuis .env
  • postgresql://postgres.jleedvfezpjaojgwltfu:Malek140504@...
  • SSL mode: require (activé pour Supabase)
  • Polling: 5 secondes

EMAIL SMTP (Gmail)
──────────────────
  • Serveur: smtp.gmail.com:587
  • Compte: benainimeroua@gmail.com
  • Mot de passe: Clé d'application Gmail (stock dans email_config.json)
  • Destination: Utilisateurs avec role='admin' ou role='security_admin'
  • Auto-enabled: OUI (pas de configuration manuelle)


🚀 USAGE
═══════════════════════════════════════════════════════════════════════════════════════════════════════

DÉMARRAGE MANUEL (pour tests)
──────────────────────────────

  cd Backend
  python notifier_advanced.py

  Ou avec intervalle custom:
  python notifier_advanced.py --interval 3


DÉMARRAGE AUTOMATIQUE
──────────────────────

  ✓ Le script p_auto.bat ajoute une tâche planifiée Windows
  ✓ Le notifier démarre à chaque redémarrage
  ✓ Fonctionne en arrière-plan (aucune fenêtre)


INTÉGRATION SNORT
─────────────────

  Le script Recuperation.py (modifié) enregistre automatiquement:
  
  1. Les alertes dans Supabase via l'API Flask
  2. Les notifications instantanées via snort_alert_processor:
     - Toast Windows
     - Email aux admins
     - Log console

  Exemple d'alerte reçue:
  
    [10:30:45] 🔴 CRITIQUE | SQL Injection Attempt | 192.168.1.100:45123 → 192.168.1.200:80
    ✓ Email envoyé à benainimeroua@gmail.com
    ✓ Toast affiché


📊 STRUCTURE DE DONNÉES
═══════════════════════════════════════════════════════════════════════════════════════════════════════

TABLE: alertes (Supabase)
────────────────────────
  
  id                BIGINT (auto)
  timestamp         TIMESTAMPTZ (NOW())
  source_ip         INET
  destination_ip    INET
  source_port       INTEGER
  destination_port  INTEGER
  protocol          VARCHAR(50)
  attack_type       TEXT
  severity          VARCHAR(20)   [critical, high, medium, low]
  details           JSONB
  created_at        TIMESTAMPTZ

TABLE: utilisateur (Supabase)
─────────────────────────────

  id                BIGINT
  email             VARCHAR(255)
  role              VARCHAR(50)   [admin, security_admin, viewer, ...]
  ...autres champs...


📧 RÉCEPTION D'EMAILS
═══════════════════════════════════════════════════════════════════════════════════════════════════════

Les alertes sont envoyées par email aux utilisateurs avec:

  ✓ role = 'admin'         OU
  ✓ role = 'security_admin'

Et qui ont un email valide dans la base de données.

EXEMPLE DE CONTENU:
───────────────────

  Subject: [IDS ALERT] CRITICAL - SQL Injection Attempt

  Body:
  ═══════════════════════════════════════════════════════════════════════════
      🚨 ALERTE IDS DÉTECTÉE 🚨
  ═══════════════════════════════════════════════════════════════════════════

  📋 TYPE          : SQL Injection Attempt
  ⚠️  SÉVÉRITÉ    : CRITICAL
  🕐 HORODATAGE   : 2026-05-18T10:30:45.123456
  
  📡 SOURCE       : 192.168.1.100:45123
  🎯 DESTINATION  : 192.168.1.200:80
  🔌 PROTOCOLE    : TCP

  ═══════════════════════════════════════════════════════════════════════════
  DÉTAILS :
  ───────────────────────────────────────────────────────────────────────────
  {
    "detection_engine": "Snort",
    "signature_id": "1:2000087:1",
    "message": "ET NETBIOS/RPC Exploit attempt"
  }


📁 FICHIERS DE CONFIGURATION
═══════════════════════════════════════════════════════════════════════════════════════════════════════

%APPDATA%\IDS_Notifier\
├── notifier.log              → Logs du notifier
├── notifier_state.json       → État (alertes vues)
├── snort_processor.log       → Logs du processeur Snort
├── email_config.json         → Configuration SMTP
└── critical_alerts.log       → Alertes critiques (log d'urgence)


🔍 DÉPANNAGE
═══════════════════════════════════════════════════════════════════════════════════════════════════════

SUPABASE INACCESSIBLE
─────────────────────
  ✓ Vérifiez la connexion Internet
  ✓ Vérifiez DATABASE_URL dans .env
  ✓ Testez: python -c "import psycopg2; ..."

EMAIL NON ENVOYÉ
────────────────
  ✓ Vérifiez email_config.json
  ✓ Vérifiez que les utilisateurs admin ont un email
  ✓ Consultez %APPDATA%\IDS_Notifier\snort_processor.log

NOTIFIER NE DÉMARRE PAS
────────────────────────
  ✓ Lancez manuellement: python notifier_advanced.py
  ✓ Consultez les logs: tail -f %APPDATA%\IDS_Notifier\notifier.log

PYTHON NON TROUVÉ
──────────────────
  ✓ Installez Python depuis https://www.python.org/downloads/
  ✓ Cochez "Add Python to PATH"
  ✓ Redémarrez


✅ VÉRIFICATION DE L'INSTALLATION
═══════════════════════════════════════════════════════════════════════════════════════════════════════

  1. Vérifier que le notifier s'est lancé:
     tasklist | find "pythonw.exe"

  2. Vérifier les logs:
     type %APPDATA%\IDS_Notifier\notifier.log

  3. Insérer une alerte de test:
     python snort_alert_processor.py

  4. Créer une alerte manuellement:
     python -c "
     import psycopg2
     from urllib.parse import urlparse
     
     db_url = open('.env').read().split('DATABASE_URL=')[1].split('\n')[0]
     parsed = urlparse(db_url)
     conn = psycopg2.connect(dbname=parsed.path.lstrip('/'), user=parsed.username, 
                             password=parsed.password, host=parsed.hostname, port=5432, sslmode='require')
     cur = conn.cursor()
     cur.execute('INSERT INTO alertes (source_ip, destination_ip, attack_type, severity) VALUES (%s, %s, %s, %s)',
                 ('192.168.1.1', '192.168.1.2', 'Test Alert', 'critical'))
     conn.commit()
     conn.close()
     print('Alert inserted')
     "


📞 SUPPORT
═══════════════════════════════════════════════════════════════════════════════════════════════════════

Logs disponibles:
  • %APPDATA%\IDS_Notifier\notifier.log
  • %APPDATA%\IDS_Notifier\snort_processor.log
  • %APPDATA%\IDS_Notifier\critical_alerts.log

Source code:
  • Backend\notifier_advanced.py
  • Backend\snort_alert_processor.py
  • Backend\Snort\Recuperation.py (modifié)


═══════════════════════════════════════════════════════════════════════════════════════════════════════
Generated: 2026-05-18
Version: 3.0 Supabase Edition
═══════════════════════════════════════════════════════════════════════════════════════════════════════
