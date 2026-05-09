-- 📊 REQUÊTES SQL - JOINTURES ALERTES & REGLES SNORT
-- Fichier: Backend/sql/alerts_regles_joins.sql

-- ═══════════════════════════════════════════════════════════════════════════
-- SCHÉMA REQUIS
-- ═══════════════════════════════════════════════════════════════════════════

-- Table ALERTES
CREATE TABLE IF NOT EXISTS alertes (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    source_ip VARCHAR(45),
    destination_ip VARCHAR(45),
    attack_type VARCHAR(255),
    severity VARCHAR(50),
    detection_engine VARCHAR(100),
    details TEXT,
    protocol VARCHAR(10),
    source_port INT,
    destination_port INT,
    loss INT DEFAULT 0,
    volume INT DEFAULT 0,
    service VARCHAR(100)
);

-- Table REGLES SNORT
CREATE TABLE IF NOT EXISTS regles (
    id SERIAL PRIMARY KEY,
    sid INT UNIQUE,                    -- Snort ID (ex: 2100498)
    message VARCHAR(255),              -- Message de la règle (ex: Auto-FTP-Patator)
    protocol VARCHAR(10),              -- TCP, UDP, ICMP, etc
    src_ip VARCHAR(255) DEFAULT 'any',
    src_port VARCHAR(255) DEFAULT 'any',
    dst_ip VARCHAR(255) DEFAULT 'any',
    dst_port VARCHAR(255) DEFAULT 'any',
    action VARCHAR(50) DEFAULT 'alert', -- alert, drop, reject, etc
    rule TEXT                          -- Règle Snort complète
);

-- ═══════════════════════════════════════════════════════════════════════════
-- 1. REQUÊTE DE JOINTURE - ALERTES + REGLES
-- ═══════════════════════════════════════════════════════════════════════════

-- ✅ Récupérer tous les alertes avec les infos des règles correspondantes
SELECT 
    -- Infos ALERTES
    a.id as alert_id,
    a.timestamp,
    a.source_ip,
    a.destination_ip,
    a.attack_type,
    a.severity,
    a.detection_engine,
    a.details,
    a.protocol,
    a.source_port,
    a.destination_port,
    a.loss,
    a.volume,
    a.service,
    -- ✅ Infos REGLES (jointure)
    r.sid as rule_sid,
    r.message as rule_message,
    r.protocol as rule_protocol,
    r.src_ip as rule_src_ip,
    r.src_port as rule_src_port,
    r.dst_ip as rule_dst_ip,
    r.dst_port as rule_dst_port,
    r.action as rule_action,
    r.rule as rule_text
FROM alertes a
LEFT JOIN regles r ON LOWER(a.attack_type) = LOWER(r.message)
                      OR a.attack_type ILIKE '%' || r.message || '%'
ORDER BY a.timestamp DESC
LIMIT 100;

-- ─────────────────────────────────────────────────────────────────────────
-- 2. JOINTURE STRICTE - Uniquement alertes avec règle correspondante
-- ─────────────────────────────────────────────────────────────────────────

SELECT 
    a.id, a.timestamp, a.attack_type, a.severity,
    r.sid, r.message, r.action, r.rule
FROM alertes a
INNER JOIN regles r ON LOWER(a.attack_type) = LOWER(r.message)
ORDER BY a.timestamp DESC;

-- ─────────────────────────────────────────────────────────────────────────
-- 3. ALERTES PAR SID (Signature ID)
-- ─────────────────────────────────────────────────────────────────────────

SELECT 
    r.sid,
    r.message,
    COUNT(a.id) as total_alerts,
    MAX(a.timestamp) as last_triggered
FROM alertes a
INNER JOIN regles r ON LOWER(a.attack_type) = LOWER(r.message)
GROUP BY r.sid, r.message
ORDER BY total_alerts DESC;

-- ─────────────────────────────────────────────────────────────────────────
-- 4. DERNIÈRE ALERTE AVEC RULE
-- ─────────────────────────────────────────────────────────────────────────

SELECT 
    a.id,
    a.timestamp,
    a.attack_type,
    a.details,
    a.protocol,
    a.severity,
    a.source_ip,
    a.destination_ip,
    r.sid as rule_sid,
    r.message as rule_message,
    r.action as rule_action,
    r.rule as rule_text
FROM alertes a
LEFT JOIN regles r ON LOWER(a.attack_type) = LOWER(r.message)
                      OR a.attack_type ILIKE '%' || r.message || '%'
ORDER BY a.timestamp DESC
LIMIT 1;

-- ═══════════════════════════════════════════════════════════════════════════
-- 5. INSERTION DE DONNEES DE TEST
-- ═══════════════════════════════════════════════════════════════════════════

-- Insérer des règles Snort de test
INSERT INTO regles (sid, message, protocol, action, rule) VALUES
(2100498, 'Auto-FTP-Patator-HighPacketRate', 'TCP', 'alert', 
 'alert tcp $EXTERNAL_NET any -> $HOME_NET 21 (msg:"Auto-FTP-Patator-HighPacketRate"; threshold:type both,track by_src,count 50,seconds 10; sid:2100498; rev:1;)'),
 
(2100499, 'Auto-Heartbleed-HighPacketRate', 'TCP', 'alert',
 'alert tcp $EXTERNAL_NET any -> $HOME_NET 443 (msg:"Auto-Heartbleed-HighPacketRate"; threshold:type both,track by_src,count 50,seconds 10; sid:2100499; rev:1;)'),
 
(2100500, 'Auto-Heartbleed-SYN', 'TCP', 'alert',
 'alert tcp $EXTERNAL_NET any -> $HOME_NET 443 (flags:S; msg:"Auto-Heartbleed-SYN"; threshold:type both,track by_src,count 20,seconds 5; sid:2100500; rev:1;)'),
 
(2100501, 'Auto-Infiltration-Portscan-SYN', 'TCP', 'alert',
 'alert tcp $EXTERNAL_NET any -> $HOME_NET any (flags:S; msg:"Auto-Infiltration-Portscan-SYN"; threshold:type both,track by_src,count 30,seconds 5; sid:2100501; rev:1;)'),
 
(2100502, 'Auto-Botnet-SYN', 'TCP', 'alert',
 'alert tcp $EXTERNAL_NET any -> $HOME_NET any (flags:S; msg:"Auto-Botnet-SYN"; threshold:type both,track by_src,count 40,seconds 10; sid:2100502; rev:1;)');

-- Insérer des alertes de test
INSERT INTO alertes (source_ip, destination_ip, attack_type, severity, detection_engine, details, protocol, source_port, destination_port) VALUES
('192.168.56.106', '192.168.56.104', 'Auto-FTP-Patator-HighPacketRate', 'critical', 'Snort', 'FTP Brute Force Attack detected from 192.168.56.106:46166', 'TCP', 46166, 21),
('192.168.56.106', '192.168.56.104', 'Auto-Heartbleed-HighPacketRate', 'critical', 'Snort', 'Heartbleed exploit attempt from 192.168.56.106:46180', 'TCP', 46180, 443),
('192.168.56.106', '192.168.56.104', 'Auto-Heartbleed-SYN', 'medium', 'Snort', 'SYN Flood from 192.168.56.106:46190', 'TCP', 46190, 443);

-- ═══════════════════════════════════════════════════════════════════════════
-- 6. CONVERTIR PAYLOAD EN HEX (pour affichage)
-- ═══════════════════════════════════════════════════════════════════════════

-- Fonction PostgreSQL pour convertir du texte en hexadécimal
CREATE OR REPLACE FUNCTION text_to_hex(p_text TEXT) RETURNS TEXT AS $$
BEGIN
    RETURN encode(p_text::bytea, 'hex');
END;
$$ LANGUAGE plpgsql;

-- Utiliser la fonction
SELECT 
    id,
    details,
    text_to_hex(details) as payload_hex
FROM alertes
WHERE details IS NOT NULL
LIMIT 10;

-- ═══════════════════════════════════════════════════════════════════════════
-- 7. VÉRIFIER LES ALERTES SANS RÈGLE CORRESPONDANTE
-- ═══════════════════════════════════════════════════════════════════════════

SELECT 
    a.id,
    a.timestamp,
    a.attack_type,
    COUNT(*) as total
FROM alertes a
LEFT JOIN regles r ON LOWER(a.attack_type) = LOWER(r.message)
                      OR a.attack_type ILIKE '%' || r.message || '%'
WHERE r.id IS NULL
GROUP BY a.id, a.timestamp, a.attack_type
ORDER BY a.timestamp DESC;

-- ═══════════════════════════════════════════════════════════════════════════
-- 8. STATISTIQUES - ALERTES PAR SÉVÉRITÉ AVEC RÈGLES
-- ═══════════════════════════════════════════════════════════════════════════

SELECT 
    a.severity,
    COUNT(a.id) as total_alerts,
    COUNT(DISTINCT r.id) as matched_rules,
    COUNT(DISTINCT a.source_ip) as unique_sources
FROM alertes a
LEFT JOIN regles r ON LOWER(a.attack_type) = LOWER(r.message)
                      OR a.attack_type ILIKE '%' || r.message || '%'
GROUP BY a.severity
ORDER BY total_alerts DESC;

-- ═══════════════════════════════════════════════════════════════════════════
-- 9. TOP 10 ALERTES AVEC PLUS D'OCCURRENCES
-- ═══════════════════════════════════════════════════════════════════════════

SELECT 
    a.attack_type,
    r.sid,
    r.message,
    r.action,
    COUNT(a.id) as occurrence_count,
    MAX(a.timestamp) as last_detected
FROM alertes a
LEFT JOIN regles r ON LOWER(a.attack_type) = LOWER(r.message)
                      OR a.attack_type ILIKE '%' || r.message || '%'
GROUP BY a.attack_type, r.sid, r.message, r.action
ORDER BY occurrence_count DESC
LIMIT 10;

