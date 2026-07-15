from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from nas.data_asset_service.app.config_store import ServiceConfigStore


class NasConfigStoreTests(unittest.TestCase):
    def test_public_config_never_exposes_token_bearing_mcp_url(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "service_config.json"
            path.write_text(
                json.dumps(
                    {
                        "tushare_token": "test-token-value",
                        "tushare_mcp_url": "https://example.test/mcp?token=test-token-value",
                    }
                ),
                encoding="utf-8",
            )

            public = ServiceConfigStore(path).public()

        self.assertTrue(public["tushare_token_configured"])
        self.assertNotEqual(public["tushare_token_masked"], "test-token-value")
        self.assertIsNone(public["tushare_mcp_url"])
        self.assertNotIn("test-token-value", json.dumps(public))


if __name__ == "__main__":
    unittest.main()
