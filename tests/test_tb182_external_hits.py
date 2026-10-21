import unittest
from stories_yggdrasil_osc.config import DEFAULT_CONFIG
from stories_yggdrasil_osc.controller import BridgeController

class TB182Tests(unittest.TestCase):
    def test_new_external_parameters(self):
        config = DEFAULT_CONFIG["parameters"]
        self.assertEqual(config["external_hit_weak"], "SoY_ExternalHitWeak")
        self.assertEqual(config["external_hit_average"], "SoY_ExternalHitAverage")

if __name__ == "__main__":
    unittest.main()
