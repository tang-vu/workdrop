import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import solami


class FakeObserver(solami.SolamiObserver):
    def __init__(self, root, history):
        self.history = history
        self.missing = set()
        self.calls = []
        super().__init__(root)

    def rpc(self, method, params):
        self.calls.append((method, params))
        if method == "getSignaturesForAddress":
            address, options = params
            rows = self.history[address]
            before = options.get("before")
            start = next((i + 1 for i, row in enumerate(rows)
                          if row["signature"] == before), 0) if before else 0
            return rows[start:start + options["limit"]]
        signature = params[0]
        if signature in self.missing:
            return None
        row = next(row for rows in self.history.values() for row in rows
                   if row["signature"] == signature)
        return {"slot": row["slot"], "meta": {"err": row.get("err")}}


def entry(n, *, failed=False):
    return {"signature": f"sig-{n}", "slot": n, "blockTime": n * 2,
            "err": {"InstructionError": [0, "Custom"]} if failed else None}


class SolamiObserverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "SOLAMI_RPC_URL": "https://rpc.solami.dev/sol?api_key=test-only",
            "WORKDROP_LIVE_ADDRESSES": "mint,program,mint",
        })
        self.env.start()
        self.page = patch.object(solami, "PAGE_SIZE", 2)
        self.max_pages = patch.object(solami, "MAX_PAGES_PER_POLL", 1)
        self.page.start()
        self.max_pages.start()

    def tearDown(self):
        self.max_pages.stop()
        self.page.stop()
        self.env.stop()
        self.temp.cleanup()

    def observer(self, history):
        return FakeObserver(Path(self.temp.name), history)

    def test_resumable_backfill_dedupes_overlapping_addresses(self):
        history = {"mint": [entry(n) for n in range(5, 0, -1)],
                   "program": [entry(5), entry(3, failed=True)]}
        observer = self.observer(history)
        self.assertEqual(observer.status()["state"], "connecting")
        observer.poll_once()
        self.assertEqual(observer.status()["state"], "catching up")
        self.assertIsNone(observer.last_success)
        # Restart must continue at the persisted page boundary, not jump to head.
        restarted = self.observer(history)
        for _ in range(5):
            restarted.poll_once()
            if restarted.status()["state"] == "live":
                break
        self.assertEqual(restarted.status()["state"], "live")
        with restarted._connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 5)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM event_addresses").fetchone()[0], 7)
            self.assertEqual(db.execute(
                "SELECT status FROM events WHERE signature='sig-3'").fetchone()[0],
                "finalized_failed")
        history["mint"] = [entry(7), entry(6)] + history["mint"]
        restarted.poll_once()
        self.assertEqual(restarted.status()["state"], "catching up")
        restarted.poll_once()
        self.assertEqual(restarted.status()["state"], "live")
        with restarted._connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 7)

    def test_missing_transaction_never_advances_cursor(self):
        history = {"mint": [entry(2)], "program": []}
        observer = self.observer(history)
        observer.missing.add("sig-2")
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            observer.poll_once()
        with observer._connect() as db:
            self.assertIsNone(db.execute(
                "SELECT newest_signature FROM cursors WHERE address='mint'").fetchone()[0])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)
        observer.missing.clear()
        observer.poll_once()
        self.assertEqual(observer.status()["state"], "live")

    def test_rejects_lookalike_host(self):
        with patch.dict(os.environ, {"SOLAMI_RPC_URL":
                                     "https://rpc.solami.dev.evil.example/sol?api_key=x"}):
            with self.assertRaisesRegex(RuntimeError, "official HTTPS"):
                solami.SolamiObserver(Path(self.temp.name))


if __name__ == "__main__":
    unittest.main()
