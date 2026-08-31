"""Homologa o armazenamento S3 local com gravação, leitura e remoção."""

import json
import uuid
from urllib.parse import urlparse

from app.core.settings import get_settings
from app.services.object_storage import LocalS3ObjectStorage

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def main() -> int:
    settings = get_settings()
    if urlparse(settings.s3_endpoint_url).hostname not in LOCAL_HOSTS:
        print(
            json.dumps(
                {"error": "A homologação gratuita aceita somente um S3 local."},
                ensure_ascii=False,
            )
        )
        return 2

    storage = LocalS3ObjectStorage(settings)
    key = f"simulation/{uuid.uuid4()}.txt"
    content = "Neria: homologação local do armazenamento.".encode()
    try:
        storage.client.head_bucket(Bucket=storage.bucket)
        storage.put(key, content, "text/plain; charset=utf-8")
        recovered = storage.get(key)
        storage.delete(key)
    except Exception as exc:  # noqa: BLE001 - apresenta falhas do serviço local
        print(json.dumps({"error": f"Falha no MinIO local: {exc}"}, ensure_ascii=False))
        return 1

    print(
        json.dumps(
            {
                "external_network_used": False,
                "bucket": storage.bucket,
                "write": "ok",
                "read_integrity": recovered == content,
                "delete": "ok",
                "temporary_key": key,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if recovered == content else 1


if __name__ == "__main__":
    raise SystemExit(main())
