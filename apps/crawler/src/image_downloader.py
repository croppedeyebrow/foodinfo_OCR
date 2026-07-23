from __future__ import annotations

from pathlib import Path

import httpx

from .checksum import calculate_sha256_bytes
from .models import DownloadedImage, ImageCandidate


class ImageDownloadError(RuntimeError):
    error_code = "IMAGE_DOWNLOAD_FAILED"


def download_images(
    product_id: str,
    candidates: list[ImageCandidate],
    output_dir: Path,
    *,
    user_agent: str,
    timeout_seconds: float,
    max_retries: int = 3,
) -> list[DownloadedImage]:
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[DownloadedImage] = []
    seen_hashes: set[str] = set()
    sequence = 0

    headers = {"User-Agent": user_agent}
    with httpx.Client(headers=headers, follow_redirects=True, timeout=timeout_seconds) as client:
        for candidate in candidates:
            content = _fetch_with_retries(
                client,
                candidate.source_url,
                max_retries=max_retries,
            )
            digest = calculate_sha256_bytes(content)
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            sequence += 1
            local_name = f"{product_id}_{sequence:02d}_{digest[:12]}.jpg"
            local_path = output_dir / local_name
            local_path.write_bytes(content)
            downloaded.append(
                DownloadedImage(
                    sequence=sequence,
                    source_url=candidate.source_url,
                    local_path=str(Path("detail_images") / local_name),
                    local_name=local_name,
                    sha256=digest,
                    alt=candidate.alt,
                    width=candidate.width,
                    height=candidate.height,
                )
            )
    return downloaded


def _fetch_with_retries(
    client: httpx.Client,
    url: str,
    *,
    max_retries: int,
) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if content_type and "image" not in content_type and "octet-stream" not in content_type:
                raise ImageDownloadError(
                    f"Unsupported content type for image: {content_type}"
                )
            return response.content
        except Exception as error:  # noqa: BLE001 - 재시도 후 실패 코드로 변환
            last_error = error
            if attempt >= max_retries:
                break
    raise ImageDownloadError(f"Failed to download image: {url}: {last_error}")
