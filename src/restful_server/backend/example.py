import logging
from typing import Any, Literal, Optional

from fastapi import APIRouter, Path

from restful_server.backend.constants import (
    RESPONSE_CODE_SERVICE_UNAVAILABLE,
    RESPONSE_CODE_SERVICE_UNAVAILABLE_MSG,
)
from restful_server.backend.models import Response
from restful_server.backend.pool.helper_doris import DorisHelper
from restful_server.backend.pool.helper_mariadb import MariaDBHelper
from restful_server.backend.pool.pool_kafka import KafkaPool
from restful_server.backend.pool.pool_redis import RedisPool


logger = logging.getLogger(__name__)

# 创建路由实例
router = APIRouter(
    prefix="/example",  # 所有路由都会自动添加此前缀
    tags=["example"],      # 在Swagger文档中分组显示
    responses={404: {"description": "Not found"}},
    include_in_schema=True,  # 控制是否在Swagger文档中显示
)

#@router.get("/mariadb")
#async def query_mariadb():
#    """
#    Check the availability of the MariaDB service
#    --------------------------------------------------------
#
#    Parameters:
#
#    Returns:
#        Response: A standardized response object containing the query result or an error message.
#    """
#    try:
#        MariaDBHelper.get_pool()
#    except RuntimeError:
#        return Response(status=RESPONSE_CODE_SERVICE_UNAVAILABLE, message=RESPONSE_CODE_SERVICE_UNAVAILABLE_MSG)
#    return Response(data = await MariaDBHelper.fetchone("SELECT NOW();"))

async def _query_mariadb_handler(query_type: Literal["now", "version", "status"]) -> Any:
    """Internal handler that contains the actual MariaDB health check logic."""
    try:
        MariaDBHelper.get_pool()
    except RuntimeError:
        return Response(
            status=RESPONSE_CODE_SERVICE_UNAVAILABLE,
            message=RESPONSE_CODE_SERVICE_UNAVAILABLE_MSG,
        )

    if query_type == "now":
        sql = "SELECT NOW() AS `current_time`;"
    elif query_type == "version":
        sql = "SELECT VERSION() AS db_version;"
    else:  # status
        return Response(data={"message": "MariaDB connection pool is healthy"})

    result = await MariaDBHelper.fetchone(sql)
    return Response(data=result)


@router.get(
    "/mariadb/{query_type}",
    summary="MariaDB health check with explicit type",
    description="""
    Execute a lightweight health-check query against MariaDB.

    **Supported values**:
    - `now`     → Returns current server time (`SELECT NOW()`)
    - `version` → Returns MariaDB server version (`SELECT VERSION()`)
    - `status`  → Only validates that the connection pool is available (no query executed)
    """,
    response_description="Query result or health status",
)
async def query_mariadb(
    query_type: Literal["now", "version", "status"] = Path(
        ...,
        description="Type of health check to perform",
        example="now",
    ),
):
    """
    Health check endpoint requiring an explicit query type in the path.
    """
    return await _query_mariadb_handler(query_type)


@router.get(
    "/mariadb",
    summary="MariaDB health check (default: current time)",
    description="""
    Quick health check that returns the current database time (`SELECT NOW()`).

    This is the default/shortcut version of the endpoint.
    Equivalent to calling `/mariadb/now`.
    """,
    response_description="Current server time from MariaDB",
)
async def query_mariadb_default():
    """
    Simple health check without path parameter.
    Always executes `SELECT NOW()` and is the most commonly used variant.
    """
    return await _query_mariadb_handler("now")

@router.get("/doris")
async def query_doris():
    try:
        DorisHelper.get_pool()
    except RuntimeError:
        return Response(status=RESPONSE_CODE_SERVICE_UNAVAILABLE, message=RESPONSE_CODE_SERVICE_UNAVAILABLE_MSG)
    return Response(data = await DorisHelper.fetchone("SELECT NOW();"))

@router.get("/redis")
async def redis_example():
    try:
        RedisPool.get_client()
    except RuntimeError:
        return Response(status=RESPONSE_CODE_SERVICE_UNAVAILABLE, message=RESPONSE_CODE_SERVICE_UNAVAILABLE_MSG)
    redis = RedisPool.get_client()
    await redis.set("greeting", "hello redis")
    value = await redis.get("greeting")
    return {"redis_value": value}

@router.get("/kafka")
async def kafka_example():
    try:
        KafkaPool.get_producer()
    except RuntimeError:
        return Response(status=RESPONSE_CODE_SERVICE_UNAVAILABLE, message=RESPONSE_CODE_SERVICE_UNAVAILABLE_MSG)
    producer = KafkaPool.get_producer()
    await producer.send_and_wait("test-topic", b"hello kafka")
    return {"kafka_status": "message sent"}
