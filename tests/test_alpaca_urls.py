"""URL construction tests only: all HTTP is replaced with a local mock."""

import unittest
from unittest.mock import Mock, patch

from core.trading import alpaca


class AlpacaReadUrlTests(unittest.TestCase):
    def test_positions_url_contains_one_api_version(self):
        for base in (
            "https://paper-api.alpaca.markets",
            "https://paper-api.alpaca.markets/",
            "https://paper-api.alpaca.markets/v2",
            "https://paper-api.alpaca.markets/v2/",
        ):
            with self.subTest(base=base):
                response = Mock()
                response.json.return_value = []
                http = Mock()
                http.get.return_value = response
                credentials = {
                    "api_key": "offline-placeholder",
                    "api_secret": "offline-placeholder",
                    "base_url": base,
                }
                with patch.object(alpaca, "get_alpaca_creds", return_value=credentials), patch.object(alpaca, "requests", http):
                    client = alpaca.AlpacaClient("tempest")
                    self.assertEqual(client.get_positions(), [])
                self.assertEqual(
                    http.get.call_args.args[0],
                    "https://paper-api.alpaca.markets/v2/positions",
                )
                http.post.assert_not_called()
                http.delete.assert_not_called()
                response.raise_for_status.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
