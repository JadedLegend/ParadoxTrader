"""Check connection for the saved data, news and paper keys: read-only, no key echoed.

Scripted HTTP; the network is blocked."""
import json
import socket
import unittest
from unittest.mock import patch

from core.runtime.service_check import check_services

PK, SECRET = "PK" + "B" * 18, "S" * 40
SAVED = {"alpaca_tempest_key_id": PK, "alpaca_tempest_secret": SECRET, "alpaca_siren_key_id": PK,
         "alphavantage": "AVKEY12345", "fmp": "F" * 20, "massive": "massivekey1", "unusual_whales": "uwkey12345",
         "eodhd": "eodkey12345", "brave_search": "bravekey123", "reddit_client_id": "redditid1",
         "reddit_client_secret": "redditsecret1", "x_bearer_token": "xbearer123456",
         "signalstack_webhook": "https://app.signalstack.com/hook/abc123", "public_com": "publickey1",
         "etoro_api_key": "etorokey12", "bigdata": "bigdatakey1"}


class Response:
    def __init__(self, status, data):
        self.status_code, self._data = status, data

    def json(self):
        return self._data


class Scripted:
    def __init__(self, broken=()):
        self.broken, self.calls = set(broken), []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        if any(host in url for host in self.broken):
            return Response(401, {"message": "invalid key " + SAVED["fmp"]})
        if "alpaca" in url:
            assert url.endswith("/v2/account")
            return Response(200, {"status": "ACTIVE", "cash": "100000"})
        if "alphavantage" in url:
            return Response(200, {"Global Quote": {"05. price": "505"}})
        return Response(200, {"data": [1]})

    def post(self, url, **kwargs):
        self.calls.append(("POST", url))
        assert url == "https://www.reddit.com/api/v1/access_token"
        assert kwargs["data"] == {"grant_type": "client_credentials"}
        return Response(200, {"access_token": "t"})


class ServiceCheckTests(unittest.TestCase):
    def setUp(self):
        for target, name in ((socket.socket, "connect"), (socket, "create_connection")):
            blocked = patch.object(target, name, side_effect=AssertionError("network forbidden"))
            blocked.start()
            self.addCleanup(blocked.stop)

    def run_check(self, http):
        return {row["service"]: row for row in check_services(SAVED.get, http_get=http.get, http_post=http.post)}

    def test_each_saved_key_gets_one_read_only_check(self):
        http = Scripted()
        rows = self.run_check(http)
        for name in ("Alpaca paper: Tempest", "Alpha Vantage", "FMP", "Massive", "Unusual Whales", "EODHD",
                     "Brave Search", "Reddit", "X"):
            self.assertEqual(rows[name]["status"], "ok", name)
        self.assertEqual(rows["Alpaca paper: Siren"]["status"], "unset")  # Half a pair is never sent.
        self.assertIn("half", rows["Alpaca paper: Siren"]["message"])
        self.assertEqual(rows["Alpaca paper: Oracle"]["status"], "unset")
        self.assertEqual([c for c in http.calls if c[0] == "POST"],
                         [("POST", "https://www.reddit.com/api/v1/access_token")])
        for _method, url in http.calls:  # No order, broker or webhook address is ever touched.
            for word in ("order", "signalstack", "etoro", "public.com", "bigdata"):
                self.assertNotIn(word, url)
        for name in ("SignalStack", "Public.com", "eToro", "Bigdata.com"):
            self.assertEqual(rows[name]["status"], "skipped", name)

    def test_a_rejected_key_says_so_without_echoing_any_key(self):
        rows = self.run_check(Scripted(broken={"financialmodelingprep", "api.x.com"}))
        self.assertEqual(rows["FMP"]["status"], "fail")
        self.assertIn("rejected", rows["FMP"]["message"])
        self.assertEqual(rows["X"]["status"], "fail")
        text = json.dumps(rows)
        for value in SAVED.values():
            self.assertNotIn(value, text)

    def test_alpha_vantage_limit_notes_fail_and_network_trouble_is_reported(self):
        class Limited(Scripted):
            def get(self, url, **kwargs):
                if "alphavantage" in url:
                    return Response(200, {"Information": "You have reached the 25 requests per day limit."})
                raise ConnectionError("down")
        rows = self.run_check(Limited())
        self.assertEqual(rows["Alpha Vantage"]["status"], "fail")
        self.assertIn("25 requests", rows["Alpha Vantage"]["message"])
        self.assertIn("could not reach", rows["EODHD"]["message"])


if __name__ == "__main__":
    unittest.main()
