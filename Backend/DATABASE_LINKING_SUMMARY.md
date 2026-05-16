# Liage BD - vlan.py et interface.py

## Vue d'ensemble
`vlan.py` est maintenant complètement lié à la base de données de la même façon que `interface.py`, avec une structure cohérente pour :
- Validation des données
- Jointures BD
- Gestion des erreurs
- Logging
- Synchronisation bidirectionnelle (BD ↔ Switch SSH)

---

## 1. STRUCTURE DES HELPERS - Liage BD

### vlan.py
```python
# ✅ Résolution ID Switch
resolve_switch_id(cur, payload)
  - payload["switch_name"] (string) → switchs table → id_switch (int)
  - Fallback: payload["id_switch"] déjà présent

# ✅ Validation Ports
validate_port_assignments(cur, ports, id_switch=None)
  - ports (string) → interface table → normalization
  - Vérifie que les ports existent pour ce switch
  - Retourne les noms canoniques

# ✅ Récupération Credentials SSH
get_switch_credentials_for_vlan(cur, id_vlan)
  - id_vlan → vlan table
  - vlan.switch_name → switchs table
  - Retourne: id_switch, ip, username, password
  - Utilisé pour SSH deploy/delete

# ✅ Sync Ports Bidirectionnelle
sync_ports_to_interface(cur, id_vlan, canonical_ports, id_switch=None)
  - Après CREATE/UPDATE VLAN
  - Efface vlan_id sur les anciennes interfaces
  - Met à jour interface.vlan_id pour les nouveaux ports
  - Source de vérité: table interface (PAS vlan.ports)
```

### interface.py
```python
# ✅ Résolution ID Switch (équivalent)
get_switch_id_by_name(cur, switch_name)
  - switch_name (string) → switchs table → id_switch (int)

# ✅ Validation VLAN
validate_vlan_reference(cur, vlan_id)
  - vlan_id (int) → vlan table → vérifie existence
  - Lance erreur si VLAN n'existe pas

# ✅ Récupération Credentials SSH
get_switch_credentials(cur, id_switch)
  - id_switch (int) → switchs table
  - Retourne ip, username, password
```

---

## 2. JOINTURES BD - Routes GET

### GET /api/vlan (vlan.py)
```sql
SELECT 
  v.id_vlan, v.nom, v.reseau, v.gateway, v.type, v.ports, v.status,
  v.switch_name, v.switch_ip
FROM vlan v
LEFT JOIN switchs s ON s.nom = v.switch_name  -- ✅ Jointure
WHERE v.switch_name = ? OR v.switch_id = ?    -- ✅ Filtrage
ORDER BY id_vlan ASC

-- ✅ ENRICHISSEMENT: Ports réels depuis interface
SELECT vlan_id, string_agg(nom, ', ') AS ports_from_interface
FROM interface
WHERE vlan_id = ANY(vlan_ids)
GROUP BY vlan_id
-- Utilise interface.vlan_id comme source de vérité, PAS vlan.ports
```

### GET /api/interface (interface.py)
```sql
SELECT 
  i.id_interface, i.nom, i.ip, i.vlan_id, i.id_switch,
  s.nom as switch_name, s.ip as switch_ip,
  v.nom as vlan_name, v.reseau as vlan_reseau
FROM interface i
LEFT JOIN switchs s ON i.id_switch = s.id_switch        -- ✅ Jointure
LEFT JOIN vlan v ON i.vlan_id = v.id_vlan             -- ✅ Jointure
WHERE i.id_switch = ? OR (aucun filtre)
ORDER BY i.id_interface ASC
```

---

## 3. CRUD - Atomicité et Transactionnel

### CREATE VLAN (vlan.py)
```
1. normalize_vlan_payload() - validation
2. resolve_switch_id(cur, payload) - switch_name → id_switch
3. validate_port_assignments(cur, ports) - ports → interface check
4. SSH Deploy via network.deploy_vlan.run_deploy()
   ↓ (SI réussi ↓)
5. INSERT INTO vlan VALUES(...) RETURNING
6. sync_ports_to_interface() - UPDATE interface.vlan_id
7. conn.commit()

⚠️  SI SSH échoue → conn.rollback() → BDD pas modifiée
```

### CREATE INTERFACE (interface.py)
```
1. normalize_interface_payload(data, cur=cur) - validation + jointures
   - id_switch (string/int) → switchs table → id_switch (int)
2. validate_vlan_reference(cur, vlan_id) - VLAN exists check
3. INSERT INTO interface VALUES(...) RETURNING
4. conn.commit()

Note: Pas de SSH deploy lors de la création en BDD
```

### UPDATE VLAN (vlan.py)
```
1. normalize_vlan_payload(..., forced_vlan_id=id_vlan)
2. resolve_switch_id(cur, payload)
3. validate_port_assignments(cur, ports)
4. UPDATE vlan SET ... WHERE id_vlan = ? RETURNING
5. sync_ports_to_interface() - resync avec nouveaux ports
6. conn.commit()
```

### UPDATE INTERFACE (interface.py)
```
1. normalize_interface_payload(..., forced_id=interface_id, cur=cur)
   - Fait jointures pour résoudre switch_name → id_switch
2. validate_vlan_reference(cur, vlan_id)
3. UPDATE interface SET ... WHERE id_interface = ? RETURNING
4. conn.commit()
```

### DELETE VLAN (vlan.py)
```
1. Libérer interfaces: UPDATE interface SET vlan_id = NULL WHERE vlan_id = id_vlan
2. DELETE FROM vlan WHERE id_vlan = id_vlan RETURNING
3. SSH Delete via network.deploy_vlan.run_delete()
4. conn.commit() (réussit même si SSH échoue)

⚠️  BDD + interface.vlan_id sont libérées (source de vérité)
    SSH peut échouer → warning au client (non-blocking)
```

### DELETE INTERFACE (interface.py)
```
1. DELETE FROM interface WHERE id_interface = ? RETURNING
2. conn.commit()

Note: Pas de SSH delete (juste BD)
```

---

## 4. RÉPONSES JSON - Cohérence

### Structure commune (vlan.py)
```json
{
  "success": true,
  "message": "...",
  "count": 10,
  "vlans": [...],
  "vlan": {single_object},
  "error": "...",
  "warning": "...",
  "ssh_deploy": {result},
  "ssh_delete": {result},
  "ports_synced": 5
}
```

### Structure commune (interface.py)
```json
{
  "success": true,
  "message": "...",
  "count": 10,
  "interfaces": [...],
  "interface": {single_object},
  "error": "..."
}
```

---

## 5. LOGGING - Traçabilité BD

### vlan.py - Patterns
```python
logger.info(f"[API] GET VLANs: {len(vlans)} VLANs retrouvés")
logger.info(f"[API] GET switchs: {len(switchs)} switches retrouvés")
logger.info(f"[API] CREATE VLAN {id} '{nom}' → SSH ✓ + BDD ✓ + {ports_synced} ports synced")
logger.info(f"[API] UPDATE VLAN {id} → BDD ✓ + {ports_synced} ports synced")
logger.info(f"[API] DELETE VLAN {id} → BDD ✓ (SSH: {'✓' if success else '✗'})")
logger.warning(f"[API] Erreur validation create_vlan: {str(e)}")
logger.exception(f"[API] Erreur get_vlans")
```

### interface.py - Patterns
```python
logger.info(f"[API] GET interfaces pour switch_id={id}")
logger.info(f"[API] Interface {nom} créée avec succès (switch_id={id})")
logger.warning(f"[API] Interface {id} introuvable")
logger.exception(f"[API] Erreur create_interface")
```

---

## 6. GESTION DES ERREURS - Cohérence

### vlan.py
```python
try:
    payload = normalize_vlan_payload(request.get_json())
except ValueError as e:
    logger.warning(f"[API] Erreur validation: {str(e)}")
    return jsonify({"success": False, "error": str(e)}), 400

try:
    # DB operations
    conn.commit()
except Exception as e:
    conn.rollback()
    logger.exception(f"[API] Erreur operation")
    return jsonify({"success": False, "error": str(e)}), 500
finally:
    conn.close()
```

### interface.py - Même pattern ✅
```python
try:
    payload = normalize_interface_payload(request.get_json(), cur=cur)
except ValueError as e:
    logger.warning(f"[API] Erreur validation: {str(e)}")
    return jsonify({"success": False, "error": str(e)}), 400

try:
    # DB operations
    conn.commit()
except Exception as e:
    conn.rollback()
    logger.exception(f"[API] Erreur operation")
    return jsonify({"success": False, "error": str(e)}), 500
finally:
    conn.close()
```

---

## 7. SYNCHRONISATION BIDIRECTIONNELLE - Spécifique VLAN

### Problème résolu
```
AVANT: vlan.ports était "source de vérité"
       → Interface.vlan_id ne reflétait pas la réalité

APRÈS: interface.vlan_id est "source de vérité"
       → GET /api/vlan enrichit les données depuis interface
       → CREATE/UPDATE/DELETE VLAN sync automatiquement interface.vlan_id
```

### Implémentation
```python
# Dans sync_ports_to_interface():
1. UPDATE interface SET vlan_id = NULL WHERE vlan_id = id_vlan
   -- Libère les anciennes interfaces assignées
2. FOR EACH port IN canonical_ports:
     UPDATE interface SET vlan_id = id_vlan WHERE nom = port
   -- Assigne les nouvelles interfaces
3. logger.info("sync_ports_to_interface: VLAN %s → %d interface(s)", id_vlan, updated)
```

---

## 8. RÉSUMÉ - Checklist de Cohérence

| Aspect | vlan.py | interface.py | Status |
|--------|---------|--------------|--------|
| **Validation** | ✅ normalize_vlan_payload() | ✅ normalize_interface_payload() | ✅ Cohérent |
| **Jointures BD** | ✅ switch_name→switchs→id_switch | ✅ switch_name→switchs→id_switch | ✅ Cohérent |
| **Jointures BD** | ✅ ports→interface validation | ✅ vlan_id→vlan validation | ✅ Cohérent |
| **Erreurs** | ✅ try/except + jsonify(400/500) | ✅ try/except + jsonify(400/500) | ✅ Cohérent |
| **Logging** | ✅ [API] prefix + contexte | ✅ [API] prefix + contexte | ✅ Cohérent |
| **Transactionnel** | ✅ conn.commit() + conn.rollback() | ✅ conn.commit() + conn.rollback() | ✅ Cohérent |
| **RealDictCursor** | ✅ cursor_factory=RealDictCursor | ✅ cursor_factory=RealDictCursor | ✅ Cohérent |
| **Réponses JSON** | ✅ success/message/error/count | ✅ success/message/error/count | ✅ Cohérent |

---

## 9. Flux d'Utilisation - Exemple

### Client
```json
POST /api/vlan
{
  "id_vlan": 100,
  "nom": "VLAN_MGT",
  "gateway": "192.168.1.1",
  "switchName": "CORE-01",
  "ports": "Gi1/0/1, Gi1/0/2"
}
```

### Backend vlan.py
```
1. normalize_vlan_payload() → validation
2. resolve_switch_id(cur, {"switchName": "CORE-01"})
   → SELECT id_switch FROM switchs WHERE nom = 'CORE-01' → 5
3. validate_port_assignments(cur, "Gi1/0/1, Gi1/0/2", id_switch=5)
   → SELECT nom FROM interface WHERE id_switch = 5
   → ✅ Gi1/0/1, Gi1/0/2 existent → retourne noms canoniques
4. network.deploy_vlan.run_deploy() → SSH au switch ✅
5. INSERT INTO vlan (id_vlan, nom, gateway, switch_name, ports) VALUES (100, 'VLAN_MGT', '192.168.1.1', 'CORE-01', 'Gi1/0/1, Gi1/0/2')
6. sync_ports_to_interface(cur, 100, 'Gi1/0/1, Gi1/0/2', id_switch=5)
   → UPDATE interface SET vlan_id = 100 WHERE nom = 'Gi1/0/1' OR nom = 'Gi1/0/2'
7. conn.commit()
```

### Réponse
```json
{
  "success": true,
  "message": "VLAN 100 'VLAN_MGT' créé...",
  "vlan": {...},
  "ssh_deploy": {"success": true, "message": "..."},
  "ports_synced": 2
}
```

---

## ✅ Conclusion

**vlan.py est maintenant lié à la BD exactement comme interface.py**:
- ✅ Validation des données normalisée
- ✅ Jointures BD cohérentes (switch_name→switchs, ports→interface)
- ✅ Gestion transactionnelle (commit/rollback)
- ✅ Logging structuré avec [API] prefix
- ✅ Réponses JSON cohérentes (success/error/count)
- ✅ Synchronisation bidirectionnelle interface.vlan_id
- ✅ Atomicité: SSH d'abord, BDD ensuite (ou rollback)

