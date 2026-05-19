ALTER TABLE interface
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS duplex VARCHAR(32);

ALTER TABLE switchs
    ADD COLUMN IF NOT EXISTS last_sync_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_sync_error TEXT;

CREATE INDEX IF NOT EXISTS idx_interface_switch_nom
    ON interface (id_switch, nom);

CREATE INDEX IF NOT EXISTS idx_interface_switch_vlan
    ON interface (id_switch, vlan_id);
