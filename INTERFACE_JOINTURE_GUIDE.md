# Guide Complet des Jointures - Interface, VLAN & Switchs

## 📋 Problème Original
L'erreur **`selectedSwitchId is not defined`** venait du fait que la fonction `buildInterfacePayload` était définie en dehors du composant React et ne pouvait pas accéder à la variable d'état `selectedSwitchId`.

## ✅ Solution Implémentée

### 1. **Frontend (interface.html)**
La fonction `buildInterfacePayload` a été **déplacée DANS le composant InterfacesPage** pour accéder à `selectedSwitchId` via closure.

```javascript
const InterfacesPage = () => {
  // ✅ buildInterfacePayload maintenant DANS le composant pour accéder à selectedSwitchId
  const buildInterfacePayload = (port) => ({
    ...(port.dbExists && { id_interface: port.id_interface }),
    nom: port.id,
    ip: port.srcIp || null,
    id_switch: selectedSwitchId,   // ← accessible car dans le même scope du composant
    vlan_id: port.mode === 'trunk' ? null : (port.vlan && port.vlan !== 'All' ? Number(port.vlan) : null),
    equipement_id: port.equipement_id ?? null,
    status: port.status,
    mode: port.mode,
    type: port.type,
    speed: port.speed === '-' ? null : port.speed,
    allowed_vlans: port.mode === 'trunk' ? (port.vlan || port.allowedVlans || 'All') : null,
    port_security: port.portSecurity,
    max_mac: Number(port.maxMac || 1),
    violation_mode: port.securityViolation || 'shutdown',
    bpdu_guard: port.bpdu_guard,
  });
  
  // ... reste du composant
};
```

### 2. **Backend (interface.py) - Jointures Correctes**

#### A. Routes GET - Jointures Complètes
```sql
SELECT 
    i.id_interface, i.nom, i.ip, i.vlan_id, i.id_switch, i.equipement_id, 
    i.status, i.mode, i.type, i.speed, i.allowed_vlans, 
    i.port_security, i.max_mac, i.violation_mode, i.bpdu_guard,
    s.nom as switch_name, s.ip as switch_ip,
    v.nom as vlan_name, v.reseau as vlan_reseau
FROM interface i
LEFT JOIN switchs s ON i.id_switch = s.id_switch
LEFT JOIN vlan v ON i.vlan_id = v.id_vlan
WHERE i.id_switch = %s
ORDER BY i.id_interface ASC
```

#### B. Fonctions d'Aide pour Jointures

**1. `get_switch_id_by_name(cur, switch_name)`**
- **Paramètre**: nom du switch (string)
- **Retour**: id_switch (int)
- **Usage**: Convertir le nom du switch en ID pour validation et stockage

```python
def get_switch_id_by_name(cur, switch_name):
    """
    Récupère l'id_switch à partir du nom du switch.
    ✅ Jointure correcte: nom (string) → switchs → id_switch (int)
    """
    if not switch_name:
        return None
    
    cur.execute(
        "SELECT id_switch FROM switchs WHERE nom = %s",
        (switch_name,)
    )
    result = cur.fetchone()
    if result:
        return result[0]
    
    logger.warning(f"[get_switch_id_by_name] Switch '{switch_name}' introuvable")
    return None
```

**2. `get_switch_credentials(cur, id_switch)`**
- **Paramètre**: id_switch (int)
- **Retour**: dictionnaire {id_switch, nom, ip, username, password}
- **Usage**: Récupérer les credentials SSH pour le déploiement

```python
def get_switch_credentials(cur, id_switch):
    """
    Récupère les credentials SSH du switch à partir de son ID.
    Utilisé pour le déploiement SSH.
    """
    if not id_switch:
        return None
    
    cur.execute(
        "SELECT id_switch, nom, ip, username, password FROM switchs WHERE id_switch = %s",
        (id_switch,)
    )
    result = cur.fetchone()
    return result if result else None
```

#### C. Validation Améliorée dans `normalize_interface_payload`

```python
def normalize_interface_payload(data, forced_id=None, cur=None):
    """
    Valide et normalise les données d'une interface.
    Si cur est fourni, effectue les jointures avec switchs et vlan.
    ✅ Jointures correctes:
       - nom du switch (string) → table switchs → id_switch (int)
       - vlan_id (int) → table vlan → validation
    """
    # ... validation des autres champs ...
    
    # ✅ JOINTURE 1: Récupérer id_switch à partir du nom du switch
    raw_id_switch = data.get("id_switch")
    id_switch = None
    
    if raw_id_switch is not None:
        try:
            # Si c'est déjà un entier, utiliser directement
            id_switch = int(raw_id_switch)
        except (TypeError, ValueError):
            # Si c'est un string (nom du switch), faire la jointure
            if cur and isinstance(raw_id_switch, str):
                id_switch = get_switch_id_by_name(cur, raw_id_switch)
                if not id_switch:
                    raise ValueError(f"Le switch '{raw_id_switch}' n'existe pas en BDD")
            else:
                raise ValueError("id_switch doit etre un entier ou un nom de switch valide")
    
    # ... reste de la validation ...
```

### 3. **Flux de Données Complet**

#### Création d'une Interface
```
1. HTML - Sélectionner un switch via le dropdown
   selectedSwitchId = 1 (ex: Cisco_Switch)

2. HTML - Cliquer sur "Appliquer & Déployer"
   buildInterfacePayload(port) envoie:
   {
     nom: "Gi1/0/1",
     ip: "192.168.1.100",
     id_switch: 1,              // ← selectedSwitchId au moment du clic
     vlan_id: 10,
     mode: "access",
     ... autres paramètres ...
   }

3. Backend API (POST /api/interface)
   normalize_interface_payload({...}, cur=cur)
   ✓ Vérifie que id_switch=1 existe dans la table switchs
   ✓ Vérifie que vlan_id=10 existe dans la table vlan
   ✓ Insère dans interface avec id_switch=1

4. Backend API (POST /api/network/deploy-interface)
   SELECT ip, username, password FROM switchs WHERE id_switch = 1
   → Récupère les credentials du switch
   → Lance le déploiement SSH avec Netmiko

5. Frontend
   Affiche: "✅ Interface Gi1/0/1 enregistrée en BDD et déployée sur le switch"
```

## 📊 Schéma des Tables

### Table `switchs`
```sql
CREATE TABLE switchs (
    id_switch SERIAL PRIMARY KEY,       -- Clé primaire
    nom VARCHAR UNIQUE,                 -- Nom du switch
    ip VARCHAR,                         -- Adresse IP
    masque VARCHAR,                     -- Masque réseau
    username VARCHAR,                   -- Utilisateur SSH
    password VARCHAR,                   -- Mot de passe SSH
    nb_ports INT,                       -- Nombre de ports
    status VARCHAR,                     -- Statut du switch
    reference_id VARCHAR                -- Référence d'inventaire
);
```

### Table `vlan`
```sql
CREATE TABLE vlan (
    id_vlan SERIAL PRIMARY KEY,         -- Clé primaire
    nom VARCHAR,                        -- Nom du VLAN
    reseau VARCHAR,                     -- Réseau CIDR
    gateway VARCHAR,                    -- Gateway du VLAN
    type VARCHAR,                       -- Type (access, trunk, etc)
    ports VARCHAR,                      -- Ports du VLAN
    status VARCHAR,                     -- Statut
    switch_name VARCHAR,                -- Nom du switch (référence)
    switch_ip VARCHAR                   -- IP du switch (référence)
);
```

### Table `interface`
```sql
CREATE TABLE interface (
    id_interface SERIAL PRIMARY KEY,    -- Clé primaire
    nom VARCHAR UNIQUE,                 -- Nom de l'interface (Gi1/0/1)
    ip VARCHAR,                         -- IP de l'interface
    vlan_id INT REFERENCES vlan(id_vlan),     -- ✅ Clé étrangère vers vlan
    equipement_id INT,                  -- ID équipement connecté
    status VARCHAR,                     -- Status (UP/DOWN)
    mode VARCHAR,                       -- Mode (access/trunk)
    type VARCHAR,                       -- Type (access/uplink)
    speed VARCHAR,                      -- Vitesse (1Gb, 10Gb, etc)
    allowed_vlans VARCHAR,              -- VLANs autorisés en trunk
    port_security BOOLEAN,              -- Port security activé
    max_mac INT,                        -- Max adresses MAC
    violation_mode VARCHAR,             -- Mode violation (shutdown/restrict/protect)
    bpdu_guard BOOLEAN,                 -- BPDU Guard activé
    id_switch INT REFERENCES switchs(id_switch) ON DELETE CASCADE  -- ✅ Clé étrangère vers switchs
);
```

## 🔄 Jointures Utilisées

### Jointure 1: Interface → Switchs
```sql
LEFT JOIN switchs s ON i.id_switch = s.id_switch
```
- **Interface.id_switch** (int) → **Switchs.id_switch** (int)
- Récupère: nom du switch, IP du switch, credentials SSH

### Jointure 2: Interface → VLAN
```sql
LEFT JOIN vlan v ON i.vlan_id = v.id_vlan
```
- **Interface.vlan_id** (int) → **VLAN.id_vlan** (int)
- Récupère: nom du VLAN, réseau du VLAN, gateway du VLAN

## 🚀 Exemple Complet d'Utilisation

### 1. Créer une Interface en Access
```javascript
// Frontend - Sélectionner switch "Cisco_Switch" (id=1)
const payload = {
  nom: "Gi1/0/1",
  ip: "192.168.1.100",
  id_switch: 1,        // selectedSwitchId du composant
  vlan_id: 10,         // VLAN existant
  mode: "access",
  type: "access",
  status: "UP",
  port_security: true,
  max_mac: 1,
  violation_mode: "shutdown",
  bpdu_guard: true
};

// POST /api/interface
```

### 2. Valider et Stocker (Backend)
```python
# normalize_interface_payload valide:
✓ id_switch=1 existe dans switchs
✓ vlan_id=10 existe dans vlan
✓ Tous les paramètres sont valides

# INSERT dans interface
INSERT INTO interface (nom, ip, vlan_id, id_switch, ...)
VALUES ('Gi1/0/1', '192.168.1.100', 10, 1, ...)
```

### 3. Récupérer les Credentials (Backend)
```python
# SELECT credentials du switch
SELECT ip, username, password FROM switchs WHERE id_switch = 1
# Résultat: ip='192.168.1.254', username='admin', password='password'
```

### 4. Déployer sur le Switch (Backend)
```python
# SSH Netmiko
interface GigabitEthernet1/0/1
  switchport access vlan 10
  switchport port-security
  switchport port-security maximum 1
  no shutdown
exit
write memory
```

## ⚠️ Erreurs Courantes et Solutions

### Erreur 1: `selectedSwitchId is not defined`
**Cause**: `buildInterfacePayload` définie en dehors du composant
**Solution**: Déplacer la fonction DANS le composant InterfacesPage ✅

### Erreur 2: `Le switch '...' n'existe pas en BDD`
**Cause**: Le nom du switch n'existe pas dans la table switchs
**Solution**: Vérifier que le switch est bien ajouté dans la page "Équipements"

### Erreur 3: `Le VLAN ... n'existe pas`
**Cause**: Le VLAN n'existe pas dans la table vlan
**Solution**: Créer le VLAN d'abord dans la page "VLAN"

### Erreur 4: Déploiement SSH échoue
**Cause**: Les credentials SSH ne correspondent pas
**Solution**: Vérifier les credentials (username/password) dans la table switchs

## 📝 Checklist de Vérification

- [x] `buildInterfacePayload` est DANS le composant InterfacesPage
- [x] Les fonctions `get_switch_id_by_name` et `get_switch_credentials` existent
- [x] La route GET `/api/interface` utilise les jointures
- [x] La route POST `/api/interface` valide l'existence du switch
- [x] La route PUT `/api/interface/<id>` valide les clés étrangères
- [x] La route `/api/network/deploy-interface` récupère les credentials correctement
- [x] Les paramètres `id_switch` et `vlan_id` sont des entiers dans la BDD
- [x] Les jointures LEFT JOIN gèrent les cas NULL

## 🎯 Résumé

| Composant | Avant | Après |
|-----------|-------|-------|
| **Frontend** | `buildInterfacePayload` en dehors | DANS le composant ✅ |
| **Backend** | Pas de validation Switch | Validation Switch + Jointures ✅ |
| **API GET** | Pas de jointures | Jointures switchs + vlan ✅ |
| **Déploiement** | Récupération confuse | Credentials via id_switch ✅ |

