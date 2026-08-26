"""Bounded official-source HTTP client. No arbitrary client-supplied URL fetching."""

import asyncio
import hashlib
import json
import warnings
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urljoin, urlsplit

import httpx
from PIL import Image, UnidentifiedImageError

API_URL = "https://data.moa.gov.tw/Service/OpenData/TransService.aspx?UnitId=QcbUEzN6E6DL"
MAX_IMAGE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class MoaPhoto:
    data: bytes
    content_type: str
    extension: str
    source_checksum: str
    width: int
    height: int


def validate_image_url(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"https", "http"}
        or parsed.hostname not in {"www.pet.gov.tw", "asms.coa.gov.tw"}
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 80, 443}
        or parsed.query
        or parsed.fragment
        or not parsed.path.lower().startswith(("/upload/pic/", "/amlapp/upload/pic/"))
        or any(word in parsed.path.lower() for word in ("..", "default", "noimage", "placeholder"))
    ):
        raise ValueError("untrusted_or_placeholder_image_url")
    return parsed._replace(scheme="https", netloc=parsed.hostname).geturl()


def decode_photo(data: bytes, *, declared_type: str) -> MoaPhoto:
    # MOA declares PNG for JPEG bytes. The declaration is deliberately not trusted.
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("image_size_invalid")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                fmt = image.format
                width, height = image.size
                if min(width, height) < 32 or width * height > 40_000_000:
                    raise ValueError("image_dimensions_invalid")
                image.verify()
            with Image.open(BytesIO(data)) as image:
                image.load()
                if all(low == high for low, high in image.convert("RGB").getextrema()):
                    raise ValueError("blank_placeholder_image")
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("image_decode_failed") from exc
    formats = {
        "JPEG": ("image/jpeg", "jpg"),
        "PNG": ("image/png", "png"),
        "WEBP": ("image/webp", "webp"),
    }
    if fmt not in formats:
        raise ValueError("image_format_unsupported")
    mime, extension = formats[fmt]
    return MoaPhoto(data, mime, extension, hashlib.sha256(data).hexdigest(), width, height)


class MoaOpenDataClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(20, connect=5), follow_redirects=False
        )
        self.owns_client = client is None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()

    async def close(self) -> None:
        if self.owns_client:
            await self.client.aclose()

    async def _get(self, url: str, *, image: bool, max_bytes: int) -> tuple[bytes, str]:
        for attempt in range(3):
            try:
                async with asyncio.timeout(30):
                    current = validate_image_url(url) if image else url
                    for _ in range(3):
                        async with self.client.stream("GET", current) as response:
                            if response.is_redirect:
                                if not image:
                                    raise ValueError("unexpected_dataset_redirect")
                                current = validate_image_url(
                                    urljoin(current, response.headers.get("location", ""))
                                )
                                continue
                            response.raise_for_status()
                            data = bytearray()
                            async for chunk in response.aiter_bytes():
                                data.extend(chunk)
                                if len(data) > max_bytes:
                                    raise ValueError("source_response_too_large")
                            return bytes(data), response.headers.get("content-type", "")
                    raise ValueError("too_many_image_redirects")
            except (httpx.TransportError, httpx.HTTPStatusError, TimeoutError) as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in {
                    429,
                    500,
                    502,
                    503,
                    504,
                }:
                    break
                if attempt < 2:
                    await asyncio.sleep(0.25 * (2**attempt))
        raise ValueError("image_fetch_failed" if image else "dataset_fetch_failed")

    async def fetch_records(self) -> list[dict]:
        data, _ = await self._get(API_URL, image=False, max_bytes=32 * 1024 * 1024)
        try:
            rows = json.loads(data)
        except (ValueError, UnicodeError) as exc:
            raise ValueError("invalid_dataset_json") from exc
        if not isinstance(rows, list) or not rows or len(rows) > 100_000:
            raise ValueError("invalid_or_empty_dataset")
        return rows

    async def fetch_photo(self, url: str) -> MoaPhoto:
        data, declared = await self._get(url, image=True, max_bytes=MAX_IMAGE_BYTES)
        return decode_photo(data, declared_type=declared)
