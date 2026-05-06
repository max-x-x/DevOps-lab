from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator
import re


class InstanceCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be empty")
        if len(v) > 32:
            raise ValueError("name must be 32 characters or fewer")
        if not re.match(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$|^[a-z0-9]$", v):
            raise ValueError("name must be lowercase alphanumeric and hyphens only")
        return v


class InstanceResponse(BaseModel):
    id: int
    name: str
    container_id: Optional[str]
    api_port: int
    console_port: int
    access_key: str
    secret_key: str
    status: str
    api_endpoint: str
    console_endpoint: str
    bucket_count: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    message: str


class BucketCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("bucket name cannot be empty")
        if len(v) < 3 or len(v) > 63:
            raise ValueError("bucket name length must be between 3 and 63")
        if not re.match(r"^[a-z0-9][a-z0-9.-]*[a-z0-9]$", v):
            raise ValueError("bucket name has invalid format")
        if ".." in v or ".-" in v or "-." in v:
            raise ValueError("bucket name has invalid sequence")
        return v


class BucketResponse(BaseModel):
    name: str
    created_at: Optional[str] = None
    objects_count: int = 0


class ObjectResponse(BaseModel):
    name: str
    size: int
    last_modified: Optional[str] = None
    etag: Optional[str] = None


class PresignedUploadRequest(BaseModel):
    object_name: str
    expires_seconds: int = 3600

    @field_validator("object_name")
    @classmethod
    def validate_object_name(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("object_name cannot be empty")
        if len(value) > 1024:
            raise ValueError("object_name is too long")
        return value

    @field_validator("expires_seconds")
    @classmethod
    def validate_expires(cls, v: int) -> int:
        if v < 60 or v > 7 * 24 * 3600:
            raise ValueError("expires_seconds must be between 60 and 604800")
        return v


class PresignedUploadResponse(BaseModel):
    upload_url: str
    method: str = "PUT"
    expires_seconds: int
    curl_example: str


class InstanceDetailsResponse(BaseModel):
    instance: InstanceResponse
    buckets: list[BucketResponse]
    quick_upload_hint: str
