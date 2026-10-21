import json
import unittest
from pathlib import Path
D = json.loads((Path(__file__).resolve().parents[1] / "contracts" / "SPELL_ID_REGISTRY_v2.json").read_text())
NAMES={145:"Light Lance",146:"Radiant Fracture",147:"Light Imbuement",148:"Dawnfall",149:"Sacred Flame",150:"Radiant Horizon",151:"Light Atomic"}
class LightMagickRegistryTests(unittest.TestCase):
    def test_entries_unique(self):
        ids=[int(row["id"]) for row in D["id_index"]]
        self.assertEqual(len(ids),151)
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(D["counts"]["unique_spell_ids"],151)
    def test_new_mappings(self):
        rows={int(r["id"]):r for r in D["id_index"]}
        for n,name in NAMES.items():
            self.assertEqual(rows[n]["name"],name)
            self.assertEqual(rows[n]["schools"],["Light Magick"])
            self.assertEqual(rows[n]["category"],"support" if n==147 else "offensive")
    def test_legacy_spell_ids_preserved(self):
        rows={int(r["id"]):r for r in D["id_index"]}
        self.assertEqual(rows[98]["name"],"Chakra Heal")
        self.assertEqual(rows[99]["name"],"Aura Shielding")
        self.assertEqual(rows[144]["name"],"Rebirth Bloom")
if __name__=="__main__":unittest.main()
