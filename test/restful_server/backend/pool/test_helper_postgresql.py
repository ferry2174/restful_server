import uuid

import pytest

from restful_server.backend.pool.helper_postgresql import PostgreSQLHelper


DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "user": "admin",
    "password": "admin123",
    "database": "mydb",
}

TEST_TABLE = "test_helper_postgresql"


_event_loop = None


def run_async(coro):
    """统一复用单个事件循环，避免 asyncio.run 关闭 loop 带来的冲突。"""
    global _event_loop
    if _event_loop is None:
        import asyncio

        _event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_event_loop)
    return _event_loop.run_until_complete(coro)


@pytest.fixture(scope="module", autouse=True)
def setup_postgresql():
    """初始化连接池并创建测试表，测试结束后清理。"""

    async def _prepare():
        await PostgreSQLHelper.init_pool(**DB_CONFIG)
        async with PostgreSQLHelper.transaction() as conn:
            await conn.execute(f"DROP TABLE IF EXISTS {TEST_TABLE}")
            await conn.execute(
                f"""
                CREATE TABLE {TEST_TABLE} (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    value INTEGER NOT NULL
                )
                """
            )

    try:
        run_async(_prepare())
    except Exception as exc:  # pragma: no cover - 依赖外部数据库
        pytest.skip(f"PostgreSQL unavailable: {exc}")

    yield

    async def _cleanup():
        async with PostgreSQLHelper.transaction() as conn:
            await conn.execute(f"DROP TABLE IF EXISTS {TEST_TABLE}")
        await PostgreSQLHelper.close()

    run_async(_cleanup())


class TestPostgreSQLHelper:
    def test_insert_and_fetchone(self):
        """验证 insert + fetchone 能写读一条记录。"""
        unique_name = f"name_{uuid.uuid4().hex}"

        async def _test():
            await PostgreSQLHelper.insert(TEST_TABLE, {"name": unique_name, "value": 1})
            row = await PostgreSQLHelper.fetchone(
                f"SELECT * FROM {TEST_TABLE} WHERE name=%s",
                (unique_name,),
            )
            assert row is not None
            assert row["name"] == unique_name
            assert row["value"] == 1

        run_async(_test())

    def test_update_and_query(self):
        """验证 update 与 query 的组合查询能力。"""
        unique_name = f"name_{uuid.uuid4().hex}"

        async def _test():
            await PostgreSQLHelper.insert(TEST_TABLE, {"name": unique_name, "value": 5})
            await PostgreSQLHelper.update(
                TEST_TABLE,
                {"value": 10},
                "name=%s",
                (unique_name,),
            )
            rows = await PostgreSQLHelper.query(
                TEST_TABLE,
                ["name", "value"],
                "name=%s",
                (unique_name,),
            )
            assert len(rows) == 1
            assert rows[0]["value"] == 10

        run_async(_test())

    def test_count_and_delete(self):
        """验证 count 与 delete 的返回情况。"""
        prefix = f"name_{uuid.uuid4().hex}"
        names = [f"{prefix}_1", f"{prefix}_2"]

        async def _test():
            for name in names:
                await PostgreSQLHelper.insert(TEST_TABLE, {"name": name, "value": 0})

            total = await PostgreSQLHelper.count(
                TEST_TABLE,
                "name = %s OR name = %s",
                tuple(names),
            )
            assert total == len(names)

            await PostgreSQLHelper.delete(
                TEST_TABLE,
                "name = %s OR name = %s",
                tuple(names),
            )

            remaining = await PostgreSQLHelper.count(
                TEST_TABLE,
                "name = %s OR name = %s",
                tuple(names),
            )
            assert remaining == 0

        run_async(_test())

