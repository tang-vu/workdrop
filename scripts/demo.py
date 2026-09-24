"""Run the full, actual-video two-wallet story against a fresh local data directory."""
import hashlib
import json
import os
from pathlib import Path
from app.store import Store, UNIT
from app.render import render

root=Path(os.getenv("WORKDROP_DATA_DIR","data/demo"))
store=Store(root)
if store.snapshot()["events"]:
    raise SystemExit(f"{root} already contains events. Choose a fresh WORKDROP_DATA_DIR to keep the record honest.")
image=Path("assets/sample/aura-product-screenshot.png").read_bytes()
source=Path("assets/sample/aura-product-screenshot.png")

def finish(owner,n):
    name=f"Aura {n}"
    job_id,_=store.request(owner,f"demo-{owner}-{n:04d}",image,name,"A calmer daily ritual for work and life.","Explore Aura")
    job=store.attempt(job_id)
    out=root/"output"/(job_id+".mp4")
    meta=render(source,name,job["value_prop"],job["cta"],out,root/"scratch"/job_id)
    (root/"output"/(job_id+".json")).write_text(json.dumps(meta,indent=2))
    store.complete(job_id,meta["sha256"],meta["bytes"])
    print(owner,"completed",job_id,"frames",meta["frames"],"sha256",meta["sha256"])

store.trade("A","buy",10,"demo-a-buy-0001")
for n in (1,2,3): finish("A",n)
store.trade("A","sell",7,"demo-a-sell-0001")
store.trade("B","buy",7,"demo-b-buy-0001")
finish("B",4)
state=store.snapshot()
assert state["balances"]["A"]["units"]==0
assert state["balances"]["B"]["units"]==6*UNIT
assert state["batch"]["consumed_units"]==4*UNIT
assert state["reconciliation"]["difference_units"]==0
print(json.dumps({"mode":"local simulation","A_available":0,"B_available":6,"completed":4,"pool":2,"video_paths":[str(root/"output"/(j["id"]+".mp4")) for j in state["jobs"]]},indent=2))
