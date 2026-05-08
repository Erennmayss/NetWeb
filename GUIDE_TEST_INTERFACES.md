# 🧪 GUIDE DE TEST COMPLET - JOINTURES INTERFACE

## 🎯 Objectif
Valider que le problème `selectedSwitchId is not defined` est résolu et que les jointures fonctionnent correctement.

---

## ✅ ÉTAPE 1: Vérifier les Données de Test

### Prérequis
Vous devez avoir au moins:
- ✅ 1 switch dans la table `switchs`
- ✅ 1 VLAN dans la table `vlan`

### Requête SQL de Vérification
```sql
-- Vérifier les switchs
SELECT id_switch, nom, ip, username, password FROM switchs LIMIT 5;

-- Vérifier les VLANs
SELECT id_vlan, nom, reseau FROM vlan LIMIT 5;

-- Vérifier les interfaces existantes
SELECT id_interface, nom, id_switch, vlan_id FROM interface LIMIT 5;
```

**Résultat attendu**:
```
 id_switch │    nom     │       ip       │ username │ password
───────────┼────────────┼────────────────┼──────────┼──────────
         1 │ Cisco_Sw   │ 192.168.1.254  │ admin    │ password
         2 │ Juniper_Sw │ 192.168.1.255  │ admin    │ admin

 id_vlan │  nom  │    reseau
─────────┼───────┼─────────────
       1 │ VLAN1 │ 10.0.0.0/24
      10 │ VLAN10│ 192.168.1.0/24
      20 │ VLAN20│ 192.168.2.0/24
```

---

## ✅ ÉTAPE 2: Tester le Frontend

### 2.1 Ouvrir la page Interfaces
1. **Accéder à**: `http://localhost:5000/interfaces.html`
2. **Attendre le chargement**: Les switches doivent se charger

### 2.2 Vérifier le Select Switch
```javascript
// Dans la console du navigateur (F12)
// Le dropdown doit afficher les switches
console.log("Switches chargés");  // Vérifier qu'il y a des switches
```

**Résultat attendu**:
- Voir un dropdown avec: "Cisco_Switch (192.168.1.254)"
- Le premier switch est sélectionné par défaut

### 2.3 Vérifier que selectedSwitchId est défini
```javascript
// Dans la console:
// Ouvrir DevTools (F12 → Console)
// Attendre que React finisse de rendre le composant
// Le dropdown devrait avoir un ID de switch sélectionné

// Essayer de créer une interface pour vérifier que selectedSwitchId est passé
// (voir étape 3)
```

---

## ✅ ÉTAPE 3: Tester la Création d'Interface

### 3.1 Créer une Interface en Access

1. **Dans la page Interfaces**:
   - Sélectionner un switch (ex: "Cisco_Switch")
   - Cliquer sur un port (ex: Gi1/0/1)
   - Dans le panneau de droite, remplir:
     - **VLAN**: 10 (ex: VLAN10)
     - **Mode**: Access
     - **Status**: UP
     - **Port Security**: Activer ✓

2. **Cliquer sur "Appliquer & Déployer"**

### 3.2 Vérifier les Logs Frontend
```
Dans la console (F12):
✅ [loadSwitches] Switches chargés: [...]
✅ [loadInterfaces] Début du chargement des interfaces pour switch_id=1
✅ [handleApplyAndDeploy] Attempting to persist port to DB: {...}
```

### 3.3 Vérifier les Logs Backend
```
Dans le terminal Python (Backend):
✅ [API] POST create_interface
✅ [API] Interface Gi1/0/1 créée avec succès (switch_id=1)
```

**Résultat attendu**:
- Pas d'erreur `selectedSwitchId is not defined`
- Toast: "✅ Interface Gi1/0/1 enregistrée en BDD et déployée sur le switch !"

---

## ✅ ÉTAPE 4: Tester la Jointure en Base de Données

### 4.1 Vérifier l'Interface Créée
```sql
-- Vérifier que l'interface a bien été créée
SELECT 
    i.id_interface, 
    i.nom, 
    i.vlan_id, 
    i.id_switch,
    s.nom as switch_name,
    v.nom as vlan_name
FROM interface i
LEFT JOIN switchs s ON i.id_switch = s.id_switch
LEFT JOIN vlan v ON i.vlan_id = v.id_vlan
WHERE i.nom = 'Gi1/0/1'
LIMIT 1;
```

**Résultat attendu**:
```
 id_interface │   nom    │ vlan_id │ id_switch │  switch_name  │ vlan_name
──────────────┼──────────┼─────────┼───────────┼───────────────┼──────────
            1 │ Gi1/0/1  │      10 │         1 │ Cisco_Switch  │ VLAN10
```

### 4.2 Vérifier l'Absence d'Erreurs de Clés Étrangères
```sql
-- Vérifier qu'il n'y a pas de clés étrangères invalides
SELECT i.id_interface, i.nom, i.id_switch
FROM interface i
LEFT JOIN switchs s ON i.id_switch = s.id_switch
WHERE i.id_switch IS NOT NULL AND s.id_switch IS NULL;

-- Résultat attendu: AUCUNE LIGNE (pas d'erreurs)
```

---

## ✅ ÉTAPE 5: Tester la Route API GET

### 5.1 Appel API Direct
```bash
# Dans un terminal ou Postman:
curl -X GET "http://localhost:5000/api/interface?switch_id=1" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Résultat attendu** (JSON):
```json
{
  "success": true,
  "count": 1,
  "interfaces": [
    {
      "id_interface": 1,
      "nom": "Gi1/0/1",
      "ip": "192.168.1.100",
      "vlan_id": 10,
      "id_switch": 1,
      "status": "UP",
      "mode": "access",
      "type": "access",
      "port_security": true,
      "switch_name": "Cisco_Switch",    // ✅ Jointure switchs
      "switch_ip": "192.168.1.254",      // ✅ Jointure switchs
      "vlan_name": "VLAN10",             // ✅ Jointure vlan
      "vlan_reseau": "192.168.1.0/24"    // ✅ Jointure vlan
    }
  ]
}
```

### 5.2 Vérifier dans le Frontend
```javascript
// Ouvrir la console (F12)
// Chercher les logs:
console.log('[loadInterfaces] Interfaces fusionnées:', mergedPorts);

// Vérifier qu'il y a les infos du switch et du VLAN
```

---

## ✅ ÉTAPE 6: Tester la Mise à Jour (PUT)

### 6.1 Modifier l'Interface
1. **Cliquer sur le port Gi1/0/1**
2. **Changer le VLAN**: 10 → 20 (VLAN20)
3. **Cliquer sur "Appliquer & Déployer"**

### 6.2 Vérifier dans la BDD
```sql
SELECT 
    i.id_interface, 
    i.nom, 
    i.vlan_id,
    s.nom as switch_name,
    v.nom as vlan_name
FROM interface i
LEFT JOIN switchs s ON i.id_switch = s.id_switch
LEFT JOIN vlan v ON i.vlan_id = v.id_vlan
WHERE i.nom = 'Gi1/0/1';
```

**Résultat attendu**:
```
 id_interface │   nom    │ vlan_id │  switch_name  │ vlan_name
──────────────┼──────────┼─────────┼───────────────┼──────────
            1 │ Gi1/0/1  │      20 │ Cisco_Switch  │ VLAN20
```

---

## ✅ ÉTAPE 7: Tester la Suppression (DELETE)

### 7.1 Supprimer l'Interface
1. **Cliquer sur le port Gi1/0/1**
2. **Cliquer sur l'icône poubelle** (Delete)
3. **Confirmer la suppression**

### 7.2 Vérifier dans la BDD
```sql
SELECT * FROM interface WHERE nom = 'Gi1/0/1';
-- Résultat attendu: AUCUNE LIGNE (supprimée)
```

---

## ✅ ÉTAPE 8: Tester avec Plusieurs Switchs

### 8.1 Créer une Interface sur Chaque Switch
1. **Sélectionner Cisco_Switch** (id=1)
   - Créer interface Gi1/0/1 sur VLAN10
2. **Sélectionner Juniper_Switch** (id=2)
   - Créer interface Gi1/0/1 sur VLAN20

### 8.2 Vérifier la Jointure
```sql
SELECT 
    i.id_interface, 
    i.nom, 
    s.nom as switch_name,
    v.nom as vlan_name
FROM interface i
LEFT JOIN switchs s ON i.id_switch = s.id_switch
LEFT JOIN vlan v ON i.vlan_id = v.id_vlan
ORDER BY i.id_switch, i.id_interface;
```

**Résultat attendu**:
```
 id_interface │   nom    │  switch_name  │ vlan_name
──────────────┼──────────┼───────────────┼──────────
            1 │ Gi1/0/1  │ Cisco_Switch  │ VLAN10
            2 │ Gi1/0/1  │ Juniper_Switch│ VLAN20
```

---

## 🐛 Débogage - Si Erreur

### Erreur: `selectedSwitchId is not defined`
**Cause**: La fonction `buildInterfacePayload` n'est pas dans le composant
**Solution**: Vérifier que la ligne ~193 de `interfaces.html` a été modifiée

```bash
# Vérifier la modification:
grep -n "const buildInterfacePayload" Frontend/interfaces.html
# Devrait afficher une ligne APRÈS "const InterfacesPage = ()"
```

### Erreur: `Le switch '...' n'existe pas`
**Cause**: Le switch n'existe pas dans la table switchs
**Solution**:
```sql
-- Ajouter un switch de test
INSERT INTO switchs (nom, ip, username, password, nb_ports, status)
VALUES ('Cisco_Switch', '192.168.1.254', 'admin', 'password', 28, 'UP');
```

### Erreur: `Le VLAN ... n'existe pas`
**Cause**: Le VLAN n'existe pas dans la table vlan
**Solution**:
```sql
-- Ajouter un VLAN de test
INSERT INTO vlan (nom, reseau, gateway, type, status)
VALUES ('VLAN10', '192.168.1.0/24', '192.168.1.1', 'access', 'UP');
```

### Erreur: Pas de jointure dans la réponse API
**Cause**: Les colonnes switch_name et vlan_name manquent
**Solution**: Vérifier que la route GET a été modifiée

```bash
# Vérifier la modification:
grep -n "switch_name" Backend/Database/interface.py
# Devrait afficher plusieurs lignes
```

---

## 📊 Checklist de Test

### Avant de Déployer
- [ ] Fichier `interfaces.html` modifié (buildInterfacePayload dans le composant)
- [ ] Fichier `interface.py` modifié (fonctions et routes)
- [ ] Pas d'erreur de syntaxe Python
- [ ] Pas d'erreur de syntaxe JavaScript

### Test Frontend
- [ ] Dropdown des switchs se charge
- [ ] Pas d'erreur console `selectedSwitchId is not defined`
- [ ] Selection d'interface affiche les infos correctes
- [ ] Bouton "Appliquer & Déployer" actif

### Test Backend
- [ ] Route GET retourne switch_name et vlan_name
- [ ] Route POST crée l'interface avec id_switch correct
- [ ] Route PUT met à jour l'interface
- [ ] Route DELETE supprime l'interface

### Test Base de Données
- [ ] Jointure switchs fonctionne
- [ ] Jointure vlan fonctionne
- [ ] Pas d'erreur de clé étrangère
- [ ] Les credentials SSH sont bien récupérés

---

## 🎉 Test Réussi!

Si tous les tests passent, félicitations! 🎊

**Résumé des changements appliqués**:
1. ✅ `buildInterfacePayload` est dans le composant React
2. ✅ Les jointures fonctionnent correctement
3. ✅ Les credentials sont bien récupérés
4. ✅ Les interfaces sont créées avec le bon switch

**Prochaines étapes**:
- Mettre en production
- Monitoring les logs
- Gérer les cas d'erreur supplémentaires si besoin

