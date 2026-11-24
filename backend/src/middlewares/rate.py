import threading
import time

from fastapi.responses import JSONResponse

_WINDOW_SECONDS = 60
_LIMIT = 90
_lock = threading.Lock()
_hits: dict[str, list[float]] = {}


def install(app):
    @app.middleware('http')
    async def burst_limit(request, call_next):
        if request.method == 'POST' and request.url.path == '/auth/login':
            now = time.monotonic()
            key = request.client.host if request.client else 'unknown'
            with _lock:
                bucket = [stamp for stamp in _hits.get(key, []) if now - stamp < _WINDOW_SECONDS]
                bucket.append(now)
                _hits[key] = bucket
                blocked = len(bucket) > _LIMIT
            if blocked:
                return JSONResponse({'detail': '登录过于频繁，请稍后重试'}, 429)
        return await call_next(request)
