import json, unittest
from pathlib import Path
P=Path(__file__).parent
class Phase7Tests(unittest.TestCase):
 def test_contract_persisted(self):
  d=json.loads((P/'option-chain-live.json').read_text()); self.assertTrue(d['persistence']); self.assertEqual(d['records'],[]); self.assertEqual(d['underlyings'],[])
 def test_no_unverified_derivative_requirements(self):
  d=json.loads((P/'option_requirements.json').read_text()); self.assertEqual(d['universe'],'only stocks whose specialist engine explicitly requires derivatives data; do not fabricate derivative requirements for stocks that do not')
if __name__=='__main__': unittest.main()
