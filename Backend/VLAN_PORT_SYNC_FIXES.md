# 🔧 Corrections - Synchronisation Ports VLAN ↔ Interface

## ❌ Problème Identifié

**Table VLAN:**
```
id_vlan | nom | ports    | switch_name | gateway
12      | IT  | g0/0/0   | Core_SW     | 10.10.10.1
```

**Table Interface:**
```
nom        | vlan_id | status | mode   | type
Gi1/0/2    | 12      | UP     | Access | Access
Gi1/0/3    | 12      | UP     | Access | Access
Gi1/0/4    | 12      | UP     | Access | Access
```

### Issue: Les noms de ports ne correspondent pas
- `vlan.ports = "g0/0/0"` (nom non-standard)
- `interface.nom = "Gi1/0/2", "Gi1/0/3", "Gi1/0/4"` (noms réels)
- ❌ Synchronisation échouée

---

## ✅ Corrections Apportées

### 1. **Normalisation Améliorée** (`normalize_interface_name()`)

**Avant:**
```python
def normalize_interface_name(name):
    # Acceptait: g, gi, gig, gigabitethernet → retournait gi0/0/0
    # Acceptait: Gi1/0/2 → retournait gi1/0/2
    # ✅ OK pour matching
```

**Après:**
```python
def normalize_interface_name(name):
    """
    Normalise les noms d'interfaces pour comparaison.
    ✅ Accepte: g0/0/0, Gi1/0/2, GigabitEthernet1/0/2, gi1/0/2, etc.
    ✅ Retourne: gi0/0/0, gi1/0/2, etc. (format canonique)
    """
    # Ajoute support pour: ethernet, eth, e
    # Plus robuste pour les variations
```

### 2. **Validation Ports Corrigée** (`validate_port_assignments()`)

**Avant:**
```python
def validate_port_assignments(cur, ports, id_switch=None):
    # Retournait les noms FOURNIS par l'utilisateur
    # "g0/0/0" → "g0/0/0"  ❌ Mauvais!
    # Devrait retourner les noms RÉELS de la BD
```

**Après:**
```python
def validate_port_assignments(cur, ports, id_switch=None):
    """
    ✅ Entrée: ports = "g0/0/0, Gi1/0/2" (variations de noms)
    ✅ Sortie: "Gi1/0/2, Gi1/0/3" (noms RÉELS depuis interface.nom)
    
    Map: normalized_port → real_interface_name
    Permet une synchronisation correcte avec la BD
    """
    # Cherche les interfaces existantes
    # Normalise les noms fournis
    # Retourne les NOMS RÉELS de la BD (pas les noms fournis!)
```

**Exemple:**
```
Entrée:  "g0/0/0, Gi1/0/2, fa0/24"
Recherche dans interface (id_switch=5):
  - Gi1/0/2  (norm: gi1/0/2)  ✅ Match!
  - Gi1/0/3  (norm: gi1/0/3)  ❌ Pas demandé
  - Gi1/0/4  (norm: gi1/0/4)  ❌ Pas demandé
  - Fa0/24   (norm: fa0/24)   ❌ Pas trouvé
  
Sortie:  "Gi1/0/2"  ← Nom RÉEL de la BD
         (pas "g0/0/0" ou "fa0/24")
```

### 3. **Synchronisation Robuste** (`sync_ports_to_interface()`)

**Avant:**
```python
def sync_ports_to_interface(cur, id_vlan, canonical_ports, id_switch=None):
    # Cherchait: "g0/0/0" dans interface.nom
    # Trouvait: rien! (car les vraies interfaces sont Gi1/0/2, etc.)
    # Résultat: vlan_id n'était pas mis à jour
```

**Après:**
```python
def sync_ports_to_interface(cur, id_vlan, canonical_ports, id_switch=None):
    """
    ✅ Normalise les noms pour matcher correctement (g0/0/0 ↔ Gi1/0/2)
    
    Étapes:
    1. Récupère toutes les anciennes interfaces (vlan_id = id_vlan)
    2. Pour chaque ancienne: si pas dans nouvelle liste → libérer (vlan_id = NULL)
    3. Pour chaque nouvelle: chercher par nom NORMALISÉ → assigner (vlan_id = id_vlan)
    """
    # Normalize new ports: {norm: real_name}
    # Pour chaque interface OLD:
    #   Si norm(old_name) NOT IN normalized_new_ports:
    #     UPDATE interface SET vlan_id = NULL
    # Pour chaque port NEW:
    #   Si norm(port) trouvé dans DB:
    #     UPDATE interface SET vlan_id = id_vlan WHERE nom = real_name
```

---

## 🚀 API Endpoints Disponibles

### 1. **GET /api/vlan** - Récupère tous les VLANs
```bash
curl http://localhost:5000/api/vlan
```

**Réponse:**
```json
{
  "success": true,
  "count": 1,
  "vlans": [
    {
      "id_vlan": 12,
      "nom": "IT",
      "gateway": "10.10.10.1",
      "ports": "Gi1/0/2, Gi1/0/3, Gi1/0/4",  ← Noms RÉELS depuis interface!
      "switchName": "Core_SW"
    }
  ]
}
```

### 2. **GET /api/switchs** - Liste tous les switches
```bash
curl http://localhost:5000/api/switchs
```

### 3. **GET /api/switch/{id}/interfaces** ⭐ NEW
```bash
curl http://localhost:5000/api/switch/5/interfaces
```

**Réponse - Montre les interfaces DISPONIBLES:**
```json
{
  "success": true,
  "switch_id": 5,
  "switch_name": "Core_SW",
  "count": 24,
  "interfaces": [
    {
      "id": 1,
      "nom": "Gi1/0/1",
      "vlan_id": 1,
      "status": "UP",
      "mode": "access",
      "type": "access",
      "speed": "1Gb"
    },
    {
      "id": 2,
      "nom": "Gi1/0/2",
      "vlan_id": 12,
      "status": "UP",
      "mode": "access",
      "type": "access",
      "speed": "1Gb"
    },
    ...
  ]
}
```

**Utilisation:** Avant de créer/modifier un VLAN, afficher cette liste pour que l'utilisateur choisisse les ports corrects.

### 4. **POST /api/vlan** - Crée un VLAN
```bash
curl -X POST http://localhost:5000/api/vlan \
  -H "Content-Type: application/json" \
  -d '{
    "id_vlan": 12,
    "nom": "IT",
    "gateway": "10.10.10.1",
    "switchName": "Core_SW",
    "ports": "Gi1/0/2, Gi1/0/3, Gi1/0/4"
  }'
```

**Réponse:**
```json
{
  "success": true,
  "message": "VLAN 12 'IT' créé sur le switch et enregistré en base de données.",
  "vlan": {
    "id_vlan": 12,
    "nom": "IT",
    "ports": "Gi1/0/2, Gi1/0/3, Gi1/0/4",  ← NOMS RÉELS!
    "switchName": "Core_SW"
  },
  "ssh_deploy": {
    "success": true,
    "message": "VLAN 12 created"
  },
  "ports_synced": 3  ← 3 interfaces mises à jour!
}
```

### 5. **PUT /api/vlan/{id}** - Met à jour un VLAN
```bash
curl -X PUT http://localhost:5000/api/vlan/12 \
  -H "Content-Type: application/json" \
  -d '{
    "ports": "Gi1/0/2, Gi1/0/5"
  }'
```

**Résultat:** 
- Gi1/0/3, Gi1/0/4 → vlan_id = NULL (libérées)
- Gi1/0/2 → vlan_id = 12 (garde)
- Gi1/0/5 → vlan_id = 12 (ajoutée)

### 6. **DELETE /api/vlan/{id}** - Supprime un VLAN
```bash
curl -X DELETE http://localhost:5000/api/vlan/12
```

**Résultat:**
- Gi1/0/2, Gi1/0/3, Gi1/0/4 → vlan_id = NULL (toutes libérées)
- Enregistrement VLAN supprimé de la BD

---

## 🔍 Troubleshooting - Vérifier la Synchronisation

### Cas 1: Les ports ne se synchronisent pas
```sql
-- Vérifier les interfaces du switch
SELECT nom, vlan_id, status FROM interface WHERE id_switch = 5 ORDER BY nom;

-- Vérifier le VLAN
SELECT id_vlan, nom, ports FROM vlan WHERE id_vlan = 12;

-- Vérifier si les noms correspondent
-- Exemple:
-- vlan.ports = "Gi1/0/2" 
-- interface.nom = "Gi1/0/2"  ← Doivent être IDENTIQUES
```

### Cas 2: Erreur "Interface(s) inexistante(s)"
```json
{
  "success": false,
  "error": "Interface(s) inexistante(s): g0/0/0\nDisponibles pour ce switch: Gi1/0/1, Gi1/0/2, Gi1/0/3, Gi1/0/4, Fa0/24"
}
```

**Solution:**
1. Appeler `GET /api/switch/{id}/interfaces` pour voir les vraies interfaces
2. Utiliser les noms exacts (ex: `Gi1/0/2` au lieu de `g0/0/0`)
3. Créer/modifier le VLAN avec les noms corrects

### Cas 3: Vérifier les logs du backend
```
[API] CREATE VLAN 12 'IT' → SSH ✓ + BDD ✓ + 3 ports synced
sync_ports_to_interface: VLAN 12 → 3 interface(s) mise(s) à jour
```

---

## 📋 Checklist - Data Integrity

Après créer/modifier un VLAN, vérifier:

- [ ] **vlan.ports** contient les noms RÉELS de la BD (ex: `Gi1/0/2, Gi1/0/3`)
- [ ] **interface.vlan_id** est mis à jour pour chaque port (vérifier 3 rows si 3 ports)
- [ ] **GET /api/vlan** retourne les ports corrects (enrichis depuis interface)
- [ ] **Logs** affichent `ports_synced: N` (ex: ports_synced: 3)

---

## 📝 Code Changes Summary

| Fonction | Avant | Après |
|----------|-------|-------|
| `normalize_interface_name()` | Basique | ✅ Supporte eth/ethernet + commentaires |
| `validate_port_assignments()` | Retournait noms fournis | ✅ Retourne noms RÉELS de BD |
| `sync_ports_to_interface()` | UPDATE aveugle | ✅ Cherche par normalisation + logs détaillés |
| Nouvelle API | N/A | ✅ GET /api/switch/{id}/interfaces |

---

## 🎯 Next Steps

1. **Tester l'API** avec les noms corrects des interfaces
2. **Utiliser** `GET /api/switch/{id}/interfaces` dans l'UI pour aider l'utilisateur
3. **Vérifier** que vlan.ports et interface.vlan_id sont en sync
4. **Valider** avec `curl` ou Postman avant d'utiliser l'UI

