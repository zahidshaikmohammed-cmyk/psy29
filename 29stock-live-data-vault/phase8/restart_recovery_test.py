import os
import unittest

class RestartRecoveryTests(unittest.TestCase):
    def test_database_url_is_external_persistent_dependency(self):
        self.assertTrue(os.environ.get("DATABASE_URL"), "DATABASE_URL must be supplied by the persistent database provider")

    def test_schema_contains_immutable_unique_keys(self):
        from pathlib import Path
        schema = Path(__file__).with_name("schema.sql").read_text()
        self.assertIn("UNIQUE(symbol, snapshot_minute)", schema)
        self.assertIn("UNIQUE(symbol, timeframe, candle_start)", schema)
        self.assertIn("archive_manifest", schema)

if __name__ == "__main__":
    unittest.main()
