import asyncio
import functools
import logging


#from restful_server.backend.metrics import create_collector
#from restful_server.backend.utils.queue_redis import AsyncRedisQueue


logger = logging.getLogger(__name__)

"""整合接口指标"""
#UNIFIED_FEATURES_WAITING_TASKS = create_collector("Gauge", "unified_features_waiting_tasks", "Current waiting tasks", [])
#UNIFIED_FEATURES_EXCEPTIONS_TOTAL = create_collector("Counter", "unified_features_exceptions_total", "Total exceptions today", [])
#UNIFIED_FEATURES_TIMEOUTS_TOTAL = create_collector("Counter", "unified_features_timeouts_total", "Total timeouts today", [])
#UNIFIED_FEATURES_COMPLETED_TOTAL = create_collector("Counter", "unified_features_completed_total", "Total completed tasks today", [])
#UNIFIED_FEATURES_EXTERNAL_API_RESPONSE_TIME = create_collector("Summary", "unified_features_external_api_response_time", "External API response time", [])

#async def monitor_waiting_tasks(task_queue: AsyncRedisQueue):
#    while True:
#        size = await task_queue.qsize()
#        logger.debug(f"[Monitor waiting tasks]current qsize is: {size}")
#        UNIFIED_FEATURES_WAITING_TASKS.set(size)
#        await asyncio.sleep(5)


# 一个自定义的、能正确处理异步函数的装饰器
def async_timer(metric):
    """ 一个自定义的、能正确处理异步函数的装饰器 """
    def decorator(f):
        if asyncio.iscoroutinefunction(f):
            @functools.wraps(f)
            async def async_timed(*args, **kwargs):
                with metric.time(): # 这里会使用metric自己的计时逻辑，但因为我们是在async函数内，调用await f()，所以时间是对的。
                    return await f(*args, **kwargs)
            return async_timed
        else:
            # 如果是同步函数，也可以用原来的方法，或者同样包装一下
            @functools.wraps(f)
            def sync_timed(*args, **kwargs):
                with metric.time():
                    return f(*args, **kwargs)
            return sync_timed
    return decorator
