"""
Script to clean up orphaned VLAN references in the database.
This resolves the issue where VLAN 50 exists in interfaces but not in the vlan table.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psycopg2
from Database.db import get_db_connection

def cleanup_vlan_orphans():
    """Execute all database cleanup operations for orphaned VLANs"""
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        print("=" * 70)
        print("VLAN ORPHAN CLEANUP - Database Integrity Check")
        print("=" * 70)
        
        # Step 1: Verify VLAN 1 exists (default safe VLAN)
        print("\n[1/6] Verifying VLAN 1 exists (default VLAN)...")
        cursor.execute("SELECT id_vlan FROM vlan WHERE id_vlan = 1;")
        print("\n[1/6] Vérification de l'existence du VLAN 10 (Management)...")
        cursor.execute("SELECT id_vlan FROM vlan WHERE id_vlan = 10;")
        result = cursor.fetchall()
        if not result:
            print("⚠️  WARNING: VLAN 1 does not exist!")
            print("       Creating VLAN 1 as default...")
            print("⚠️  ATTENTION: Le VLAN 10 n'existe pas en base de données !")
            print("       Injection du VLAN 10 (SVI Management)...")
            cursor.execute("""
                INSERT INTO vlan (id_vlan, nom, reseau, gateway, type, status)
                VALUES (1, 'Default', '192.168.1.0/24', '192.168.1.1', 'Data', 'Active')
                VALUES (10, 'SVI_Management', '192.168.10.0/24', '192.168.10.1', 'Management', 'Active')
                ON CONFLICT (id_vlan) DO NOTHING;
            """)
            conn.commit()
            print("       ✓ VLAN 1 created")
        else:
            print("   ✓ VLAN 1 exists")
            print("   ✓ Le VLAN 10 est présent.")
        
        # Step 2: Find all orphaned VLANs (used by interfaces but don't exist in vlan table)
        print("\n[2/6] Identifying orphaned VLAN references...")
        cursor.execute("""
            SELECT DISTINCT i.vlan_id 
            FROM interface i 
            WHERE i.vlan_id IS NOT NULL 
            AND NOT EXISTS (SELECT 1 FROM vlan v WHERE v.id_vlan = i.vlan_id)
            ORDER BY i.vlan_id;
        """)
        orphaned_vlans = [row[0] for row in cursor.fetchall()]
        
        if orphaned_vlans:
            print(f"   Found {len(orphaned_vlans)} orphaned VLAN(s): {orphaned_vlans}")
        else:
            print("   ✓ No orphaned VLANs found")
            cursor.close()
            conn.close()
            print("\n" + "=" * 70)
            print("✓ DATABASE ALREADY CLEAN - No cleanup needed")
            print("=" * 70)
            return True
        
        # Step 3: For each orphaned VLAN, show affected interfaces
        print("\n[3/6] Identifying affected interfaces...")
        for orphan_vlan in orphaned_vlans:
            cursor.execute("""
                SELECT id_interface, nom, id_switch 
                FROM interface 
                WHERE vlan_id = %s
                ORDER BY nom;
            """, (orphan_vlan,))
            affected = cursor.fetchall()
            print(f"   VLAN {orphan_vlan}: {len(affected)} interface(s)")
            for iface_id, iface_nom, switch_id in affected:
                print(f"      - {iface_nom} (id={iface_id}, switch={switch_id})")
        
        # Step 4: Reassign orphaned interfaces to VLAN 1
        print("\n[4/6] Reassigning orphaned interfaces to VLAN 1...")
        print("\n[4/6] Réaffectation des interfaces orphelines vers le VLAN 10...")
        for orphan_vlan in orphaned_vlans:
            cursor.execute(
                "UPDATE interface SET vlan_id = 1 WHERE vlan_id = %s;",
                (orphan_vlan,)
            )
            cursor.execute("UPDATE interface SET vlan_id = 10 WHERE vlan_id = %s;", (orphan_vlan,))
            affected_count = cursor.rowcount
            print(f"   VLAN {orphan_vlan}: Updated {affected_count} interface(s)")
        
        conn.commit()
        
        # Step 5: Delete orphaned VLANs from vlan table
        print("\n[5/6] Deleting orphaned VLAN entries...")
        for orphan_vlan in orphaned_vlans:
            cursor.execute("DELETE FROM vlan WHERE id_vlan = %s;", (orphan_vlan,))
            deleted_count = cursor.rowcount
            print(f"   VLAN {orphan_vlan}: Deleted {deleted_count} VLAN record(s)")
        
        conn.commit()
        
        # Step 6: Verify cleanup - should return empty result
        print("\n[6/6] Verifying cleanup...")
        cursor.execute("""
            SELECT DISTINCT i.vlan_id 
            FROM interface i 
            WHERE i.vlan_id IS NOT NULL 
            AND NOT EXISTS (SELECT 1 FROM vlan v WHERE v.id_vlan = i.vlan_id);
        """)
        remaining_orphans = cursor.fetchall()
        
        if not remaining_orphans:
            print("   ✓ No orphaned VLAN references found - cleanup successful!")
        else:
            print(f"   ⚠️  WARNING: Found remaining orphans: {remaining_orphans}")
        
        # Show final interface distribution
        print("\n" + "-" * 70)
        print("Final Interface Distribution by VLAN:")
        print("-" * 70)
        cursor.execute("""
            SELECT vlan_id, COUNT(*) as count
            FROM interface 
            WHERE vlan_id IS NOT NULL 
            GROUP BY vlan_id 
            ORDER BY vlan_id;
        """)
        results = cursor.fetchall()
        print("VLAN_ID | Count")
        print("-" * 20)
        for vlan_id, count in results:
            print(f"{vlan_id:7} | {count}")
        
        cursor.close()
        conn.close()
        
        print("\n" + "=" * 70)
        print("✓ CLEANUP COMPLETED SUCCESSFULLY")
        print("=" * 70)
        return True
        
    except psycopg2.Error as e:
        print(f"\n❌ Database Error: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False
    except Exception as e:
        print(f"\n❌ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = cleanup_vlan_orphans()
    sys.exit(0 if success else 1)