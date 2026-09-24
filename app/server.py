import hashlib
import io
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from .store import Store, LedgerError, MANIFEST, UNIT
from .render import render, probe
from .solami import SolamiObserver

MODE=os.getenv("WORKDROP_MODE","local")
ROOT=Path(os.getenv("WORKDROP_DATA_DIR","data"))
if MODE!="local":
    raise RuntimeError("Only the local ledger is enabled; refusing to imply live settlement")
store=Store(ROOT)
observer=SolamiObserver(ROOT)
workers=ThreadPoolExecutor(max_workers=2,thread_name_prefix="workdrop-render")
running=set()
running_lock=threading.Lock()
app=FastAPI(title="WORKDROP local product demo")
app.add_middleware(CORSMiddleware,allow_origins=["http://127.0.0.1:5173","http://localhost:5173"],allow_methods=["GET","POST"],allow_headers=["*"])


def owner(header):
    if header not in ("A","B"): raise HTTPException(401,"Select a local demo wallet")
    return header


def safe(fn,*args,**kwargs):
    try: return fn(*args,**kwargs)
    except LedgerError as exc: raise HTTPException(400,str(exc))


def normalize(raw):
    if len(raw)>MANIFEST["acceptedInput"]["maxBytes"]: raise HTTPException(413,"Image exceeds 8 MB")
    try:
        im=Image.open(io.BytesIO(raw)); im.verify()
        im=Image.open(io.BytesIO(raw))
        if im.format not in MANIFEST["acceptedInput"]["imageFormats"]: raise HTTPException(400,"Use PNG, JPEG, or WebP")
        if im.width<640 or im.height<360 or im.width*im.height>16000000: raise HTTPException(400,"Image dimensions must be at least 640×360 and at most 16 megapixels")
        im=ImageOps.exif_transpose(im).convert("RGB")
        out=io.BytesIO(); im.save(out,format="PNG",optimize=True)
        return out.getvalue()
    except (UnidentifiedImageError,OSError,ValueError) as exc: raise HTTPException(400,"Corrupt or unsupported image") from exc


def work(job_id):
    with running_lock:
        if job_id in running: return
        running.add(job_id)
    try:
        job=store.get_job(job_id)
        if not job or job["state"]!="Requested": return
        output=ROOT/"output"/(job_id+".mp4")
        if output.exists():
            check=probe(output)
            if check["frames"]!=450 or abs(check["duration"]-15)>0.05 or check["codec"]!="h264" or check["pixel_format"]!="yuv420p":
                raise RuntimeError("Stored artifact failed recovery validation")
            digest=hashlib.sha256(output.read_bytes()).hexdigest()
            store.complete(job_id,digest,output.stat().st_size)
            return
        job=store.attempt(job_id)
        if not job: return
        input_path=ROOT/"input"/(job_id+".png")
        meta=render(input_path,job["product_name"],job["value_prop"],job["cta"],output,ROOT/"scratch"/job_id)
        (ROOT/"output"/(job_id+".json")).write_text(json.dumps(meta,indent=2))
        store.set_stage(job_id,"settling")
        store.complete(job_id,meta["sha256"],meta["bytes"])
    except Exception as exc:
        store.set_stage(job_id,"retry available",str(exc)[:300])
    finally:
        with running_lock: running.discard(job_id)


@app.on_event("startup")
def recover():
    observer.start()
    for job in store.snapshot()["jobs"]:
        if job["state"]=="Requested" and (job["attempts"]<MANIFEST["maxAttempts"] or (ROOT/"output"/(job["id"]+".mp4")).exists()):
            workers.submit(work,job["id"])


@app.get("/api/state")
def state(x_demo_wallet: str | None=Header(default=None)):
    return store.snapshot(owner(x_demo_wallet))


@app.get("/api/live")
def live():
    return observer.status()


@app.post("/api/trade")
def trade(payload:dict,x_demo_wallet: str | None=Header(default=None)):
    return safe(store.trade,owner(x_demo_wallet),payload.get("side"),payload.get("quantity"),payload.get("nonce"))


@app.post("/api/jobs")
async def create_job(image:UploadFile=File(...),product_name:str=Form(...),value_prop:str=Form(...),cta:str=Form(...),nonce:str=Form(...),x_demo_wallet:str|None=Header(default=None)):
    who=owner(x_demo_wallet)
    raw=await image.read(MANIFEST["acceptedInput"]["maxBytes"]+1)
    normalized=normalize(raw)
    job_id,created=safe(store.request,who,nonce,normalized,product_name.strip(),value_prop.strip(),cta.strip())
    if created: workers.submit(work,job_id)
    return {"id":job_id,"created":created,"mode":"local simulation"}


@app.get("/api/jobs/{job_id}")
def job(job_id:str,x_demo_wallet:str|None=Header(default=None)):
    who=owner(x_demo_wallet)
    row=store.get_job(job_id)
    if not row: raise HTTPException(404,"Unknown job")
    if row["owner"]!=who: raise HTTPException(403,"Private job")
    return row


@app.post("/api/jobs/{job_id}/retry")
def retry(job_id:str,x_demo_wallet:str|None=Header(default=None)):
    who=owner(x_demo_wallet); row=store.get_job(job_id)
    if not row or row["owner"]!=who: raise HTTPException(404,"Unknown job")
    if row["state"]!="Requested" or row["attempts"]>=MANIFEST["maxAttempts"]: raise HTTPException(400,"Retry unavailable")
    workers.submit(work,job_id)
    return {"queued":True}


@app.post("/api/jobs/{job_id}/recover")
def recover_credit(job_id:str,x_demo_wallet:str|None=Header(default=None)):
    who=owner(x_demo_wallet); row=store.get_job(job_id)
    if not row or row["owner"]!=who: raise HTTPException(404,"Unknown job")
    safe(store.timeout,job_id)
    return {"state":"TimedOut","credit_returned":True}


@app.get("/api/jobs/{job_id}/video")
def video(job_id:str,x_demo_wallet:str|None=Header(default=None)):
    who=owner(x_demo_wallet); row=store.get_job(job_id)
    if not row or row["owner"]!=who: raise HTTPException(404,"Unknown job")
    if row["state"]!="Completed": raise HTTPException(409,"Video is not released")
    return FileResponse(ROOT/"output"/(job_id+".mp4"),media_type="video/mp4",filename=f"workdrop-{job_id[:8]}.mp4")


@app.get("/api/receipt/{job_id}")
def receipt(job_id:str):
    row=store.get_job(job_id)
    if not row: raise HTTPException(404,"Unknown receipt")
    return {"id":row["id"],"state":row["state"],"input_commitment":row["input_hash"],"artifact_sha256":row["artifact_hash"],"completed_at":row["completed_at"],"deadline_at":row["deadline_at"],"network":"local simulation","note":"This is a local receipt, not an onchain attestation."}


@app.get("/api/sample")
def sample():
    path=Path("assets/sample/workdrop-sample.mp4")
    if not path.exists(): raise HTTPException(404,"Sample has not been rendered")
    return FileResponse(path,media_type="video/mp4")
