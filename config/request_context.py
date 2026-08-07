"""Contexto mínimo de request para eventos generados desde signals/modelos."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

from .client_ip import get_client_ip


@dataclass(frozen=True)
class RequestContext:
    user_id: int | None = None
    ip_address: str | None = None
    user_agent: str = ""
    path: str = ""
    request_id: str = ""


_current: ContextVar[RequestContext | None] = ContextVar("security_request_context", default=None)


def current_request_context() -> RequestContext:
    return _current.get() or RequestContext()


class SecurityRequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ctx = RequestContext(
            user_id=request.user.pk if getattr(request.user, "is_authenticated", False) else None,
            ip_address=get_client_ip(request),
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:300],
            path=(request.path or "")[:500],
            request_id=(request.headers.get("X-Request-ID") or "")[:100],
        )
        token = _current.set(ctx)
        try:
            return self.get_response(request)
        finally:
            _current.reset(token)
