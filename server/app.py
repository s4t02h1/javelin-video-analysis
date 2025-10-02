import os
import uuid
import json
import tempfile
import shutil
from datetime import datetime
from typing import Dict

import boto3
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse

APP_REGION = os.getenv("AWS_REGION", "ap-northeast-1")
BUCKET = os.getenv("JVA_BUCKET", "your-bucket-name")

app = FastAPI(title="JVA Minimal SaaS")
s3 = boto3.client("s3", region_name=APP_REGION)


def _status_key(job_id: str) -> str:
    return f"results/{job_id}/status.json"


def _result_prefix(job_id: str) -> str:
    return f"results/{job_id}/"


def _presign_put(key: str, content_type: str = "application/octet-stream", expiry: int = 3600) -> Dict:
    return s3.generate_presigned_post(
        BUCKET,
        key,
        Fields={"Content-Type": content_type},
        Conditions=[["content-length-range", 0, 1024 * 1024 * 1024]],
        ExpiresIn=expiry,
    )


@app.post("/v1/jobs")
def create_job() -> JSONResponse:
    job_id = str(uuid.uuid4())
    key = f"uploads/{job_id}/input.mp4"
    url = _presign_put(key, "video/mp4")
    return JSONResponse({"id": job_id, "upload": url, "upload_key": key})


def _run_job(job_id: str, input_key: str):
    # Download input
    tmpdir = tempfile.mkdtemp(prefix=f"jva-{job_id}-")
    local_in = os.path.join(tmpdir, "input.mp4")
    local_out_dir = os.path.join(tmpdir, "out")
    os.makedirs(local_out_dir, exist_ok=True)

    s3.download_file(BUCKET, input_key, local_in)

    # Run CLI (blocking)
    # Using python -m to ensure venv resolution; fallback to script if needed
    from subprocess import run, CalledProcessError
    try:
        run(["python", "run.py", "--video", local_in, "--output", os.path.join(local_out_dir, "analysis.mp4"), "--all-variants"], check=True)
        status = {"status": "completed", "updated_at": datetime.utcnow().isoformat()}
    except CalledProcessError as e:
        status = {"status": "failed", "error": str(e), "updated_at": datetime.utcnow().isoformat()}

    # Upload results
    for root, _, files in os.walk(local_out_dir):
        for f in files:
            p = os.path.join(root, f)
            rel = os.path.relpath(p, local_out_dir).replace("\\", "/")
            s3.upload_file(p, BUCKET, _result_prefix(job_id) + rel)

    # Upload status
    s3.put_object(Bucket=BUCKET, Key=_status_key(job_id), Body=json.dumps(status).encode("utf-8"), ContentType="application/json")

    shutil.rmtree(tmpdir, ignore_errors=True)


@app.post("/v1/jobs/{job_id}/process")
def process_job(job_id: str, payload: Dict, bg: BackgroundTasks) -> JSONResponse:
    input_key = payload.get("upload_key")
    if not input_key:
        return JSONResponse({"error": "upload_key is required"}, status_code=400)
    bg.add_task(_run_job, job_id, input_key)
    return JSONResponse({"id": job_id, "status": "queued"})


@app.get("/v1/jobs/{job_id}")
def get_status(job_id: str) -> JSONResponse:
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=_status_key(job_id))
        body = obj["Body"].read().decode("utf-8")
        return JSONResponse(json.loads(body))
    except s3.exceptions.NoSuchKey:
        return JSONResponse({"status": "pending"})
