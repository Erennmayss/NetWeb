#!/usr/bin/env python3
"""
Script de test - Vérifier la synchronisation VLAN ↔ Interface

Usage:
  python3 test_vlan_sync.py
  
Cela teste:
1. Récupération des switches
2. Récupération des interfaces d'un switch
3. Création d'un VLAN avec les bons noms d'interface
4. Vérification de la synchronisation en BD
"""

import requests
import json
import sys

BASE_URL = "http://localhost:5000"

def test_get_switchs():
    print("\n" + "="*60)
    print("TEST 1: Récupérer les switches")
    print("="*60)
    try:
        resp = requests.get(f"{BASE_URL}/api/switchs")
        data = resp.json()
        print(f"✅ Status: {resp.status_code}")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        
        if data.get("success") and data.get("switchs"):
            return data["switchs"][0]["id"]
        else:
            print("❌ Aucun switch trouvé!")
            return None
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return None

def test_get_interfaces(switch_id):
    print("\n" + "="*60)
    print(f"TEST 2: Récupérer les interfaces du switch {switch_id}")
    print("="*60)
    try:
        resp = requests.get(f"{BASE_URL}/api/switch/{switch_id}/interfaces")
        data = resp.json()
        print(f"✅ Status: {resp.status_code}")
        print(f"Switch: {data.get('switch_name')}")
        print(f"Total interfaces: {data.get('count')}")
        
        if data.get("interfaces"):
            print("\nPremières interfaces:")
            for iface in data["interfaces"][:5]:
                print(f"  - {iface['nom']} (vlan_id={iface['vlan_id']}, status={iface['status']})")
            
            # Retourner les 3 premiers noms d'interface pour le test
            return [iface["nom"] for iface in data["interfaces"][:3]]
        else:
            print("❌ Aucune interface trouvée!")
            return None
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return None

def test_create_vlan(switch_id, interface_names):
    print("\n" + "="*60)
    print(f"TEST 3: Créer un VLAN TEST (id=999)")
    print("="*60)
    
    payload = {
        "id_vlan": 999,
        "nom": "VLAN_TEST",
        "gateway": "10.99.99.1",
        "switchName": "Test_Switch",  # ← Sera résolu via switchs table
        "ports": ", ".join(interface_names)  # ← Noms RÉELS des interfaces
    }
    
    print(f"Payload:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    
    try:
        resp = requests.post(
            f"{BASE_URL}/api/vlan",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        data = resp.json()
        print(f"\n✅ Status: {resp.status_code}")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        
        if data.get("success"):
            print(f"\n✅ VLAN créé avec succès!")
            print(f"   - id_vlan: {data['vlan']['id_vlan']}")
            print(f"   - nom: {data['vlan']['nom']}")
            print(f"   - ports: {data['vlan']['ports']}")
            print(f"   - ports_synced: {data.get('ports_synced')} interfaces")
            return True
        else:
            print(f"\n❌ Erreur: {data.get('error')}")
            return False
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return False

def test_get_vlan(vlan_id):
    print("\n" + "="*60)
    print(f"TEST 4: Vérifier que le VLAN {vlan_id} est bien créé")
    print("="*60)
    try:
        resp = requests.get(f"{BASE_URL}/api/vlan")
        data = resp.json()
        print(f"✅ Status: {resp.status_code}")
        
        vlans = data.get("vlans", [])
        target_vlan = next((v for v in vlans if v["id_vlan"] == vlan_id), None)
        
        if target_vlan:
            print(f"\n✅ VLAN trouvé!")
            print(json.dumps(target_vlan, indent=2, ensure_ascii=False))
            
            print(f"\n🔍 Vérification:")
            print(f"   - id_vlan: {target_vlan['id_vlan']}")
            print(f"   - nom: {target_vlan['nom']}")
            print(f"   - ports: {target_vlan['ports']}")
            print(f"   - gateway: {target_vlan['gateway']}")
            
            return True
        else:
            print(f"❌ VLAN {vlan_id} pas trouvé!")
            return False
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return False

def test_delete_vlan(vlan_id):
    print("\n" + "="*60)
    print(f"TEST 5: Supprimer le VLAN TEST {vlan_id}")
    print("="*60)
    try:
        resp = requests.delete(f"{BASE_URL}/api/vlan/{vlan_id}")
        data = resp.json()
        print(f"✅ Status: {resp.status_code}")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        
        if data.get("success"):
            print(f"\n✅ VLAN supprimé!")
            return True
        else:
            print(f"\n❌ Erreur: {data.get('error')}")
            return False
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return False

def main():
    print("\n" + "🧪 "*30)
    print("TEST SUITE - Synchronisation VLAN ↔ Interface")
    print("🧪 "*30)
    
    print(f"\nServeur: {BASE_URL}")
    
    # Test 1: Récupérer les switches
    switch_id = test_get_switchs()
    if not switch_id:
        print("\n❌ Impossible de continuer: aucun switch trouvé")
        sys.exit(1)
    
    # Test 2: Récupérer les interfaces
    interfaces = test_get_interfaces(switch_id)
    if not interfaces:
        print("\n❌ Impossible de continuer: aucune interface trouvée")
        sys.exit(1)
    
    # Test 3: Créer un VLAN
    success = test_create_vlan(switch_id, interfaces)
    
    # Test 4: Vérifier que le VLAN est créé
    if success:
        test_get_vlan(999)
    
    # Test 5: Supprimer le VLAN
    if success:
        test_delete_vlan(999)
    
    print("\n" + "🧪 "*30)
    print("TESTS TERMINÉS")
    print("🧪 "*30 + "\n")

if __name__ == "__main__":
    main()
