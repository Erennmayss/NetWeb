# ✅ CHECKLIST DE DÉPLOIEMENT - TFTP Ready for Production

## 📍 Fichiers à Vérifier

### 1. **Backend/network_api.py**
- [ ] Imports: `import logging`, `from datetime import datetime`
- [ ] Logger: `logger = logging.getLogger(__name__)`
- [ ] Fonction `api_tftp_backup()` ~ ligne 200
  - [ ] Paramètre `config_type` accepté
  - [ ] Validation: `"running" | "startup"`
  - [ ] Logs: `[TFTP-BACKUP]` présents
  - [ ] `send_command_timing()` avec `delay_factor=2.0, max_loops=200`
  - [ ] Gestion prompts Cisco: "Destination filename"
  - [ ] Détection erreurs: "Error", "timeout", "bytes copied"
  - [ ] Réponse JSON: `config_type`, `timestamp`, `output`
  
- [ ] Fonction `api_tftp_restore()` ~ ligne 290
  - [ ] Paramètre `config_type` accepté
  - [ ] Validation: `"running" | "startup"`
  - [ ] Logs: `[TFTP-RESTORE]` présents
  - [ ] Gestion prompts: "Destination filename", "File exists", "Overwrite"
  - [ ] Save config en NVRAM si type=running
  - [ ] Réponse JSON structure correcte

### 2. **Backend/Database/interface.py**
- [ ] Fonction `ensure_interface_schema()` ~ ligne 90
  - [ ] Création colonne `static_mac VARCHAR(17)`
  - [ ] Try/except pour ALTER TABLE
  - [ ] Log: "Colonne interface.static_mac ajoutee"

- [ ] Fonction `row_to_interface()` ~ ligne 160
  - [ ] Retour du champ: `"static_mac": row.get("static_mac")`

- [ ] Fonction `normalize_interface_payload()` ~ ligne 180
  - [ ] Validation MAC: `len(...replace(":", "")) == 12`
  - [ ] Stockage: `"static_mac": static_mac`
  - [ ] Warning log si format invalide

- [ ] Toutes les routes API (`/api/interface`)
  - [ ] GET: SELECT inclut `static_mac`
  - [ ] POST: INSERT inclut `static_mac`
  - [ ] PUT: UPDATE inclut `static_mac`
  - [ ] DELETE: RETURNING inclut `static_mac`
  - [ ] Logs: `[API] Interface ... créée/mise à jour/supprimée`

### 3. **Frontend/interfaces.html**
- [ ] État React: `const [tftpConfigType, setTftpConfigType] = useState('running')`
- [ ] Fonction `handleTftp()` ~ ligne 450
  - [ ] Body include: `config_type: tftpConfigType`
  - [ ] Toast affiche: `${data.config_type}-config sauvegardée`

- [ ] UI Sélecteur config_type ~ ligne 520
  - [ ] Select avec options: "running-config", "startup-config"
  - [ ] Labels: "RAM (live)", "NVRAM (persistent)"
  - [ ] Appliqué à Backup ET Restore

- [ ] Support Static MAC ~ ligne 850
  - [ ] Input field pour MAC
  - [ ] Placeholder: "ex. 00:1A:2B:3C:4D:5E"
  - [ ] Validation regex affichée
  - [ ] Inclus dans buildInterfacePayload()
  - [ ] Affiché dans CLI preview

---

## 🔧 Vérification Technique

### Base de Données

```bash
# Connectez-vous à PostgreSQL
psql -U netguard_user -d netguard -h localhost

# Vérifiez la colonne static_mac
\d interface;
# Résultat attendu:
#  static_mac | character varying(17) |

# Vérifiez un enregistrement
SELECT nom, static_mac, port_security FROM interface LIMIT 5;
```

### Logs Backend

```bash
# Démarrez le backend en mode debug
cd Backend
export FLASK_ENV=development
python app.py

# Vous devez voir les imports:
# - logging
# - datetime

# Testez un TFTP backup et vérifiez les logs:
# [TFTP-BACKUP] Début - Serveur: ...
# [TFTP-BACKUP][switch_name] Commande: ...
```

### Vérification Frontend

Ouvrez la console browser (F12) et vérifiez:

```javascript
// Vérifiez l'état React
// Dans interfaces.html, cherchez:
const [tftpConfigType, setTftpConfigType] = useState('running');

// Vérifiez le body TFTP
// La fonction handleTftp() doit envoyer:
{
  tftp_server: "192.168.1.100",
  filename: "backup.cfg",
  config_type: "running"  // ← Doit être présent!
}
```

---

## 🧪 Test Pré-Production (5 minutes)

### Test 1: Paramètre config_type accepté

```bash
# Requête valide
curl -X POST http://127.0.0.1:5000/api/network/tftp-backup \
  -H "Content-Type: application/json" \
  -d '{
    "tftp_server": "192.168.1.100",
    "filename": "test.cfg",
    "config_type": "running"
  }'
# Réponse: {"success": ...}

# Requête invalide
curl -X POST http://127.0.0.1:5000/api/network/tftp-backup \
  -H "Content-Type: application/json" \
  -d '{
    "tftp_server": "192.168.1.100",
    "filename": "test.cfg",
    "config_type": "invalid"
  }'
# Réponse attendue: HTTP 400 + error message
```

### Test 2: Static MAC dans la BDD

```bash
# Créez une interface avec static_mac
curl -X POST http://127.0.0.1:5000/api/interface \
  -H "Content-Type: application/json" \
  -d '{
    "id_interface": 100,
    "nom": "Gi1/0/1",
    "status": "UP",
    "mode": "access",
    "vlan_id": 10,
    "static_mac": "00:1A:2B:3C:4D:5E",
    "port_security": true
  }'

# Réponse doit inclure:
# "static_mac": "00:1A:2B:3C:4D:5E"

# Vérifiez en BDD:
psql -U netguard_user -d netguard -c "SELECT nom, static_mac FROM interface WHERE id_interface = 100;"
```

### Test 3: UI Sélecteur config_type

1. Ouvrir interfaces.html
2. Cliquer sur "TFTP Config"
3. Vérifier que le dropdown "Type Config" existe
4. Options: "running-config" et "startup-config"
5. Vérifier les labels: "RAM (live)" et "NVRAM (persistent)"

### Test 4: Static MAC Input

1. Sélectionnez un port (ex: Gi1/0/1)
2. Activez "Port Security"
3. Vérifiez le champ "MAC Statique"
4. Entrez: `00:1A:2B:3C:4D:5E`
5. Vérifiez que le CLI Preview inclut: `switchport port-security mac-address 00:1A:2B:3C:4D:5E`

### Test 5: Logs Détaillés

```bash
# Dans les logs du backend, après un TFTP backup, vous devez voir:
[TFTP-BACKUP] Début - Serveur: 192.168.1.100, Config: running, Fichier: test.cfg
[TFTP-BACKUP][switch_cible] Commande: copy running-config tftp://192.168.1.100/test.cfg
[TFTP-BACKUP][switch_cible] Prompt détecté: Destination filename
[TFTP-BACKUP][switch_cible] Sauvegarde réussie
[TFTP-BACKUP] Succès - Sauvegardée → tftp://192.168.1.100/test.cfg
```

---

## 📊 Status de Déploiement

- [ ] network_api.py vérifiée
- [ ] interface.py vérifiée
- [ ] interfaces.html vérifiée
- [ ] BDD: colonne static_mac existe
- [ ] Logs: [TFTP-BACKUP] présents
- [ ] UI: Sélecteur config_type visible
- [ ] Test 1: config_type validé ✅
- [ ] Test 2: static_mac en BDD ✅
- [ ] Test 3: UI fonctionnelle ✅
- [ ] Test 4: CLI Preview correct ✅
- [ ] Test 5: Logs clairs ✅

**Si tous les ✅ sont cochés → PRÊT POUR TEST SUR SWITCH RÉEL** 🎉

---

## 🚀 Déploiement Final

### Avant de tester sur le switch réel

1. **Redémarrer le backend**
   ```bash
   pkill -f "python.*app.py"
   cd Backend && python app.py &
   ```

2. **Rafraîchir le navigateur** (Ctrl+F5)

3. **Vérifier la page interfaces.html** charge correctement

4. **Tester un TFTP backup** sur un switch de test d'abord

5. **Consulter GUIDE_TEST_TFTP.md** pour les tests complets

---

## 📞 Dépannage Rapide

| Problème | Solution |
|----------|----------|
| Colonne static_mac manquante | Exécuter: `ensure_interface_schema()` (auto au démarrage) |
| Logs [TFTP-BACKUP] absents | Vérifier import logging en haut de network_api.py |
| Sélecteur config_type inexistant | Actualiser le navigateur (Ctrl+F5) |
| Static_mac non sauvegardé | Vérifier le format XX:XX:XX:XX:XX:XX |
| Erreur HTTP 400 sur TFTP | Vérifier config_type est "running" ou "startup" |

---

## 🎯 Résultat Attendu

Après déploiement, vous devez avoir:

✅ Fichiers corrigés en production  
✅ Colonne static_mac en BDD  
✅ Logs détaillés [TFTP-BACKUP][HOST]  
✅ Sélecteur running/startup visibleUI  
✅ Support MAC statique fonctionnel  
✅ Paramètre config_type accepté  

**Prêt pour tester sur votre switch Cisco réel!** 🚀
