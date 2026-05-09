# 📌 RÉSUMÉ DES CHANGEMENTS EFFECTUÉS

## ✅ Problème Résolu
**Erreur initiale**: `selectedSwitchId is not defined`  
**Cause**: La fonction `buildInterfacePayload` était définie en dehors du composant React  
**Solution**: Déplacer la fonction DANS le composant InterfacesPage

---

## 🔧 Changements Détaillés

### 1. **Frontend** (`Frontend/interfaces.html`)

#### ❌ Avant (ERREUR)
```javascript
// Défini AVANT le composant → selectedSwitchId inaccessible
const buildInterfacePayload = (port) => ({
  id_switch: selectedSwitchId,   // ❌ ReferenceError: selectedSwitchId is not defined
  ...
});

const InterfacesPage = () => {
  const [selectedSwitchId, setSelectedSwitchId] = useState(null);
  // ...
};
```

#### ✅ Après (CORRIGÉ)
```javascript
const InterfacesPage = () => {
  const [selectedSwitchId, setSelectedSwitchId] = useState(null);
  
  // ✅ Défini DANS le composant → accès via closure
  const buildInterfacePayload = (port) => ({
    id_switch: selectedSwitchId,   // ✅ Accessible !
    ...
  });
  
  // ... reste du composant
};
```

**Fichier modifié**: `Frontend/interfaces.html` (ligne ~193-210)

---

### 2. **Backend - Ajout des Fonctions d'Aide** (`Backend/Database/interface.py`)

#### ✅ Nouvelle fonction: `get_switch_id_by_name(cur, switch_name)`
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

#### ✅ Nouvelle fonction: `get_switch_credentials(cur, id_switch)`
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

**Fichier modifié**: `Backend/Database/interface.py` (ligne ~32-70)

---

### 3. **Backend - Amélioration de `normalize_interface_payload`**

#### ❌ Avant (SANS jointure)
```python
def normalize_interface_payload(data, forced_id=None):
    raw_id_switch = data.get("id_switch")
    id_switch = None if raw_id_switch in (None, "") else raw_id_switch
    if id_switch is not None:
        try:
            id_switch = int(id_switch)
        except (TypeError, ValueError):
            raise ValueError("id_switch doit etre un entier")
    # ❌ Pas de vérification si le switch existe !
```

#### ✅ Après (AVEC jointure)
```python
def normalize_interface_payload(data, forced_id=None, cur=None):
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

**Fichier modifié**: `Backend/Database/interface.py` (ligne ~270-360)

---

### 4. **Backend - Amélioration de la Route GET** (`/api/interface`)

#### ❌ Avant (SANS jointure)
```python
@interface_bp.route("/api/interface", methods=["GET"])
def get_interfaces():
    query = """
        SELECT id_interface, nom, ip, vlan_id, id_switch, equipement_id, status, mode, type,
               speed, allowed_vlans, port_security, max_mac, violation_mode, bpdu_guard
        FROM interface
    """
    # ❌ Pas de jointure avec switchs et vlan
```

#### ✅ Après (AVEC jointures)
```python
@interface_bp.route("/api/interface", methods=["GET"])
def get_interfaces():
    query = """
        SELECT 
            i.id_interface, i.nom, i.ip, i.vlan_id, i.id_switch, i.equipement_id, 
            i.status, i.mode, i.type, i.speed, i.allowed_vlans, 
            i.port_security, i.max_mac, i.violation_mode, i.bpdu_guard,
            s.nom as switch_name, s.ip as switch_ip,         -- ✅ JOINTURE 1
            v.nom as vlan_name, v.reseau as vlan_reseau      -- ✅ JOINTURE 2
        FROM interface i
        LEFT JOIN switchs s ON i.id_switch = s.id_switch
        LEFT JOIN vlan v ON i.vlan_id = v.id_vlan
    """
```

**Fichier modifié**: `Backend/Database/interface.py` (ligne ~395-430)

---

### 5. **Backend - Amélioration de la Route POST** (`/api/interface`)

#### ❌ Avant
```python
@interface_bp.route("/api/interface", methods=["POST"])
def create_interface():
    try:
        payload = normalize_interface_payload(request.get_json())
    except ValueError as e:
        # ❌ Pas de passage du curseur pour la jointure
```

#### ✅ Après
```python
@interface_bp.route("/api/interface", methods=["POST"])
def create_interface():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # ✅ Passer le curseur pour les jointures
        payload = normalize_interface_payload(request.get_json(), cur=cur)
    except ValueError as e:
        # ...
    
    # ✅ Vérification que le switch existe
    if payload["id_switch"]:
        cur.execute("SELECT 1 FROM switchs WHERE id_switch = %s", (payload["id_switch"],))
        if not cur.fetchone():
            return jsonify({"success": False, "error": f"Le switch {payload['id_switch']} n'existe pas"}), 404
```

**Fichier modifié**: `Backend/Database/interface.py` (ligne ~440-520)

---

### 6. **Backend - Amélioration de la Route PUT** (`/api/interface/<id>`)

#### ✅ Après (MÊME LOGIQUE QUE POST)
```python
@interface_bp.route("/api/interface/<int:interface_id>", methods=["PUT"])
def update_interface(interface_id):
    # ✅ Passer le curseur pour les jointures
    payload = normalize_interface_payload(request.get_json() or {}, forced_id=interface_id, cur=cur)
    
    # ✅ Vérification que le switch existe
    if payload["id_switch"]:
        cur.execute("SELECT 1 FROM switchs WHERE id_switch = %s", (payload["id_switch"],))
        if not cur.fetchone():
            return jsonify({"success": False, "error": f"Le switch {payload['id_switch']} n'existe pas"}), 404
```

**Fichier modifié**: `Backend/Database/interface.py` (ligne ~525-600)

---

## 🎯 Flux de Données Corrigé

```
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND (interface.html)                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Sélectionner un switch dans le dropdown                │
│     selectedSwitchId = 1 (Cisco_Switch)                    │
│                                                             │
│  2. Cliquer sur "Appliquer & Déployer"                     │
│     buildInterfacePayload(port) {                          │
│       id_switch: selectedSwitchId  // ✅ Accessible !      │
│     }                                                       │
│                                                             │
│  3. POST /api/interface + JSON payload                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                            ↓ HTTP POST
┌─────────────────────────────────────────────────────────────┐
│ BACKEND (interface.py)                                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. normalize_interface_payload(data, cur=cur)             │
│     ✅ Vérifier que id_switch existe dans switchs          │
│     ✅ Vérifier que vlan_id existe dans vlan               │
│                                                             │
│  2. INSERT interface (...)                                 │
│     INSERT INTO interface (nom, id_switch, vlan_id, ...)   │
│     VALUES ('Gi1/0/1', 1, 10, ...)                         │
│                                                             │
│  3. POST /api/network/deploy-interface                     │
│     SELECT ip, username, password FROM switchs WHERE id=1  │
│     ✅ Récupère les credentials SSH                        │
│                                                             │
│  4. SSH Deploy via Netmiko                                 │
│     configure terminal                                     │
│     interface GigabitEthernet1/0/1                         │
│     switchport access vlan 10                              │
│     no shutdown                                            │
│     write memory                                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                            ↓ Response
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND (interface.html)                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ✅ Affiche:                                                │
│  "Interface Gi1/0/1 enregistrée en BDD et déployée         │
│   sur le switch Cisco_Switch (192.168.1.254)"              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 Schéma des Jointures

```
┌─────────────────────┐
│   switchs           │
│  ┌───────────────┐  │
│  │ id_switch (PK)├──┼───┐
│  │ nom           │  │   │
│  │ ip            │  │   │
│  │ username      │  │   │
│  │ password      │  │   │
│  │ nb_ports      │  │   │
│  └───────────────┘  │   │
└─────────────────────┘   │
                          │
                    ✅ FK (id_switch)
                          │
┌─────────────────────────┴───────┐
│   interface                     │
│  ┌──────────────────────────┐   │
│  │ id_interface (PK)        │   │
│  │ nom                      │   │
│  │ ip                       │   │
│  │ vlan_id (FK) ────────┐   │   │
│  │ id_switch (FK) ──────┼───┤   │
│  │ status, mode, type   │   │   │
│  │ port_security, ...   │   │   │
│  └──────────────────────┼───┘   │
└──────────────────────────┼────────┘
                           │
                     ✅ FK (vlan_id)
                           │
        ┌──────────────────┘
        │
┌───────▼─────────────┐
│   vlan              │
│  ┌───────────────┐  │
│  │ id_vlan (PK) │  │
│  │ nom           │  │
│  │ reseau        │  │
│  │ gateway       │  │
│  │ type          │  │
│  │ switch_name   │  │
│  │ switch_ip     │  │
│  └───────────────┘  │
└─────────────────────┘
```

---

## 📝 Fichiers Créés/Modifiés

### Modifiés:
1. ✅ `Frontend/interfaces.html` - Déplacer `buildInterfacePayload` dans le composant
2. ✅ `Backend/Database/interface.py` - Ajouter jointures et validations

### Créés:
3. ✅ `INTERFACE_JOINTURE_GUIDE.md` - Guide complet des jointures
4. ✅ `Backend/sql/interface_joins.sql` - Requêtes SQL avec jointures
5. ✅ `CHANGEMENTS_DETAILLES.md` - Ce fichier

---

## ✨ Résultat Final

| Avant | Après |
|-------|-------|
| ❌ Erreur `selectedSwitchId is not defined` | ✅ Variable accessible via closure |
| ❌ Pas de validation du switch | ✅ Vérification id_switch existe |
| ❌ Pas de jointure avec switchs | ✅ LEFT JOIN switchs avec infos |
| ❌ Pas de jointure avec vlan | ✅ LEFT JOIN vlan avec infos |
| ❌ Credentials récupérés manuellement | ✅ Auto-récupération via id_switch |
| ❌ Erreurs BDD silencieuses | ✅ Messages d'erreur clairs |

---

## 🚀 Prochaines Étapes

1. **Tester en local**:
   ```bash
   npm start  # Frontend
   python app.py  # Backend
   ```

2. **Tester la création d'interface**:
   - Aller sur la page Interfaces
   - Sélectionner un switch
   - Créer/modifier une interface
   - Vérifier que `selectedSwitchId` est bien passé

3. **Vérifier les logs**:
   - Frontend: Console (F12)
   - Backend: Terminal ou logs.txt

4. **Tester le déploiement SSH**:
   - Cliquer sur "Appliquer & Déployer"
   - Vérifier que les credentials du switch sont bien récupérés
   - Vérifier que la config est bien envoyée au switch

