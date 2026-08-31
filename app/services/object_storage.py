from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.settings import Settings, get_settings


class ObjectStorage(Protocol):
    def put(self, key: str, content: bytes, content_type: str | None = None) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class LocalObjectStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def resolve(self, key: str) -> Path:
        destination = (self.root / key).resolve()
        if self.root not in destination.parents:
            raise ValueError("Caminho de arquivo inválido.")
        return destination

    def put(self, key: str, content: bytes, content_type: str | None = None) -> None:
        destination = self.resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

    def get(self, key: str) -> bytes:
        return self.resolve(key).read_bytes()

    def delete(self, key: str) -> None:
        self.resolve(key).unlink(missing_ok=True)


class S3ObjectStorage:
    def __init__(
        self,
        *,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        region: str,
    ) -> None:
        import boto3

        self.bucket = bucket
        self.client = boto3.client(
            service_name="s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
        )

    def put(self, key: str, content: bytes, content_type: str | None = None) -> None:
        arguments = {"Bucket": self.bucket, "Key": key, "Body": content}
        if content_type:
            arguments["ContentType"] = content_type
        self.client.put_object(**arguments)

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


class R2ObjectStorage(S3ObjectStorage):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            endpoint_url=settings.r2_endpoint_url or "",
            access_key_id=settings.r2_access_key_id or "",
            secret_access_key=settings.r2_secret_access_key or "",
            bucket=settings.r2_bucket_name or "",
            region="auto",
        )


class LocalS3ObjectStorage(S3ObjectStorage):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            endpoint_url=settings.s3_endpoint_url,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            bucket=settings.s3_bucket_name,
            region=settings.s3_region,
        )


@lru_cache
def get_object_storage() -> ObjectStorage:
    settings = get_settings()
    if settings.object_storage_backend == "r2":
        return R2ObjectStorage(settings)
    if settings.object_storage_backend == "s3":
        return LocalS3ObjectStorage(settings)
    return LocalObjectStorage(settings.knowledge_storage_path)
