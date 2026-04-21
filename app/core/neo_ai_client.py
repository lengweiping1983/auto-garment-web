"""Neo AI image generation client."""
import asyncio
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx

from app.config import settings


class NeoAIClient:
    def __init__(self):
        self.base_url = settings.neo_ai_base_url.rstrip("/")
        self.token = settings.resolved_neo_ai_access_token
        self.headers = {
            "accessToken": self.token,
            "Content-Type": "application/json",
        }
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))

    async def upload_to_oss(self, local_path: Path) -> str:
        """Upload a local file to Neo AI OSS and return the public URL."""
        import mimetypes
        import oss2

        # Step 1: Get STS token
        sts_url = "https://story.neodomain.cn/agent/sts/oss/token"
        response = await self.client.get(sts_url, headers={"accessToken": self.token})
        response.raise_for_status()
        sts_result = response.json()
        if not sts_result.get("success"):
            raise RuntimeError(f"Failed to get STS token: {sts_result.get('errMessage', 'Unknown error')}")
        sts = sts_result["data"]

        # Step 2: Upload to OSS
        auth = oss2.StsAuth(
            sts["accessKeyId"],
            sts["accessKeySecret"],
            sts["securityToken"],
        )
        bucket = oss2.Bucket(auth, "oss-cn-shanghai.aliyuncs.com", sts["bucketName"])

        ext = local_path.suffix
        date_str = datetime.now().strftime("%Y%m%d")
        remote_path = f"temp/{date_str}/{uuid.uuid4().hex[:8]}{ext}"
        content_type = mimetypes.guess_type(str(local_path))[0] or "application/octet-stream"

        bucket.put_object_from_file(remote_path, str(local_path), headers={"Content-Type": content_type})
        url = f"https://wlpaas.oss-cn-shanghai.aliyuncs.com/{remote_path}"
        return url

    async def submit_generation(
        self,
        prompt: str,
        negative_prompt: str = "",
        model: str = "",
        size: str = "",
        reference_images: list[str] | None = None,
        num_images: int = 1,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ) -> str:
        """Submit generation task, return task_code."""
        print(f"[DEBUG] NeoAI token prefix: {self.token[:20]}..." if self.token else "[DEBUG] NeoAI token is EMPTY")
        payload = {
            "modelName": model or settings.neo_ai_default_model,
            "prompt": prompt,
            "negativePrompt": negative_prompt,
            "size": size or settings.neo_ai_default_size,
            "numImages": str(num_images),
            "outputFormat": "png",
            "aspectRatio": "1:1",
            "guidanceScale": 7.5,
            "safetyTolerance": "5",
            "showPrompt": True,
        }
        if reference_images:
            payload["imageUrls"] = reference_images

        last_err = ""
        for attempt in range(max_retries):
            response = await self.client.post(
                f"{self.base_url}/generate",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                task_data = data.get("data", {})
                return task_data.get("task_code", "")
            last_err = data.get("errMessage", "Unknown error")
            if "CONCURRENT_UPDATE_CONFLICT" in last_err and attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))
                continue
            break
        raise RuntimeError(f"Neo AI generation failed: {last_err}")

    async def get_task_status(self, task_code: str) -> dict:
        """Poll task status."""
        response = await self.client.get(
            f"{self.base_url}/result/{task_code}",
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    async def download_image(self, url: str, dest: Path) -> Path:
        """Download generated image to local path."""
        response = await self.client.get(url)
        response.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(response.content)
        return dest

    async def poll_until_complete(
        self,
        task_code: str,
        output_dir: Path,
        timeout: int = 300,
        poll_interval: int = 5,
    ) -> Path:
        """Poll until task completes, then download and return local path."""
        start = time.time()
        while time.time() - start < timeout:
            result = await self.get_task_status(task_code)
            if not result.get("success"):
                raise RuntimeError(f"Neo AI status check failed: {result.get('errMessage', 'Unknown error')}")
            status_data = result.get("data", {})
            status = status_data.get("status", "").upper()
            if status == "SUCCESS":
                image_urls = status_data.get("image_urls", [])
                if image_urls:
                    suffix = ".png"
                    url = image_urls[0]
                    if ".jpg" in url or ".jpeg" in url:
                        suffix = ".jpg"
                    dest = output_dir / f"collection_board_{task_code}{suffix}"
                    return await self.download_image(url, dest)
                raise RuntimeError("Task completed but no image URL found")
            elif status == "FAILED":
                raise RuntimeError(f"Generation failed: {status_data.get('failure_reason', 'Unknown error')}")
            await asyncio.sleep(poll_interval)
        raise TimeoutError(f"Generation timeout after {timeout}s")
