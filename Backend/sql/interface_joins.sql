-- 📊 REQUÊTES SQL COMPLÈTES - JOINTURES INTERFACE, VLAN & SWITCHS
-- Fichier: Backend/sql/interface_joins.sql

-- ═══════════════════════════════════════════════════════════════════════════
-- 1. RÉCUPÉRER TOUTES LES INTERFACES AVEC INFOS SWITCH & VLAN
-- ═══════════════════════════════════════════════════════════════════════════

SELECT 
    i.id_interface, 
    i.nom, 
    i.ip, 
    i.vlan_id, 
    i.id_switch, 
    i.equipement_id, 
    i.status, 
    i.mode, 
    i.type, 
    i.speed, 
    i.allowed_vlans, 
    i.port_security, 
    i.max_mac, 
    i.violation_mode, 
    i.bpdu_guard,
    -- ✅ Infos du Switch (jointure 1)
    s.nom as switch_name, 
    s.ip as switch_ip,
    s.username as switch_username,
    s.password as switch_password,
    -- ✅ Infos du VLAN (jointure 2)
    v.nom as vlan_name, 
    v.reseau as vlan_reseau,
    v.gateway as vlan_gateway
FROM interface i
LEFT JOIN switchs s ON i.id_switch = s.id_switch
LEFT JOIN vlan v ON i.vlan_id = v.id_vlan
ORDER BY i.id_switch, i.id_interface ASC;

-- ─────────────────────────────────────────────────────────────────────────
-- 2. RÉCUPÉRER LES INTERFACES D'UN SWITCH SPÉCIFIQUE
-- ─────────────────────────────────────────────────────────────────────────

SELECT 
    i.id_interface, 
    i.nom, 
    i.ip, 
    i.vlan_id, 
    i.id_switch, 
    i.status, 
    i.mode, 
    i.type,
    -- ✅ Infos du Switch
    s.nom as switch_name, 
    s.ip as switch_ip,
    s.username as switch_username,
    s.password as switch_password,
    -- ✅ Infos du VLAN
    v.nom as vlan_name, 
    v.reseau as vlan_reseau
FROM interface i
LEFT JOIN switchs s ON i.id_switch = s.id_switch
LEFT JOIN vlan v ON i.vlan_id = v.id_vlan
WHERE i.id_switch = 1  -- Remplacer 1 par l'id_switch désiré
ORDER BY i.id_interface ASC;

-- ─────────────────────────────────────────────────────────────────────────
-- 3. RÉCUPÉRER UN SWITCH PAR SON NOM
-- ─────────────────────────────────────────────────────────────────────────

SELECT 
    id_switch, 
    nom, 
    ip, 
    masque, 
    username, 
    password, 
    nb_ports, 
    status
FROM switchs
WHERE nom = 'Cisco_Switch'  -- Remplacer par le nom du switch
LIMIT 1;

-- ─────────────────────────────────────────────────────────────────────────
-- 4. RÉCUPÉRER LES CREDENTIALS D'UN SWITCH POUR SSH
-- ─────────────────────────────────────────────────────────────────────────

SELECT 
    id_switch, 
    nom, 
    ip, 
    username, 
    password
FROM switchs
WHERE id_switch = 1;  -- Remplacer 1 par l'id_switch désiré

-- ─────────────────────────────────────────────────────────────────────────
-- 5. VÉRIFIER QU'UN VLAN EXISTE AVANT DE L'ASSIGNER
-- ─────────────────────────────────────────────────────────────────────────

SELECT 
    id_vlan, 
    nom, 
    reseau, 
    gateway
FROM vlan
WHERE id_vlan = 10  -- Remplacer 10 par l'id_vlan désiré
LIMIT 1;

-- ─────────────────────────────────────────────────────────────────────────
-- 6. VÉRIFIER QU'UN SWITCH EXISTE AVANT INSERTION
-- ─────────────────────────────────────────────────────────────────────────

SELECT 1
FROM switchs
WHERE id_switch = 1;  -- Remplacer 1 par l'id_switch désiré

-- ═══════════════════════════════════════════════════════════════════════════
-- 7. INSÉRER UNE NOUVELLE INTERFACE
-- ═══════════════════════════════════════════════════════════════════════════

INSERT INTO interface (
    nom, 
    ip, 
    vlan_id, 
    id_switch,          -- ✅ Clé étrangère vers switchs
    equipement_id, 
    status, 
    mode, 
    type,
    speed, 
    allowed_vlans, 
    port_security, 
    max_mac, 
    violation_mode, 
    bpdu_guard
)
VALUES (
    'Gi1/0/1',          -- nom
    '192.168.1.100',    -- ip
    10,                 -- vlan_id (doit exister dans vlan table)
    1,                  -- id_switch (doit exister dans switchs table) ✅
    NULL,               -- equipement_id
    'UP',               -- status
    'access',           -- mode
    'access',           -- type
    '1Gb',              -- speed
    NULL,               -- allowed_vlans
    TRUE,               -- port_security
    1,                  -- max_mac
    'shutdown',         -- violation_mode
    TRUE                -- bpdu_guard
)
RETURNING 
    id_interface, 
    nom, 
    ip, 
    vlan_id, 
    id_switch;

-- ─────────────────────────────────────────────────────────────────────────
-- 8. METTRE À JOUR UNE INTERFACE
-- ─────────────────────────────────────────────────────────────────────────

UPDATE interface
SET 
    vlan_id = 20,               -- Changer le VLAN
    status = 'DOWN',            -- Changer le statut
    id_switch = 1,              -- ✅ Peut changer le switch
    port_security = FALSE,
    bpdu_guard = FALSE
WHERE id_interface = 1          -- Remplacer 1 par l'id_interface
RETURNING 
    id_interface, 
    nom, 
    ip, 
    vlan_id, 
    id_switch;

-- ═══════════════════════════════════════════════════════════════════════════
-- 9. STATISTIQUES - INTERFACES PAR SWITCH
-- ═══════════════════════════════════════════════════════════════════════════

SELECT 
    s.nom as switch_name,
    s.ip as switch_ip,
    COUNT(i.id_interface) as total_interfaces,
    SUM(CASE WHEN i.status = 'UP' THEN 1 ELSE 0 END) as interfaces_up,
    SUM(CASE WHEN i.status = 'DOWN' THEN 1 ELSE 0 END) as interfaces_down,
    SUM(CASE WHEN i.port_security = TRUE THEN 1 ELSE 0 END) as with_port_security
FROM switchs s
LEFT JOIN interface i ON s.id_switch = i.id_switch
GROUP BY s.id_switch, s.nom, s.ip
ORDER BY s.nom;

-- ─────────────────────────────────────────────────────────────────────────
-- 10. STATISTIQUES - INTERFACES PAR VLAN
-- ─────────────────────────────────────────────────────────────────────────

SELECT 
    v.nom as vlan_name,
    v.id_vlan,
    COUNT(i.id_interface) as total_interfaces,
    COUNT(DISTINCT i.id_switch) as switches_utilises
FROM vlan v
LEFT JOIN interface i ON v.id_vlan = i.vlan_id
GROUP BY v.id_vlan, v.nom
ORDER BY v.nom;

-- ═══════════════════════════════════════════════════════════════════════════
-- 11. VÉRIFIER L'INTÉGRITÉ DES CLÉS ÉTRANGÈRES
-- ═══════════════════════════════════════════════════════════════════════════

-- Vérifier les interfaces avec des id_switch invalides
SELECT i.id_interface, i.nom, i.id_switch
FROM interface i
LEFT JOIN switchs s ON i.id_switch = s.id_switch
WHERE i.id_switch IS NOT NULL AND s.id_switch IS NULL;

-- Vérifier les interfaces avec des vlan_id invalides
SELECT i.id_interface, i.nom, i.vlan_id
FROM interface i
LEFT JOIN vlan v ON i.vlan_id = v.id_vlan
WHERE i.vlan_id IS NOT NULL AND v.id_vlan IS NULL;

-- ═══════════════════════════════════════════════════════════════════════════
-- 12. CAS PARTICULIER - INTERFACE AVEC NOM DE SWITCH AU LIEU D'ID
-- ═══════════════════════════════════════════════════════════════════════════

-- Si vous devez convertir un nom de switch en id_switch:
SELECT 
    i.id_interface,
    i.nom,
    i.id_switch,
    s.id_switch as switch_id_from_name,
    s.nom as switch_name
FROM interface i
INNER JOIN switchs s ON i.nom LIKE CONCAT('%', s.nom, '%')
LIMIT 10;

-- ─────────────────────────────────────────────────────────────────────────
-- 13. EXEMPLE COMPLET - CRÉER UNE INTERFACE AVEC TOUTES LES VÉRIFICATIONS
-- ─────────────────────────────────────────────────────────────────────────

-- Étape 1: Vérifier que le switch existe
SELECT id_switch, nom, ip FROM switchs WHERE nom = 'Cisco_Switch';

-- Étape 2: Vérifier que le VLAN existe
SELECT id_vlan, nom, reseau FROM vlan WHERE id_vlan = 10;

-- Étape 3: Insérer l'interface (avec les id vérifiés)
BEGIN;
INSERT INTO interface (nom, ip, vlan_id, id_switch, status, mode, type, port_security, max_mac, violation_mode, bpdu_guard)
VALUES ('Gi1/0/1', '192.168.1.100', 10, 1, 'UP', 'access', 'access', TRUE, 1, 'shutdown', TRUE);
COMMIT;

-- Étape 4: Vérifier avec jointure
SELECT 
    i.id_interface, i.nom, i.ip, i.status,
    s.nom as switch_name, s.ip as switch_ip,
    v.nom as vlan_name, v.reseau as vlan_reseau
FROM interface i
LEFT JOIN switchs s ON i.id_switch = s.id_switch
LEFT JOIN vlan v ON i.vlan_id = v.id_vlan
WHERE i.nom = 'Gi1/0/1';

