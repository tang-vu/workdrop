"""Optional server-side Solami RPC observer.

Records finalized transactions touching configured addresses. Signatures alone do
not decode Meteora trades or prove WORKDROP fulfillment.
"""
import json
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx


PAGE_SIZE = 100
MAX_PAGES_PER_POLL = 4


class SolamiObserver:
    def __init__(self, root: Path):
        self.url = os.getenv("SOLAMI_RPC_URL", "")
        self.addresses = list(dict.fromkeys(
            a.strip() for a in os.getenv("WORKDROP_LIVE_ADDRESSES", "").split(",") if a.strip()
        ))
        self.root = Path(root)
        self.db = self.root / "observations.sqlite3"
        self.last_success = None
        self.last_error = None
        self.running = False
        if self.url:
            parsed = urlsplit(self.url)
            if (parsed.scheme != "https" or
                    not re.fullmatch(r"(?:[a-z0-9-]+\.)?rpc\.solami\.dev", parsed.hostname or "") or
                    parsed.path != "/sol" or parsed.username or parsed.password or
                    parsed.port or parsed.fragment):
                raise RuntimeError("SOLAMI_RPC_URL must be an official HTTPS Solami /sol endpoint")
            self.root.mkdir(parents=True, exist_ok=True)
            self._init()
            if self.addresses:
                with self._connect() as db:
                    rows = db.execute(
                        "SELECT last_success FROM cursors WHERE address IN ({})".format(
                            ",".join("?" for _ in self.addresses)), self.addresses
                    ).fetchall()
                if len(rows) == len(self.addresses) and all(row[0] for row in rows):
                    self.last_success = min(row[0] for row in rows)

    def _init(self):
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS events(
                signature TEXT PRIMARY KEY, slot INTEGER NOT NULL, block_time INTEGER,
                status TEXT NOT NULL, observed_at INTEGER NOT NULL,
                source_address TEXT NOT NULL, tx_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS event_addresses(
                signature TEXT NOT NULL, address TEXT NOT NULL,
                PRIMARY KEY(signature,address)
            );
            CREATE TABLE IF NOT EXISTS cursors(
                address TEXT PRIMARY KEY, newest_signature TEXT,
                newest_slot INTEGER NOT NULL DEFAULT 0, last_success INTEGER
            );
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(cursors)")}
            for name, kind in (("scan_head_signature", "TEXT"),
                               ("scan_head_slot", "INTEGER"), ("scan_before", "TEXT")):
                if name not in columns:
                    db.execute(f"ALTER TABLE cursors ADD COLUMN {name} {kind}")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db, timeout=2)
        try:
            with db:
                yield db
        finally:
            db.close()

    def rpc(self, method, params):
        with httpx.Client(timeout=15) as client:
            response = client.post(self.url, json={
                "jsonrpc": "2.0", "id": "workdrop", "method": method, "params": params
            })
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                raise RuntimeError(f"Solami RPC {method}: invalid response")
            if "error" in body:
                error = body["error"]
                code = error.get("code", "unknown") if isinstance(error, dict) else "unknown"
                raise RuntimeError(f"Solami RPC {method}: error code {code}")
            if "result" not in body:
                raise RuntimeError(f"Solami RPC {method}: missing result")
            return body["result"]

    def _cursor(self, db, address):
        db.execute("INSERT OR IGNORE INTO cursors(address) VALUES(?)", (address,))
        return db.execute("""SELECT newest_signature,newest_slot,last_success,
                            scan_head_signature,scan_head_slot,scan_before
                            FROM cursors WHERE address=?""", (address,)).fetchone()

    def _record(self, db, address, entry):
        signature = entry.get("signature")
        if not isinstance(signature, str) or not signature or not isinstance(entry.get("slot"), int):
            raise RuntimeError("Solami RPC getSignaturesForAddress: malformed entry")
        if not db.execute("SELECT 1 FROM events WHERE signature=?", (signature,)).fetchone():
            tx = self.rpc("getTransaction", [signature, {
                "encoding": "jsonParsed", "maxSupportedTransactionVersion": 0,
                "commitment": "finalized"
            }])
            # A transient null must not advance the cursor and permanently skip the tx.
            if not isinstance(tx, dict) or not isinstance(tx.get("slot"), int):
                raise RuntimeError("Solami RPC getTransaction: finalized transaction unavailable")
            if tx["slot"] != entry["slot"]:
                raise RuntimeError("Solami RPC transaction slot mismatch")
            failed = bool(entry.get("err") is not None or (tx.get("meta") or {}).get("err") is not None)
            db.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?)", (
                signature, entry["slot"], entry.get("blockTime"),
                "finalized_failed" if failed else "finalized", int(time.time()),
                address, json.dumps(tx, separators=(",", ":"))
            ))
        db.execute("INSERT OR IGNORE INTO event_addresses VALUES(?,?)", (signature, address))

    def _poll_address(self, address):
        with self._connect() as db:
            old, old_slot, _last, head, head_slot, before = self._cursor(db, address)
        for _ in range(MAX_PAGES_PER_POLL):
            options = {"limit": PAGE_SIZE, "commitment": "finalized"}
            if before:
                options["before"] = before
            page = self.rpc("getSignaturesForAddress", [address, options])
            if not isinstance(page, list) or any(not isinstance(item, dict) for item in page):
                raise RuntimeError("Solami RPC getSignaturesForAddress: invalid response")
            if page and head is None:
                head, head_slot = page[0].get("signature"), page[0].get("slot")
            old_index = next((i for i, item in enumerate(page)
                              if item.get("signature") == old), None) if old else None
            new_entries = page[:old_index] if old_index is not None else page
            with self._connect() as db:
                for entry in reversed(new_entries):
                    self._record(db, address, entry)
                done = old_index is not None or len(page) < PAGE_SIZE
                if done:
                    now = int(time.time())
                    db.execute("""UPDATE cursors SET newest_signature=?,newest_slot=?,
                                  last_success=?,scan_head_signature=NULL,
                                  scan_head_slot=NULL,scan_before=NULL WHERE address=?""",
                               (head or old, head_slot if head_slot is not None else old_slot,
                                now, address))
                    return True
                before = page[-1].get("signature")
                if not isinstance(before, str) or not before:
                    raise RuntimeError("Solami RPC getSignaturesForAddress: malformed page tail")
                db.execute("""UPDATE cursors SET scan_head_signature=?,scan_head_slot=?,
                              scan_before=? WHERE address=?""", (head, head_slot, before, address))
        return False

    def poll_once(self):
        if not self.url or not self.addresses:
            return
        results = [self._poll_address(address) for address in self.addresses]
        self.last_error = None
        if all(results):
            self.last_success = int(time.time())

    def loop(self):
        self.running = True
        while self.running:
            try:
                self.poll_once()
            except Exception as exc:
                self.last_error = type(exc).__name__
            time.sleep(15)

    def start(self):
        if self.url and self.addresses and not self.running:
            self.running = True
            threading.Thread(target=self.loop, daemon=True, name="solami-observer").start()

    def status(self):
        base = {"last_success": self.last_success, "source": "Solami RPC", "events": []}
        if not self.url:
            return {**base, "state": "not configured"}
        if not self.addresses:
            return {**base, "state": "addresses not configured"}
        with self._connect() as db:
            rows = db.execute("""SELECT signature,slot,block_time,status,source_address
                              FROM events ORDER BY slot DESC,signature DESC LIMIT 10""").fetchall()
            pending = db.execute("""SELECT 1 FROM cursors WHERE address IN ({})
                                  AND scan_head_signature IS NOT NULL LIMIT 1""".format(
                ",".join("?" for _ in self.addresses)), self.addresses).fetchone()
        state = "connecting" if self.last_success is None else "live"
        if pending:
            state = "catching up"
        if self.last_error:
            state = "reconnecting"
        if self.last_success and time.time() - self.last_success > 60:
            state = "stale"
        return {**base, "state": state, "last_error": self.last_error,
                "events": [dict(zip(("signature", "slot", "block_time", "status", "source_address"), row))
                           for row in rows]}
