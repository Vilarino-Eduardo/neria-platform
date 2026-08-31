from io import BytesIO
from unittest.mock import MagicMock

from app.services.object_storage import LocalObjectStorage, S3ObjectStorage


def test_local_storage_round_trip(tmp_path) -> None:
    storage = LocalObjectStorage(str(tmp_path))
    storage.put("organization/document.txt", b"conteudo")
    assert storage.get("organization/document.txt") == b"conteudo"
    storage.delete("organization/document.txt")
    assert not storage.resolve("organization/document.txt").exists()


def test_s3_storage_uses_same_round_trip_contract() -> None:
    storage = object.__new__(S3ObjectStorage)
    storage.bucket = "neria-knowledge"
    storage.client = MagicMock()
    storage.client.get_object.return_value = {"Body": BytesIO(b"conteudo")}

    storage.put("organization/document.txt", b"conteudo", "text/plain")
    assert storage.get("organization/document.txt") == b"conteudo"
    storage.delete("organization/document.txt")

    storage.client.put_object.assert_called_once_with(
        Bucket="neria-knowledge",
        Key="organization/document.txt",
        Body=b"conteudo",
        ContentType="text/plain",
    )
    storage.client.delete_object.assert_called_once_with(
        Bucket="neria-knowledge", Key="organization/document.txt"
    )
