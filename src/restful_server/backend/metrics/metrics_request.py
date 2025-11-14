import logging
import time
from typing import Awaitable, Callable

from fastapi import Request

from restful_server.backend.metrics import create_collector


logger = logging.getLogger(__name__)


"""通用请求指标"""
REQUEST_COUNT = create_collector("Counter",
    'fastapi_request_count',
    'Total number of requests to endpoints',
    ['method', 'status_code', 'path']
)
REQUEST_LATENCY = create_collector("Histogram",
    'fastapi_request_latency_seconds',
    'Request latency to endpoints in seconds',
    ['method', 'status_code', 'path'],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 5, 10]
)

# 定义要监控的路径前缀
MONITORED_PREFIXS = ["/restful_server"]

def should_monitor(path: str) -> bool:
    """检查路径是否是需要监控的路径"""
    return any(path.startswith(prefix) for prefix in MONITORED_PREFIXS)

async def monitor_requests_middleware(request: Request, call_next: Callable[[Request], Awaitable]):
    """监控请求的中间件函数"""
    original_path = request.url.path
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time

    if should_monitor(original_path):
        REQUEST_COUNT.labels(
            method=request.method,
            status_code=response.status_code,
            path=original_path,
        ).inc()

        REQUEST_LATENCY.labels(
            method=request.method,
            status_code=response.status_code,
            path=original_path,
        ).observe(process_time)

    return response
