"""Durable, explicitly local ledger. This is not a Solana or Meteora adapter."""
import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

MANIFEST = json.loads((Path(__file__).parent.parent / "service-manifest.json").read_text())
MANIFEST_HASH = hashlib.sha256(json.dumps(MANIFEST, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
UNIT = int(MANIFEST["creditBaseUnits"])
PRICE_CENTS = 500


class LedgerError(Exception):
    pass


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "input").mkdir(exist_ok=True)
        (self.root / "output").mkdir(exist_ok=True)
        self.db = self.root / "workdrop.sqlite3"
        self.lock = threading.RLock()
        self._init()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            if conn.in_transaction: conn.commit()
        except Exception:
            if conn.in_transaction: conn.rollback()
            raise
        finally:
            conn.close()

    def _init(self):
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=DELETE")
            db.executescript("""
            CREATE TABLE IF NOT EXISTS balances(owner TEXT PRIMARY KEY, units INTEGER NOT NULL CHECK(units>=0), cash_cents INTEGER NOT NULL CHECK(cash_cents>=0));
            CREATE TABLE IF NOT EXISTS batch(id INTEGER PRIMARY KEY CHECK(id=1), pool_units INTEGER NOT NULL CHECK(pool_units>=0), pool_cash_cents INTEGER NOT NULL CHECK(pool_cash_cents>=0), consumed_units INTEGER NOT NULL CHECK(consumed_units>=0), manifest_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, owner TEXT NOT NULL, nonce TEXT NOT NULL, state TEXT NOT NULL, stage TEXT NOT NULL, input_hash TEXT NOT NULL, input_digest TEXT, artifact_hash TEXT, artifact_bytes INTEGER, created_at INTEGER NOT NULL, deadline_at INTEGER NOT NULL, completed_at INTEGER, attempts INTEGER NOT NULL DEFAULT 0, lease_until INTEGER NOT NULL DEFAULT 0, error TEXT, product_name TEXT NOT NULL, value_prop TEXT NOT NULL, cta TEXT NOT NULL, UNIQUE(owner,nonce));
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, owner TEXT, job_id TEXT, units INTEGER NOT NULL DEFAULT 0, cash_cents INTEGER NOT NULL DEFAULT 0, at INTEGER NOT NULL, detail TEXT NOT NULL DEFAULT '{}');
            """)
            if "input_digest" not in [r[1] for r in db.execute("PRAGMA table_info(jobs)")]:
                db.execute("ALTER TABLE jobs ADD COLUMN input_digest TEXT")
            if "lease_until" not in [r[1] for r in db.execute("PRAGMA table_info(jobs)")]:
                db.execute("ALTER TABLE jobs ADD COLUMN lease_until INTEGER NOT NULL DEFAULT 0")
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO batch VALUES(1,?,?,?,?)", (12*UNIT,0,0,MANIFEST_HASH))
            for name in ("A", "B"):
                db.execute("INSERT OR IGNORE INTO balances VALUES(?,?,?)", (name,0,50000))
            actual = db.execute("SELECT manifest_hash FROM batch WHERE id=1").fetchone()[0]
            if actual != MANIFEST_HASH:
                raise LedgerError("Service manifest changed after batch creation")
            db.execute("COMMIT")

    def snapshot(self, owner=None):
        with self.connect() as db:
            db.execute("BEGIN")
            batch = dict(db.execute("SELECT * FROM batch WHERE id=1").fetchone())
            balances = {r["owner"]: dict(r) for r in db.execute("SELECT * FROM balances")}
            jobs = [dict(r) for r in db.execute("SELECT * FROM jobs ORDER BY created_at DESC")]
            events = [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 50")]
        reserved = sum(UNIT for j in jobs if j["state"] == "Requested")
        held = sum(b["units"] for b in balances.values())
        total = held + reserved + batch["pool_units"] + batch["consumed_units"]
        if total != MANIFEST["batchSize"] * UNIT:
            raise LedgerError(f"Supply invariant failed: {total}")
        if owner:
            jobs = [j for j in jobs if j["owner"] == owner]
        return {"batch":batch, "balances":balances, "jobs":jobs, "events":events,
                "reconciliation":{"issued_units":MANIFEST["batchSize"]*UNIT,"held_units":held,"pool_units":batch["pool_units"],"reserved_units":reserved,"completed_burn_units":batch["consumed_units"],"difference_units":0},
                "manifest":MANIFEST,"unit":UNIT,"price_cents":PRICE_CENTS,"mode":"local simulation"}

    def trade(self, owner, side, quantity, nonce):
        if owner not in ("A", "B") or side not in ("buy", "sell") or type(quantity) is not int or not 1 <= quantity <= 12:
            raise LedgerError("Invalid trade")
        if not isinstance(nonce,str) or len(nonce)<8 or len(nonce)>100:
            raise LedgerError("Invalid nonce")
        units = quantity*UNIT
        cash = quantity*PRICE_CENTS
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT detail FROM events WHERE kind='trade' AND owner=? AND json_extract(detail,'$.nonce')=?",(owner,nonce)).fetchone()
            if prior:
                result=json.loads(prior[0]); db.execute("COMMIT"); return result
            bal=db.execute("SELECT * FROM balances WHERE owner=?",(owner,)).fetchone()
            pool=db.execute("SELECT * FROM batch WHERE id=1").fetchone()
            if side=="buy":
                if pool["pool_units"]<units or bal["cash_cents"]<cash: raise LedgerError("Insufficient local pool credits or demo cash")
                db.execute("UPDATE balances SET units=units+?,cash_cents=cash_cents-? WHERE owner=?",(units,cash,owner))
                db.execute("UPDATE batch SET pool_units=pool_units-?,pool_cash_cents=pool_cash_cents+? WHERE id=1",(units,cash))
            else:
                if bal["units"]<units or pool["pool_cash_cents"]<cash: raise LedgerError("Insufficient available credits or local pool cash")
                db.execute("UPDATE balances SET units=units-?,cash_cents=cash_cents+? WHERE owner=?",(units,cash,owner))
                db.execute("UPDATE batch SET pool_units=pool_units+?,pool_cash_cents=pool_cash_cents-? WHERE id=1",(units,cash))
            result={"side":side,"quantity":quantity,"owner":owner,"cash_cents":cash,"nonce":nonce,"venue":"local fixed-price simulation"}
            db.execute("INSERT INTO events(kind,owner,units,cash_cents,at,detail) VALUES('trade',?,?,?,?,?)",(owner,units,cash,int(time.time()),json.dumps(result)))
            db.execute("COMMIT")
        return result

    def request(self, owner, nonce, image_bytes, product_name, value_prop, cta, now=None):
        if owner not in ("A","B") or not isinstance(nonce,str) or len(nonce)<8 or len(nonce)>100: raise LedgerError("Invalid wallet or nonce")
        for value, limit, label in ((product_name,44,"product name"),(value_prop,100,"value proposition"),(cta,32,"CTA")):
            if not isinstance(value,str) or not 1<=len(value.strip())<=limit: raise LedgerError(f"Invalid {label}")
        now = int(time.time()) if now is None else int(now)
        salt=os.urandom(16)
        commitment=hashlib.sha256(salt+image_bytes+product_name.encode()+value_prop.encode()+cta.encode()).hexdigest()
        digest=hashlib.sha256(image_bytes+product_name.encode()+value_prop.encode()+cta.encode()).hexdigest()
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            prior=db.execute("SELECT id,input_digest FROM jobs WHERE owner=? AND nonce=?",(owner,nonce)).fetchone()
            if prior:
                if prior["input_digest"]!=digest: raise LedgerError("Nonce already used for different inputs")
                db.execute("COMMIT"); return prior[0],False
            bal=db.execute("SELECT units FROM balances WHERE owner=?",(owner,)).fetchone()
            if bal[0]<UNIT: raise LedgerError("No available whole credit")
            job_id=uuid.uuid4().hex
            input_path=self.root/"input"/(job_id+".png")
            temp=input_path.with_suffix(".tmp")
            temp.write_bytes(image_bytes)
            os.replace(temp,input_path)
            db.execute("UPDATE balances SET units=units-? WHERE owner=?",(UNIT,owner))
            db.execute("INSERT INTO jobs(id,owner,nonce,state,stage,input_hash,input_digest,created_at,deadline_at,product_name,value_prop,cta) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(job_id,owner,nonce,"Requested","queued",commitment,digest,now,now+48*3600,product_name,value_prop,cta))
            db.execute("INSERT INTO events(kind,owner,job_id,units,at,detail) VALUES('request',?,?,?,?,'{}')",(owner,job_id,UNIT,now))
            db.execute("COMMIT")
        return job_id,True

    def set_stage(self, job_id, stage, error=None):
        with self.connect() as db:
            db.execute("UPDATE jobs SET stage=?,error=?,lease_until=CASE WHEN ?='retry available' THEN 0 ELSE lease_until END WHERE id=? AND state='Requested'",(stage,error,stage,job_id))

    def attempt(self, job_id):
        with self.lock,self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job=db.execute("SELECT * FROM jobs WHERE id=?",(job_id,)).fetchone()
            if not job or job["state"]!="Requested": db.execute("COMMIT"); return None
            if job["attempts"]>=MANIFEST["maxAttempts"]: db.execute("COMMIT"); return None
            now=int(time.time())
            if job["lease_until"]>now: db.execute("COMMIT"); return None
            db.execute("UPDATE jobs SET attempts=attempts+1,stage='rendering',lease_until=? WHERE id=?",(now+660,job_id))
            db.execute("COMMIT")
            return dict(job)

    def complete(self, job_id, artifact_hash, artifact_bytes, now=None):
        now=int(time.time()) if now is None else int(now)
        with self.lock,self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job=db.execute("SELECT * FROM jobs WHERE id=?",(job_id,)).fetchone()
            if not job: raise LedgerError("Unknown job")
            if job["state"]=="Completed": db.execute("COMMIT"); return False
            if job["state"]!="Requested" or now>=job["deadline_at"]: raise LedgerError("Job expired or already timed out")
            output=self.root/"output"/(job_id+".mp4")
            if not output.exists() or hashlib.sha256(output.read_bytes()).hexdigest()!=artifact_hash: raise LedgerError("Durable artifact missing or invalid")
            db.execute("UPDATE jobs SET state='Completed',stage='complete',artifact_hash=?,artifact_bytes=?,completed_at=?,error=NULL WHERE id=?",(artifact_hash,artifact_bytes,now,job_id))
            db.execute("UPDATE batch SET consumed_units=consumed_units+? WHERE id=1",(UNIT,))
            db.execute("INSERT INTO events(kind,owner,job_id,units,at,detail) VALUES('complete',?,?,?,?,'{}')",(job["owner"],job_id,UNIT,now))
            db.execute("COMMIT")
        return True

    def timeout(self, job_id, now=None):
        now=int(time.time()) if now is None else int(now)
        with self.lock,self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job=db.execute("SELECT * FROM jobs WHERE id=?",(job_id,)).fetchone()
            if not job: raise LedgerError("Unknown job")
            if job["state"]=="TimedOut": db.execute("COMMIT"); return False
            if job["state"]!="Requested" or now<job["deadline_at"]: raise LedgerError("Not eligible for timeout")
            db.execute("UPDATE jobs SET state='TimedOut',stage='credit returned' WHERE id=?",(job_id,))
            db.execute("UPDATE balances SET units=units+? WHERE owner=?",(UNIT,job["owner"]))
            db.execute("INSERT INTO events(kind,owner,job_id,units,at,detail) VALUES('timeout',?,?,?,?,'{}')",(job["owner"],job_id,UNIT,now))
            db.execute("COMMIT")
        return True

    def get_job(self, job_id):
        with self.connect() as db:
            row=db.execute("SELECT * FROM jobs WHERE id=?",(job_id,)).fetchone()
            return dict(row) if row else None
