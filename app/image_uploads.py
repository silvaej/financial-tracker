from io import BytesIO

from fastapi import HTTPException, UploadFile
from PIL import Image

# Keyed by Pillow's `Image.format` (derived from the actual file bytes), not
# by the client-supplied Content-Type header, which is trivially spoofable.
ALLOWED_IMAGE_FORMATS = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}


async def read_image_upload(
    file: UploadFile | None, *, max_bytes: int, label: str = "Image"
) -> tuple[bytes, str] | None:
    """Validate an uploaded image's actual bytes and return (data, mimetype).

    Returns None if no file was submitted. Raises HTTPException(400) for
    anything oversized or that doesn't decode as one of ALLOWED_IMAGE_FORMATS.
    """
    if file is None or not file.filename:
        return None
    data = await file.read()
    if not data:
        return None
    if len(data) > max_bytes:
        raise HTTPException(status_code=400, detail=f"{label} must be under {max_bytes // 1024}KB.")
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = image.format
            image.verify()
    except Exception as exc:
        # Pillow raises different exception types (UnidentifiedImageError,
        # OSError, SyntaxError, ...) depending on which format parser hits
        # the malformed/non-image data, so any failure here means "reject".
        raise HTTPException(
            status_code=400, detail=f"{label} must be a valid PNG, JPEG, WEBP, or GIF image."
        ) from exc
    mimetype = ALLOWED_IMAGE_FORMATS.get(image_format or "")
    if mimetype is None:
        raise HTTPException(
            status_code=400, detail=f"{label} must be a PNG, JPEG, WEBP, or GIF image."
        )
    return data, mimetype


async def read_receipt_upload(
    file: UploadFile | None, *, max_bytes: int, label: str = "Receipt"
) -> tuple[bytes, str] | None:
    """Like read_image_upload, but also accepts a PDF -- real receipts are
    just as often emailed/downloaded as a PDF as they are a photo. PDF
    validity is checked via its standard "%PDF-" magic-byte header (not a
    full parse -- good enough to reject non-PDF junk with a spoofed
    extension; nothing downstream ever executes this file, it's only ever
    served back with Content-Type + X-Content-Type-Options: nosniff, same
    as every other upload in this app).
    """
    if file is None or not file.filename:
        return None
    data = await file.read()
    if not data:
        return None
    if len(data) > max_bytes:
        raise HTTPException(status_code=400, detail=f"{label} must be under {max_bytes // 1024}KB.")
    if data.startswith(b"%PDF-"):
        return data, "application/pdf"
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = image.format
            image.verify()
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"{label} must be a PNG, JPEG, WEBP, GIF image, or a PDF."
        ) from exc
    mimetype = ALLOWED_IMAGE_FORMATS.get(image_format or "")
    if mimetype is None:
        raise HTTPException(
            status_code=400, detail=f"{label} must be a PNG, JPEG, WEBP, GIF image, or a PDF."
        )
    return data, mimetype
