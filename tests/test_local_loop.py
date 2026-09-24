import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from app.store import Store, LedgerError, UNIT
from app.render import render, probe

SAMPLE=Path("assets/sample/aura-product-screenshot.png")


class LocalLoop(unittest.TestCase):
    def setUp(self):
        Path(".test-data").mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=".test-data")
        self.store=Store(self.temp.name)

    def tearDown(self): self.temp.cleanup()

    def finished(self, owner, number):
        source=SAMPLE.read_bytes()
        job_id,created=self.store.request(owner,f"nonce-{owner}-{number}",source,f"Aura {number}","A calmer daily ritual for work and life.","Explore Aura")
        self.assertTrue(created)
        job=self.store.attempt(job_id)
        output=Path(self.temp.name)/"output"/(job_id+".mp4")
        meta=render(SAMPLE,job["product_name"],job["value_prop"],job["cta"],output,Path(self.temp.name)/"scratch"/job_id)
        self.assertEqual(meta["frames"],450)
        self.assertEqual(meta["duration"],15.0)
        self.assertTrue(self.store.complete(job_id,meta["sha256"],meta["bytes"]))
        self.assertFalse(self.store.complete(job_id,meta["sha256"],meta["bytes"]))
        return job_id

    def test_full_two_wallet_story_with_four_real_videos(self):
        s=self.store
        s.trade("A","buy",10,"a-buy-0001")
        self.assertEqual(s.snapshot()["balances"]["A"]["units"],10*UNIT)
        ids=[self.finished("A",n) for n in range(3)]
        s.trade("A","sell",7,"a-sell-0001")
        s.trade("B","buy",7,"b-buy-0001")
        ids.append(self.finished("B",3))
        state=s.snapshot()
        self.assertEqual(state["balances"]["A"]["units"],0)
        self.assertEqual(state["balances"]["B"]["units"],6*UNIT)
        self.assertEqual(state["batch"]["consumed_units"],4*UNIT)
        self.assertEqual(state["batch"]["pool_units"],2*UNIT)
        self.assertEqual(state["reconciliation"]["difference_units"],0)
        self.assertEqual(len(set(ids)),4)
        for job_id in ids:
            self.assertEqual(probe(Path(self.temp.name)/"output"/(job_id+".mp4"))["frames"],450)

    def test_duplicate_trade_and_request(self):
        s=self.store
        first=s.trade("A","buy",1,"repeat-0001")
        self.assertEqual(first,s.trade("A","buy",1,"repeat-0001"))
        source=SAMPLE.read_bytes()
        a=s.request("A","repeat-job-0001",source,"Aura","Calm work.","Explore")
        b=s.request("A","repeat-job-0001",source,"Aura","Calm work.","Explore")
        self.assertEqual(a[0],b[0]); self.assertFalse(b[1])
        with self.assertRaises(LedgerError):
            s.request("A","repeat-job-0001",source,"Aura","Different copy.","Explore")
        self.assertEqual(s.snapshot()["reconciliation"]["reserved_units"],UNIT)

    def test_timeout_and_complete_are_exclusive(self):
        s=self.store;s.trade("A","buy",1,"buy-00000001")
        job_id,_=s.request("A","timeout-0001",SAMPLE.read_bytes(),"Aura","Calm work.","Explore",now=100)
        with self.assertRaises(LedgerError):s.complete(job_id,"missing",123,now=101)
        with self.assertRaises(LedgerError):s.timeout(job_id,now=101)
        self.assertTrue(s.timeout(job_id,now=100+48*3600))
        with self.assertRaises(LedgerError):s.complete(job_id,"abc",0,now=100+48*3600)
        self.assertEqual(s.snapshot()["balances"]["A"]["units"],UNIT)

    def test_concurrent_sale_and_request_cannot_double_spend(self):
        s=self.store;s.trade("A","buy",1,"buy-00000001")
        outcomes=[]
        def sale():
            try:s.trade("A","sell",1,"sell-00000001");outcomes.append("sell")
            except LedgerError:pass
        def use():
            try:s.request("A","job-00000001",SAMPLE.read_bytes(),"Aura","Calm work.","Explore");outcomes.append("use")
            except LedgerError:pass
        threads=[threading.Thread(target=sale),threading.Thread(target=use)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(len(outcomes),1)
        self.assertEqual(s.snapshot()["reconciliation"]["difference_units"],0)

    def test_snapshot_remains_consistent_during_trades(self):
        s=self.store;s.trade("A","buy",1,"initial-0001")
        stop=threading.Event(); errors=[]
        def reader():
            while not stop.is_set():
                try:s.snapshot()
                except Exception as exc:errors.append(exc);break
        t=threading.Thread(target=reader);t.start()
        try:
            for n in range(3):
                s.trade("A","sell",1,f"sale-{n:04d}")
                s.trade("A","buy",1,f"buy-{n:04d}")
        finally:
            stop.set();t.join()
        self.assertEqual(errors,[])


if __name__=="__main__":unittest.main()
