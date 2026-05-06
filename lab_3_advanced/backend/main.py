import os
import secrets
import string
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from minio.error import S3Error

from database import Base, engine, get_db
from models import Instance
from schemas import (
    InstanceCreate,
    InstanceResponse,
    MessageResponse,
    BucketCreate,
    BucketResponse,
    ObjectResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
    InstanceDetailsResponse,
)
from docker_manager import DockerManager
from storage_manager import StorageManager

# ── Bootstrap ─────────────────────────────────────────────────────────────────

Base.metadata.create_all(bind=engine)

app = FastAPI(title="MinIO SaaS API", version="1.0.0", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

docker = DockerManager()
HOST_BASE_URL = os.getenv("HOST_BASE_URL", "http://localhost")
storage = StorageManager(docker, HOST_BASE_URL)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gen_creds() -> tuple[str, str]:
    alpha = string.ascii_letters + string.digits
    access_key = "".join(secrets.choice(alpha) for _ in range(20))
    secret_key = "".join(secrets.choice(alpha) for _ in range(40))
    return access_key, secret_key


def _to_response(inst: Instance, bucket_count: Optional[int] = None) -> InstanceResponse:
    return InstanceResponse(
        id=inst.id,
        name=inst.name,
        container_id=inst.container_id,
        api_port=inst.api_port,
        console_port=inst.console_port,
        access_key=inst.access_key,
        secret_key=inst.secret_key,
        status=inst.status,
        api_endpoint=f"{HOST_BASE_URL}:{inst.api_port}",
        console_endpoint=f"{HOST_BASE_URL}:{inst.console_port}",
        bucket_count=bucket_count,
        created_at=inst.created_at,
    )


def _sync_status(inst: Instance, db: Session) -> None:
    if inst.container_id:
        live = docker.get_status(inst.container_id)
        if live != inst.status:
            inst.status = live
            inst.updated_at = datetime.utcnow()
            db.commit()


def _get_instance_or_404(instance_id: int, db: Session) -> Instance:
    inst = db.query(Instance).filter(Instance.id == instance_id).first()
    if not inst:
        raise HTTPException(404, "Instance not found.")
    _sync_status(inst, db)
    return inst


def _bucket_count_safe(inst: Instance) -> Optional[int]:
    if inst.status != "running":
        return None
    try:
        return len(storage.list_buckets(inst))
    except Exception:
        return None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/instances", response_model=InstanceResponse, status_code=201)
def create_instance(body: InstanceCreate, db: Session = Depends(get_db)):
    if db.query(Instance).filter(Instance.name == body.name).first():
        raise HTTPException(400, "An instance with this name already exists.")

    access_key, secret_key = _gen_creds()

    # Port allocation – check both DB and Docker
    db_ports: set[int] = set()
    for row in db.query(Instance).all():
        db_ports.update({row.api_port, row.console_port})

    try:
        api_port, console_port = docker.find_free_ports(db_ports, count=2)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))

    inst = Instance(
        name=body.name,
        api_port=api_port,
        console_port=console_port,
        access_key=access_key,
        secret_key=secret_key,
        status="creating",
    )
    db.add(inst)
    db.commit()
    db.refresh(inst)

    try:
        cid = docker.create_container(
            instance_name=body.name,
            access_key=access_key,
            secret_key=secret_key,
            api_port=api_port,
            console_port=console_port,
        )
        inst.container_id = cid
        inst.status = "running"
    except Exception as exc:
        inst.status = "error"
        db.commit()
        raise HTTPException(500, f"Docker error: {exc}")

    inst.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(inst)
    return _to_response(inst)


@app.get("/api/instances", response_model=list[InstanceResponse])
def list_instances(db: Session = Depends(get_db)):
    rows = db.query(Instance).order_by(Instance.created_at.desc()).all()
    for inst in rows:
        _sync_status(inst, db)
    return [_to_response(i, bucket_count=_bucket_count_safe(i)) for i in rows]


@app.get("/api/instances/{instance_id}", response_model=InstanceResponse)
def get_instance(instance_id: int, db: Session = Depends(get_db)):
    inst = _get_instance_or_404(instance_id, db)
    return _to_response(inst, bucket_count=_bucket_count_safe(inst))


@app.post("/api/instances/{instance_id}/start", response_model=MessageResponse)
def start_instance(instance_id: int, db: Session = Depends(get_db)):
    inst = _get_instance_or_404(instance_id, db)
    if not inst.container_id:
        raise HTTPException(400, "Instance has no associated container.")
    if inst.status == "running":
        raise HTTPException(400, "Instance is already running.")

    try:
        docker.start_container(inst.container_id)
        inst.status = "running"
        inst.updated_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        raise HTTPException(500, f"Docker error: {exc}")

    return MessageResponse(message="Instance started successfully.")


@app.post("/api/instances/{instance_id}/stop", response_model=MessageResponse)
def stop_instance(instance_id: int, db: Session = Depends(get_db)):
    inst = _get_instance_or_404(instance_id, db)
    if not inst.container_id:
        raise HTTPException(400, "Instance has no associated container.")
    if inst.status == "stopped":
        raise HTTPException(400, "Instance is already stopped.")

    try:
        docker.stop_container(inst.container_id)
        inst.status = "stopped"
        inst.updated_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        raise HTTPException(500, f"Docker error: {exc}")

    return MessageResponse(message="Instance stopped successfully.")


@app.delete("/api/instances/{instance_id}", response_model=MessageResponse)
def delete_instance(instance_id: int, db: Session = Depends(get_db)):
    inst = _get_instance_or_404(instance_id, db)

    if inst.container_id:
        docker.remove_container(inst.container_id)

    db.delete(inst)
    db.commit()
    return MessageResponse(message="Instance deleted successfully.")


@app.get("/api/instances/{instance_id}/logs")
def get_logs(instance_id: int, tail: int = 100, db: Session = Depends(get_db)):
    inst = _get_instance_or_404(instance_id, db)
    if not inst.container_id:
        raise HTTPException(400, "Instance has no associated container.")
    return {"logs": docker.get_logs(inst.container_id, tail=tail)}


@app.get("/api/instances/{instance_id}/details", response_model=InstanceDetailsResponse)
def get_instance_details(instance_id: int, db: Session = Depends(get_db)):
    inst = _get_instance_or_404(instance_id, db)
    if inst.status != "running":
        raise HTTPException(400, "Instance must be running to inspect buckets.")
    try:
        buckets = storage.list_buckets(inst)
    except S3Error as exc:
        raise HTTPException(502, f"MinIO error: {exc.code} ({exc.message})")
    except Exception as exc:
        raise HTTPException(502, f"Failed to read instance details: {exc}")

    return InstanceDetailsResponse(
        instance=_to_response(inst, bucket_count=len(buckets)),
        buckets=[BucketResponse(name=b.name, created_at=b.created_at, objects_count=b.objects_count) for b in buckets],
        quick_upload_hint="Create a bucket, generate presigned URL, then upload file with PUT.",
    )


@app.post("/api/instances/{instance_id}/buckets", response_model=BucketResponse, status_code=201)
def create_bucket(instance_id: int, body: BucketCreate, db: Session = Depends(get_db)):
    inst = _get_instance_or_404(instance_id, db)
    if inst.status != "running":
        raise HTTPException(400, "Instance must be running to create a bucket.")

    try:
        storage.create_bucket(inst, body.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except S3Error as exc:
        raise HTTPException(502, f"MinIO error: {exc.code} ({exc.message})")
    except Exception as exc:
        raise HTTPException(502, f"Failed to create bucket: {exc}")

    return BucketResponse(name=body.name, objects_count=0)


@app.get("/api/instances/{instance_id}/buckets/{bucket_name}/objects", response_model=list[ObjectResponse])
def list_bucket_objects(instance_id: int, bucket_name: str, limit: int = 200, db: Session = Depends(get_db)):
    inst = _get_instance_or_404(instance_id, db)
    if inst.status != "running":
        raise HTTPException(400, "Instance must be running to list objects.")
    if limit < 1 or limit > 1000:
        raise HTTPException(400, "limit must be between 1 and 1000")

    try:
        objects = storage.list_objects(inst, bucket_name, limit=limit)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except S3Error as exc:
        raise HTTPException(502, f"MinIO error: {exc.code} ({exc.message})")
    except Exception as exc:
        raise HTTPException(502, f"Failed to list objects: {exc}")

    return [
        ObjectResponse(
            name=o.name,
            size=o.size,
            last_modified=o.last_modified,
            etag=o.etag,
        )
        for o in objects
    ]


@app.post(
    "/api/instances/{instance_id}/buckets/{bucket_name}/presigned-upload",
    response_model=PresignedUploadResponse,
)
def create_presigned_upload(
    instance_id: int,
    bucket_name: str,
    body: PresignedUploadRequest,
    db: Session = Depends(get_db),
):
    inst = _get_instance_or_404(instance_id, db)
    if inst.status != "running":
        raise HTTPException(400, "Instance must be running to create upload URL.")

    try:
        upload_url = storage.create_presigned_put_url(
            inst=inst,
            bucket_name=bucket_name,
            object_name=body.object_name,
            expires_seconds=body.expires_seconds,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except S3Error as exc:
        raise HTTPException(502, f"MinIO error: {exc.code} ({exc.message})")
    except Exception as exc:
        raise HTTPException(502, f"Failed to create presigned URL: {exc}")

    curl_example = (
        f'curl -X PUT --upload-file "./your-file.bin" "{upload_url}"'
    )
    return PresignedUploadResponse(
        upload_url=upload_url,
        expires_seconds=body.expires_seconds,
        curl_example=curl_example,
    )
