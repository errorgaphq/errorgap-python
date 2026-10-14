"""ASGI middleware for any ASGI framework.

:class:`ErrorgapMiddleware` is pure ASGI, so it works under Starlette,
FastAPI, Quart, Litestar, Falcon (ASGI), Sanic's ASGI mode and Django's ASGI
handler alike::

    from errorgap.asgi import ErrorgapMiddleware

    app = ErrorgapMiddleware(app)

It reports unhandled exceptions and, with ``apm_enabled``, times each request
as a transaction. For WSGI frameworks (Flask, Bottle, Falcon, Pyramid,
CherryPy) use :class:`errorgap.wsgi.ErrorgapMiddleware`.
"""

from .fastapi import TRANSACTION_KEY, ErrorgapMiddleware, spans

__all__ = ["ErrorgapMiddleware", "TRANSACTION_KEY", "spans"]
