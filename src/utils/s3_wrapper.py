from typing import Dict, Optional

import aioboto3
from fastapi import HTTPException
from starlette import status

from src.constants.env import (
    R2_ACCESS_KEY_ID,
    R2_ENDPOINT_URL,
    R2_REGION_NAME,
    R2_SECRET_ACCESS_KEY,
)
from src.utils.logger import logger


class S3ClientWrapper:
    def __init__(self):
        self.session = aioboto3.Session(
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name=R2_REGION_NAME,
        )
        self.s3_client = None
        self._client_cm = None

    async def __aenter__(self):
        try:
            self._client_cm = self.session.client(
                "s3",
                region_name=R2_REGION_NAME,
                aws_access_key_id=R2_ACCESS_KEY_ID,
                aws_secret_access_key=R2_SECRET_ACCESS_KEY,
                endpoint_url=R2_ENDPOINT_URL,
            )
            # Context manager'ı açık tutarak client'ı elde et
            self.s3_client = await self._client_cm.__aenter__()
            return self
        except Exception as e:
            logger.error(f"S3 connection could not be established: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="S3 connection could not be established",
            )

    async def __aexit__(self, exc_type, exc_value, traceback):
        if self._client_cm is not None:
            await self._client_cm.__aexit__(exc_type, exc_value, traceback)

    async def upload_fileobj(
        self, fileobj, bucket, key, extra_args: Optional[Dict] = None
    ) -> None:
        try:
            await self.s3_client.upload_fileobj(
                Fileobj=fileobj,
                Bucket=bucket,
                Key=key,
                ExtraArgs=extra_args,
            )
        except Exception as e:
            logger.error(f"Error uploading file to S3: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error uploading file to S3",
            )

    async def put_object(
        self, bucket: str, key: str, body: bytes, content_type: str = "application/octet-stream"
    ) -> None:
        try:
            await self.s3_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
            )
        except Exception as e:
            logger.error(f"Error putting object to S3: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error uploading file to S3",
            )

    async def generate_presigned_url(
        self, client_method, params, expires_in
    ) -> Optional[str]:
        try:
            # aiobotocore/aioboto3'te bu metod senkron döner (str)
            return await self.s3_client.generate_presigned_url(
                ClientMethod=client_method,
                Params=params,
                ExpiresIn=expires_in,
            )
        except Exception as e:
            logger.error(f"Error generating presigned URL: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error generating presigned URL",
            )

    async def delete_object(self, bucket, key) -> bool:
        try:
            await self.s3_client.delete_object(Bucket=bucket, Key=key)
            return True
        except Exception as e:
            logger.error(f"Error deleting object from S3: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error deleting object from S3",
            )

    async def get_object(self, bucket, key) -> Optional[Dict]:
        try:
            return await self.s3_client.get_object(Bucket=bucket, Key=key)
        except Exception as e:
            logger.error(f"Error getting object from S3: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error getting object from S3",
            )

    async def download_file(self, bucket, key, download_path) -> None:
        try:
            await self.s3_client.download_file(
                Bucket=bucket, Key=key, Filename=download_path
            )
        except Exception as e:
            logger.error(f"Error downloading file from S3: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error downloading file from S3",
            )
