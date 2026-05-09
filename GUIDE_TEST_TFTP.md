# 📋 Guide de Test TFTP - Étapes Pratiques

## ✅ Prérequis

- [ ] Switch Cisco Catalyst (9200, 2960, etc.) accessible par SSH
- [ ] Adresse IP Switch: `10.10.10.50` (ou votre IP)
- [ ] Identifiants SSH: admin/password
- [ ] Serveur TFTP opérationnel sur `192.168.1.100`
- [ ] Connectivité réseau complète Switch ↔ PC TFTP

## 🔧 Étape 1 : Configurer les identifiants SSH du Switch

### Depuis l'interface web (interfaces.html)

1. **Cliquez** sur le bouton **"TFTP Config"** (en haut à droite)
2. **Ouvrir** le panneau de configuration du switch (section "Switch Cible - hosts.yaml")
3. **Remplissez**:
   - IP du Switch: `10.10.10.50`
   - Utilisateur SSH: `admin`
   - Mot de passe SSH: `password123`
   - Enable Secret: `enable_pwd` (si nécessaire)
   - Port SSH: `22`
   - Nom inventaire: `switch_cible`

4. **Cliquez** sur **"💾 Sauvegarder"**
   - Toast: "✅ Configuration switch sauvegardée dans hosts.yaml"

### Ce qui se passe en arrière-plan
```python
# Le fichier network/hosts.yaml reçoit:
switch_cible:
  hostname: 10.10.10.50
  username: admin
  password: password123
  port: 22
  platform: ios
  connection_options:
    netmiko:
      extras:
        secret: enable_pwd
```

---

## 📤 Étape 2 : Test BACKUP - running-config

### 1. Préparez le serveur TFTP
```bash
# Vérifier que le serveur TFTP écoute
tftp 192.168.1.100
```

### 2. Depuis l'interface web

1. **Ouvrir** le panneau TFTP (bouton "TFTP Config")
2. **Paramètres**:
   - Opération: **⬆️ Backup**
   - Type Config: **running-config** (RAM - live)
   - Serveur TFTP (IP): `192.168.1.100`
   - Nom du fichier: `backup-running-20260503.cfg`

3. **Cliquez** sur **"⬆️ Lancer Backup"**

### 3. Attendez la réponse

**Succès - Toast vert** ✅
```
✅ running-config sauvegardée sur 192.168.1.100
```

**Sortie du switch (dans le résultat)**:
```
Sending cfglog file to server 192.168.1.100!!!
3457 bytes copied in 1.234 secs
```

### 4. Vérifiez le fichier

```bash
# Sur le serveur TFTP
ls -lah /tftp/backup-running-20260503.cfg
cat /tftp/backup-running-20260503.cfg | head -20
# Doit afficher la running-config du switch
```

### Dépannage

| Erreur | Cause | Solution |
|--------|-------|----------|
| "Network unreachable" | TFTP non joignable | Vérifier IP serveur + connectivité |
| "Permission denied" | Pas de droits SSH | Vérifier user/password |
| "timeout" | Switch ne répond pas | Vérifier IP switch + SSH enabled |
| Pas de fichier créé | Mauvais chemin TFTP | Vérifier répertoire TFTP sur serveur |

---

## ⬇️ Étape 3 : Test BACKUP - startup-config

### Procédure identique à l'Étape 2, sauf:

- **Type Config**: **startup-config** (NVRAM - persistent)
- **Nom du fichier**: `backup-startup-20260503.cfg`

### Vérification

```bash
# Sur le serveur TFTP - Les deux fichiers doivent exister
ls -lah /tftp/backup-*.cfg

# Comparaison des contenus
diff /tftp/backup-running-20260503.cfg /tftp/backup-startup-20260503.cfg
# Doivent être similaires (startup-config souvent plus court)
```

---

## ⬆️ Étape 4 : Test RESTORE - running-config

### 1. Préparez un fichier de test

```bash
# Sur le serveur TFTP
# Option A : Utilisez le fichier de backup précédent
cp /tftp/backup-running-20260503.cfg /tftp/test-restore.cfg

# Option B : Créez une config minimaliste
cat > /tftp/test-restore.cfg << 'EOF'
!
! Test restore configuration
!
hostname TEST-SWITCH
!
interface Gi1/0/1
 description Test Port
 switchport mode access
 switchport access vlan 10
 no shutdown
!
ip route 0.0.0.0 0.0.0.0 10.10.10.1
!
end
EOF

# Vérifiez le fichier
cat /tftp/test-restore.cfg
```

### 2. Depuis l'interface web

1. **Paramètres TFTP**:
   - Opération: **⬇️ Restore**
   - Type Config: **running-config** (RAM)
   - Serveur TFTP: `192.168.1.100`
   - Nom du fichier: `test-restore.cfg`

2. **Cliquez** sur **"⬇️ Lancer Restore"**

### 3. Attendez la réponse

**Succès - Toast vert** ✅
```
✅ running-config restaurée depuis 192.168.1.100
```

**Sortie du switch**:
```
Configuring from tftp://192.168.1.100/test-restore.cfg!!!
3124 bytes copied in 0.987 secs
[OK]
```

### 4. Vérifiez sur le switch

```
# SSH ou CLI du switch
show running-config
# Vous devez voir les changements (nouvelle hostname, interface config, etc.)
```

### ⚠️ Important: Configuration en RAM uniquement!

Actuellement, la config est en **RAM uniquement** (running-config).
Si vous redémarrez le switch, elle revient à l'ancienne.

**Pour persister** (sauvegarder en NVRAM):
```
# SSH au switch et tapez:
copy running-config startup-config
# OU (syntaxe IOS XE)
write memory
```

---

## 🔄 Étape 5 : Test RESTORE + SAVE (Persistent)

### Procédure complète

1. **Restore running-config** (Étape 4)
2. **Une fois réussi**, tapez sur le CLI du switch:
   ```
   copy running-config startup-config
   ```
   OU
   ```
   write memory
   ```

3. **Reload le switch**:
   ```
   reload
   ```
   Confirmez: `yes`

4. **Après redémarrage**, vérifiez la config persiste:
   ```
   show running-config
   # Doit être identique à celle restaurée
   ```

---

## 🔐 Étape 6 : Test Interface Port-Security avec Static MAC

### Depuis interfaces.html

1. **Sélectionnez une interface**: `Gi1/0/1`

2. **Configurez**:
   - Status: **UP**
   - Mode: **access**
   - VLAN: **10**
   - Port Security: **Activé** ✓
   - Max MAC: **1**
   - Violation: **shutdown**
   - MAC Statique: `00:1A:2B:3C:4D:5E`
   - BPDU Guard: **Activé** ✓

3. **CLI Preview** doit afficher:
   ```
   interface Gi1/0/1
    description Access Port
    switchport mode access
    switchport access vlan 10
    switchport port-security
    switchport port-security maximum 1
    switchport port-security violation shutdown
    switchport port-security mac-address 00:1A:2B:3C:4D:5E
    spanning-tree bpduguard enable
    no shutdown
    exit
   ```

4. **Cliquez** sur **"🚀 Appliquer & Déployer sur le Switch"**

5. **Vérifiez sur le switch**:
   ```
   show port-security interface Gi1/0/1
   # Doit afficher:
   # - Port Security: Enabled
   # - Max MAC Addr: 1
   # - Violation Action: shutdown
   # - SecureUp Address (Configured): 00:1A:2B:3C:4D:5E
   ```

---

## ❌ Étape 7 : Test des Erreurs

### Erreur 1: Serveur TFTP Injoignable

1. **Paramètres TFTP**:
   - IP: `10.99.99.99` (invalide)
   - Opération: Backup

2. **Cliquez** sur "⬆️ Lancer Backup"

3. **Attendez** (quelques secondes)

4. **Toast rouge** ❌
   ```
   ❌ TFTP échoué : Erreur TFTP sur switch_cible: ...timeout...
   ```

### Erreur 2: Authentification SSH Échouée

1. **Modifier la config du switch**:
   - Utilisateur SSH: `baduser`
   - Mot de passe: `wrongpass`

2. **Sauvegardez**

3. **Tentez un Backup**

4. **Toast rouge** ❌
   ```
   ❌ TFTP échoué : Erreur SSH sur switch_cible: Authentication failed
   ```

### Erreur 3: Paramètres Invalides

1. **Essayez**:
   - config_type: `invalid`
   - tftp_server: (laissez vide)

2. **Lors du clic**: HTTP 400 Bad Request affiché

---

## 🎯 Checklist de Test Final

- [ ] **Test 1**: Backup running-config ✅
- [ ] **Test 2**: Backup startup-config ✅
- [ ] **Test 3**: Restore running-config ✅
- [ ] **Test 4**: Restore + Save (persistent) ✅
- [ ] **Test 5**: Port-Security avec Static MAC ✅
- [ ] **Test 6**: Interface Trunk avec VLAN allowed ✅
- [ ] **Test 7**: Erreur serveur TFTP ✅
- [ ] **Test 8**: Erreur SSH auth ✅

**Si tous ✅**: Fonctionnalité TFTP **100% opérationnelle** en production! 🎉

---

## 📊 Logs à Vérifier

### Logs Backend (Python)

```bash
# Dans les logs Flask:
[TFTP-BACKUP] Début - Serveur: 192.168.1.100, Config: running, Fichier: backup.cfg
[TFTP-BACKUP][switch_cible] Commande: copy running-config tftp://192.168.1.100/backup.cfg
[TFTP-BACKUP][switch_cible] Prompt détecté: Destination filename
[TFTP-BACKUP][switch_cible] Sauvegarde réussie
[TFTP-BACKUP] Succès - Sauvegardée → tftp://192.168.1.100/backup.cfg
```

### Inspection DB

```bash
# Vérifier static_mac dans la BDD
SELECT nom, static_mac, port_security FROM interface WHERE port_security = true;

# Doit afficher:
# nom         | static_mac            | port_security
# Gi1/0/1     | 00:1A:2B:3C:4D:5E     | true
```

---

## 🏁 Conclusion

Vous pouvez maintenant utiliser la fonctionnalité TFTP de manière **fiable et sûre** sur un switch Cisco réel! 

Tous les bugs ont été corrigés:
- ✅ Paramètre `config_type` (running/startup)
- ✅ Gestion d'erreurs robuste
- ✅ Logs détaillés pour le debugging
- ✅ Support du static MAC
- ✅ Validation complète frontend ↔ backend

**Bonne chance avec votre switch! 🚀**
