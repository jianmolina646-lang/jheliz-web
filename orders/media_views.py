"""Media serving for payment artifacts.

Yape payment proofs uploaded by clients contain personally identifiable
info (transaction id, amount, account holder) and must NOT be served to
the public internet — staff-only.

The merchant Yape QR, on the other hand, is shown to every buyer paying
the order (including guest checkouts), so it is served publicly: the
checkout flow does not require login, and a login-gated QR would render
as a broken image for anonymous buyers.
"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import FileResponse, Http404
from django.views.decorators.cache import cache_control


_IMAGE_EXTENSIONS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".svg": "image/svg+xml",
}


def _guess_content_type(target: Path) -> str:
    """Best content type for ``target``.

    Mobile browsers (and our ``X-Content-Type-Options: nosniff`` header)
    refuse to render bytes served as ``application/octet-stream``. Always
    return a real ``image/*`` type for known extensions and fall back to
    ``image/png`` for anything else under ``payments/``.
    """
    ext = target.suffix.lower()
    if ext in _IMAGE_EXTENSIONS:
        return _IMAGE_EXTENSIONS[ext]
    guessed, _ = mimetypes.guess_type(str(target))
    return guessed or "image/png"


def _safe_join(base: Path, rel: str) -> Path | None:
    """Resolve ``rel`` against ``base`` and reject path traversal."""
    target = (base / rel).resolve()
    try:
        target.relative_to(base.resolve())
    except ValueError:
        return None
    return target


def _serve_under(subdir: str, rel_path: str) -> FileResponse:
    base = Path(settings.MEDIA_ROOT) / subdir
    target = _safe_join(base, rel_path)
    if target is None or not target.is_file():
        raise Http404
    response = FileResponse(
        open(target, "rb"),
        content_type=_guess_content_type(target),
    )
    # Inline display so mobile browsers render the image instead of
    # offering a download.
    response["Content-Disposition"] = f'inline; filename="{target.name}"'
    return response


@login_required
@user_passes_test(lambda u: u.is_staff, login_url=settings.LOGIN_URL)
def serve_payment_proof(request, path: str):
    """Yape payment proofs uploaded by clients. Staff-only."""
    return _serve_under(os.path.join("payments", "proofs"), path)


@cache_control(public=True, max_age=600)
def serve_yape_qr(request, path: str):
    """Merchant Yape QR shown to every buyer (incl. guest checkouts)."""
    return _serve_under(os.path.join("payments", "yape"), path)
