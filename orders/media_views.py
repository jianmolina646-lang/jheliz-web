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

import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import FileResponse, Http404


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
    return FileResponse(open(target, "rb"))


@login_required
@user_passes_test(lambda u: u.is_staff, login_url=settings.LOGIN_URL)
def serve_payment_proof(request, path: str):
    """Yape payment proofs uploaded by clients. Staff-only."""
    return _serve_under(os.path.join("payments", "proofs"), path)


def serve_yape_qr(request, path: str):
    """Merchant Yape QR shown to every buyer (incl. guest checkouts)."""
    return _serve_under(os.path.join("payments", "yape"), path)
