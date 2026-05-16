# 🚀 VLAN SYNC - QUICK START

## ⚡ 5 Minutes pour Commencer

### 1. Vérifier les Noms des Interfaces

```bash
curl http://localhost:5000/api/switch/5/interfaces
```

Résultat: Vous voyez les VRAIS noms (ex: `Gi1/0/1`, `Gi1/0/2`, etc.)

### 2. Créer un VLAN Avec les Bons Noms

```bash
curl -X POST http://localhost:5000/api/vlan \
  -H "Content-Type: application/json" \
  -d '{
    "id_vlan": 20,
    "nom": "TEST_VLAN",
    "gateway": "10.20.20.1",
    "switchName": "Core_SW",
    "ports": "Gi1/0/1, Gi1/0/2"
  }'
```

✅ **Vérifier dans la réponse:**
```json
{
  "success": true,
  "ports_synced": 2,
  "vlan": {
    "ports": "Gi1/0/1, Gi1/0/2"
  }
}
```

### 3. Vérifier en BD

```sql
-- 1. Vérifier que vlan.ports a les noms RÉELS
SELECT ports FROM vlan WHERE id_vlan = 20;
-- Résultat: "Gi1/0/1, Gi1/0/2"

-- 2. Vérifier que interface.vlan_id est synchronisé
SELECT nom, vlan_id FROM interface WHERE vlan_id = 20;
-- Résultat: 2 lignes (Gi1/0/1, Gi1/0/2)
```

### 4. Mettre à Jour le VLAN

```bash
curl -X PUT http://localhost:5000/api/vlan/20 \
  -H "Content-Type: application/json" \
  -d '{
    "ports": "Gi1/0/1, Gi1/0/3"
  }'
```

✅ **Résultat:**
- Gi1/0/2 → vlan_id = NULL (libérée)
- Gi1/0/1 → vlan_id = 20 (garde)
- Gi1/0/3 → vlan_id = 20 (ajoutée)

### 5. Supprimer le VLAN

```bash
curl -X DELETE http://localhost:5000/api/vlan/20
```

✅ **Résultat:**
- Gi1/0/1, Gi1/0/3 → vlan_id = NULL (toutes libérées)
- VLAN 20 supprimé de la BD

---

## ❌ Erreurs Courantes et Solutions

| Erreur | Cause | Solution |
|--------|-------|----------|
| `Interface inexistante: g0/0/0` | Mauvais nom d'interface | Utiliser `GET /api/switch/{id}/interfaces` pour voir les vrais noms |
| `ports_synced: 0` | Ports ne correspondent pas | Vérifier les noms exacts (case-sensitive) |
| `VLAN créé mais ports non synchronisés` | Données OLD en BD | Faire un PUT pour forcer la re-sync |

---

## 📚 Documentation Complète

| Document | Contenu |
|----------|---------|
| `VLAN_SYNC_SUMMARY.md` | **Résumé complet des corrections** |
| `VLAN_SYNC_BEFORE_AFTER.md` | **Avant/Après visuel avec diagrams** |
| `VLAN_PORT_SYNC_FIXES.md` | **Guide détaillé de troubleshooting** |
| `DATABASE_LINKING_SUMMARY.md` | **Architecture BD et jointures** |
| `test_vlan_sync.py` | **Script de test automatisé** |

---

## 🧪 Tester Automatiquement

```bash
cd /path/to/Backend
python3 test_vlan_sync.py
```

Le script teste:
- ✅ Récupération des switches
- ✅ Affichage des interfaces
- ✅ Création d'un VLAN TEST
- ✅ Vérification de la synchronisation
- ✅ Suppression du VLAN TEST

---

## 🎯 Checklist Avant Production

- [ ] Backend redémarré
- [ ] Script test passe (`test_vlan_sync.py`)
- [ ] Créer un VLAN TEST et vérifier `ports_synced > 0`
- [ ] Vérifier en BD que `vlan.ports` = noms RÉELS
- [ ] Vérifier que `interface.vlan_id` est synchronisé
- [ ] Tester PUT: ajouter/retirer des ports
- [ ] Tester DELETE: interfaces libérées

---

## 📞 Si Ça ne Marche Pas

1. **Vérifier les logs du backend:**
   ```
   [API] CREATE VLAN 20 → SSH ✓ + BDD ✓ + 2 ports synced
   ```

2. **Appeler la nouvelle route:**
   ```bash
   curl http://localhost:5000/api/switch/5/interfaces
   ```
   Copier les noms exacts affichés

3. **Lire le troubleshooting:**
   Voir `VLAN_PORT_SYNC_FIXES.md`

---

## ✅ C'est Fait!

Les corrections sont actives. Vous pouvez maintenant:
- ✅ Créer des VLANs avec certitude
- ✅ Les ports se synchronisent automatiquement
- ✅ Les noms sont cohérents (RÉELS)
- ✅ Les updates/deletes reflètent la réalité

🎉 **Bon courage!**

