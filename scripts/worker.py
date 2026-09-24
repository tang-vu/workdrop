"""Optional separate local render worker; SQLite leases prevent duplicate claims."""
import time
from app.server import store, work, ROOT
from app.store import MANIFEST

print("WORKDROP local worker started; no onchain settlement",flush=True)
while True:
    try:
        for job in store.snapshot()["jobs"]:
            if job["state"]=="Requested" and ((ROOT/"output"/(job["id"]+".mp4")).exists() or (job["attempts"]<MANIFEST["maxAttempts"] and job["lease_until"]<=int(time.time()))):
                work(job["id"])
    except Exception as exc:
        print(f"worker check failed: {type(exc).__name__}",flush=True)
    time.sleep(5)
