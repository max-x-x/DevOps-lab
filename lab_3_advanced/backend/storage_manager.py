from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlparse

from minio import Minio

from models import Instance
from docker_manager import DockerManager


@dataclass
class BucketInfo:
    name: str
    created_at: str | None
    objects_count: int


@dataclass
class ObjectInfo:
    name: str
    size: int
    last_modified: str | None
    etag: str | None


class StorageManager:
    def __init__(self, docker: DockerManager, host_base_url: str):
        self.docker = docker
        self.host_base_url = host_base_url.rstrip("/")

    def _host_and_secure(self) -> tuple[str, bool]:
        parsed = urlparse(self.host_base_url)
        secure = parsed.scheme == "https"
        host = parsed.netloc or parsed.path
        return host, secure

    def _internal_client(self, inst: Instance) -> Minio:
        if not inst.container_id:
            raise RuntimeError("Instance has no associated container.")
        container_ip = self.docker.get_container_ip(inst.container_id)
        return Minio(
            endpoint=f"{container_ip}:9000",
            access_key=inst.access_key,
            secret_key=inst.secret_key,
            secure=False,
        )

    def _external_client(self, inst: Instance) -> Minio:
        host, secure = self._host_and_secure()
        return Minio(
            endpoint=f"{host}:{inst.api_port}",
            access_key=inst.access_key,
            secret_key=inst.secret_key,
            secure=secure,
            region="us-east-1",
        )

    def list_buckets(self, inst: Instance) -> list[BucketInfo]:
        client = self._internal_client(inst)
        result: list[BucketInfo] = []
        for b in client.list_buckets():
            count = 0
            for _ in client.list_objects(b.name, recursive=True):
                count += 1
            created_at = b.creation_date.isoformat() if b.creation_date else None
            result.append(BucketInfo(name=b.name, created_at=created_at, objects_count=count))
        return result

    def create_bucket(self, inst: Instance, bucket_name: str) -> None:
        client = self._internal_client(inst)
        if client.bucket_exists(bucket_name):
            raise ValueError(f'Bucket "{bucket_name}" already exists.')
        client.make_bucket(bucket_name)

    def list_objects(self, inst: Instance, bucket_name: str, limit: int = 200) -> list[ObjectInfo]:
        client = self._internal_client(inst)
        if not client.bucket_exists(bucket_name):
            raise ValueError(f'Bucket "{bucket_name}" not found.')

        objects: list[ObjectInfo] = []
        for idx, obj in enumerate(client.list_objects(bucket_name, recursive=True)):
            if idx >= limit:
                break
            objects.append(
                ObjectInfo(
                    name=obj.object_name,
                    size=obj.size,
                    last_modified=obj.last_modified.isoformat() if obj.last_modified else None,
                    etag=obj.etag,
                )
            )
        return objects

    def create_presigned_put_url(
        self,
        inst: Instance,
        bucket_name: str,
        object_name: str,
        expires_seconds: int,
    ) -> str:
        internal_client = self._internal_client(inst)
        if not internal_client.bucket_exists(bucket_name):
            raise ValueError(f'Bucket "{bucket_name}" not found.')

        external_client = self._external_client(inst)
        return external_client.presigned_put_object(
            bucket_name,
            object_name,
            expires=timedelta(seconds=expires_seconds),
        )

