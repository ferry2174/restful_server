import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from functools import partial

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from restful_server import get_root_path
from restful_server.backend import example
from restful_server.backend.config import ConfigManager
from restful_server.backend.constants import ENV_KEY_IN_OSENV
from restful_server.backend.metrics.metrics_request import monitor_requests_middleware
from restful_server.backend.models import Response, custom_openapi
from restful_server.backend.pool.helper_doris import DorisHelper
from restful_server.backend.pool.helper_mariadb import MariaDBHelper
from restful_server.backend.pool.helper_redis import RedisHelper
from restful_server.backend.pool.pool_kafka import KafkaPool
from restful_server.backend.utils.response_validation_handler import EnhancedResponseValidationHandler


logger = logging.getLogger(__name__)
metrics_logger = logging.getLogger("metrics")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("==========start app lifespan")
    env = os.getenv(ENV_KEY_IN_OSENV)
    logger.info(f"==========start app at {env}")
    # 因为gunicorn和fastapi在不同进程，所以需要重新初始化配置
    config = ConfigManager.init_config(env=env or "dev")

    # 初始化 MariaDB 连接池
    if config.get("enable_mariadb", False):
        logger.info("Initializing MariaDB pool...")
        await MariaDBHelper.init_pool(
            host=config.get("mariadb.host"),
            port=config.get("mariadb.port"),
            user=config.get("mariadb.user"),
            password=config.get("mariadb.password"),
            database=config.get("mariadb.database"),
            min_size=config.get("mariadb.min_pool_size", 1),
            max_size=config.get("mariadb.max_pool_size", 10)
        )

    # 初始化 Doris 连接池（使用 MySQL 协议）
    if config.get("enable_doris", False):
        logger.info("Initializing Doris pool...")
        await DorisHelper.init_pool(
            hosts=config.get("doris.host"),
            port=config.get("doris.port"),
            user=config.get("doris.user"),
            password=config.get("doris.password"),
            database=config.get("doris.database"),
            min_size=config.get("doris.min_pool_size", 1),
            max_size=config.get("doris.max_pool_size", 10)
        )

    # 初始化 Redis
    if config.get("enable_redis", False):
        logger.info("Initializing Redis pool...")
        await RedisHelper.init_pool(config.get("redis.from_url"))
    # 初始化 Kafka
    if config.get("enable_kafka", False):
        logger.info("Initializing Kafka pool...")
        await KafkaPool.init_pool(config.get("kafka.bootstrap_servers"))

    # 初始化订单处理协程 和 等待任务数指标采集器
#    task_queue = AsyncRedisQueue(name="features_unified_queue", host=config.get("redis.host", "127.0.0.1"),
#                             port=config.get("redis.port", 6379), db=0)
#    app.state.task_queue = task_queue
#    await start_workers(config.get("unified_async_workers", 5), task_queue)
#    asyncio.create_task(monitor_waiting_tasks(task_queue))

    # 应用代理
    if config.get("enable_proxy", False):
        logger.info("Setting proxy...")
        os.environ['http_proxy'] = config.get("proxy.http_proxy", "http://127.0.0.1:7890")
        os.environ['https_proxy'] = config.get("proxy.https_proxy", "https://127.0.0.1:7890")
    else:
        proxy_keys = ['http_proxy', 'https_proxy', 'ftp_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']
        for key in proxy_keys:
            if key in os.environ:
                del os.environ[key]
                print(f"已移除 {key}")

    yield  # 应用运行期间

    # 应用关闭时释放连接池资源
    await DorisHelper.close()
    await MariaDBHelper.close()
    await RedisHelper.close()
    await KafkaPool.close()
#    await task_queue.close()


app = FastAPI(
    lifespan=lifespan,
    openapi_url="/restful_server/openapi.json",
    docs_url="/restful_server/docs",
    redoc_url="/restful_server/redoc"
)
app.include_router(example.router, prefix="/restful_server")

# 挂载静态文件目录
static_path = os.path.join(get_root_path() or "", "frontend", "static")
if os.path.exists(static_path):
    app.mount("/restful_server/static", StaticFiles(directory=static_path), name="static")

templates_path = os.path.join(get_root_path() or "", "frontend", "templates")
if os.path.exists(templates_path):
    templates = Jinja2Templates(directory=templates_path)

app.middleware("http")(monitor_requests_middleware)

"""这个列表里的url会打印 ~/restful_server/logs/metrics.log"""
VALID_PREFIXES = [
    "/restful_server/example",
]
@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000  # 转为毫秒
    path = request.url.path
    if any(path.startswith(p) for p in VALID_PREFIXES):
        # query 参数
        query_params = dict(request.query_params)

        # ⚠️ 可选：body参数（注意只能读一次，会影响后续）
        # try:
        #     body = await request.json()
        # except Exception:
        #     body = None

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        metrics_logger.info(
            f'{current_time} | {request.client.host if request.client else "unknown"} | "{request.method} {path}" '
            f"params={query_params} | {response.status_code} | {duration_ms:.2f}ms"
        )
    return response

#@app.middleware("http")
#async def add_cache_control_header(request: Request, call_next):
#    """
#    add_cache_control_header
#    ------------------------------------
#
#    lock the response header to prevent caching
#    临时调试用
#    """
#    response = await call_next(request)
#    # 设置Cache-Control头，禁止缓存
#    response.headers["Cache-Control"] = "no-store"
#    return response

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """请求参数校验失败处理器"""
    return Response(
        code=422,
        message="参数验证失败",
        data={"errors": exc.errors(), "body": exc.body}
    )

""" 响应校验失败异常处理器 """
validation_handler = EnhancedResponseValidationHandler(log_level="ERROR")
@app.exception_handler(ResponseValidationError)
async def handle_response_validation_error(request: Request, exc: ResponseValidationError):
    return await validation_handler(request, exc)

@app.get("/restful_server", response_class=HTMLResponse, include_in_schema=False)
async def read_root(request: Request):
    """
    跟路径响应
    ------------------
    响应前端页面
    """
    return templates.TemplateResponse("index.html", {"request": request})

"""注入文档配置"""
app.openapi = partial(custom_openapi, app)
