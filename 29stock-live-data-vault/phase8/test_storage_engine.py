import os
import tempfile
import unittest
from pathlib import Path
from storage_engine import sha256_file, archive_verified

class Phase8StorageTests(unittest.TestCase):
    def test_checksum_and_manifest_verification(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "archive.bin"
            p.write_bytes(b"PSY29 archive")
            digest = sha256_file(p)
            manifest = Path(d) / "manifest.json"
            manifest.write_text('{"trading_date":"2026-08-17","sha256":"' + digest + '","byte_size":13}')
            self.assertTrue(archive_verified(manifest, p, "2026-08-17"))

    def test_database_url_required(self):
        old = os.environ.pop("DATABASE_URL", None)
        try:
            from storage_engine import connect
            with self.assertRaises(RuntimeError):
                connect()
        finally:
            if old is not None:
                os.environ["DATABASE_URL"] = old

if __name__ == "__main__":
    unittest.main()
