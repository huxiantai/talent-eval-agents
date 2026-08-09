from io import BytesIO

import boto3
from botocore.client import Config

from app.config import Settings, get_settings


class ObjectStore:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.client = boto3.client(
            "s3",
            endpoint_url=self.settings.s3_endpoint_url,
            aws_access_key_id=self.settings.s3_access_key,
            aws_secret_access_key=self.settings.s3_secret_key,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        self.public_client = boto3.client(
            "s3",
            endpoint_url=self.settings.s3_public_endpoint_url,
            aws_access_key_id=self.settings.s3_access_key,
            aws_secret_access_key=self.settings.s3_secret_key,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        self.ensure_bucket()

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.settings.s3_bucket)
        except Exception:
            self.client.create_bucket(Bucket=self.settings.s3_bucket)

    def put_bytes(self, key: str, content: bytes, content_type: str) -> None:
        self.client.upload_fileobj(BytesIO(content), self.settings.s3_bucket, key, ExtraArgs={"ContentType": content_type})

    def get_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.settings.s3_bucket, Key=key)["Body"].read()

    def presigned_get(self, key: str, expires: int = 900) -> str:
        return self.public_client.generate_presigned_url("get_object", Params={"Bucket": self.settings.s3_bucket, "Key": key}, ExpiresIn=expires)
