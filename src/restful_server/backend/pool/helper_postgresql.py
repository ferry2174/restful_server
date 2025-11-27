import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import asyncpg


logger = logging.getLogger(__name__)

SqlArgs = Union[Sequence[Any], Dict[str, Any], None]


class PostgreSQLHelper:
    """基于 asyncpg 的 PostgreSQL 工具类，接口对齐 MariaDB 版本，方便替换。"""
    _instance: "PostgreSQLHelper | None" = None
    _pool: asyncpg.Pool | None = None

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        user: str = "postgres",
        password: str = "",
        database: str = "",
        min_size: int = 1,
        max_size: int = 5,
    ):
        """保存连接配置但不立即建池，可用于重复初始化。"""
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.min_size = min_size
        self.max_size = max_size

    @classmethod
    async def init_pool(
        cls,
        host: str = "localhost",
        port: int = 5432,
        user: str = "postgres",
        password: str = "",
        database: str = "",
        min_size: int = 1,
        max_size: int = 5,
    ) -> "PostgreSQLHelper":
        """创建异步连接池，保证全局只初始化一次。

        用法: await PostgreSQLHelper.init_pool(host="db", database="app")
        """
        if cls._instance is None:
            cls._instance = cls(host, port, user, password, database, min_size, max_size)
            cls._pool = await asyncpg.create_pool(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                min_size=min_size,
                max_size=max_size,
            )
            logger.info("PostgreSQL connection pool initialized.")
        return cls._instance

    @classmethod
    def get_pool(cls) -> asyncpg.Pool:
        """直接返回底层 asyncpg pool，未初始化则抛出异常。

        用法: pool = PostgreSQLHelper.get_pool()
        """
        if cls._pool is None:
            raise RuntimeError("Connection pool is not initialized")
        return cls._pool

    @classmethod
    async def close(cls) -> None:
        """关闭连接池并清空单例，释放所有连接。

        用法: await PostgreSQLHelper.close()
        """
        if cls._pool is not None:
            await cls._pool.close()
            cls._pool = None
            cls._instance = None
            logger.info("PostgreSQL connection pool closed.")

    @classmethod
    async def execute(cls, sql: str, args: SqlArgs = None) -> str:
        """执行单条写操作，返回 asyncpg 的状态字符串。

        用法: await PostgreSQLHelper.execute("UPDATE t SET flag=%s WHERE id=%s", (True, 1))
        """
        formatted_sql, params = cls._format_sql(sql, args)
        async with cls.get_pool().acquire() as conn:
            return await conn.execute(formatted_sql, *params)

    @classmethod
    async def executemany(cls, sql: str, args: Iterable[Sequence[Any]]) -> None:
        """批量执行写操作，使用 executemany 减少往返。

        用法: await PostgreSQLHelper.executemany("INSERT INTO t(a,b) VALUES(%s,%s)", [(1,2),(3,4)])
        """
        args_list = [tuple(item) for item in args]
        if not args_list:
            return
        formatted_sql, _ = cls._format_sql(sql, args_list[0])
        async with cls.get_pool().acquire() as conn:
            await conn.executemany(formatted_sql, args_list)

    @classmethod
    async def fetchone(cls, sql: str, args: SqlArgs = None) -> Optional[Dict[str, Any]]:
        """查询单行结果，返回 dict 或 None。

        用法: row = await PostgreSQLHelper.fetchone("SELECT * FROM t WHERE id=%s", (1,))
        """
        formatted_sql, params = cls._format_sql(sql, args)
        async with cls.get_pool().acquire() as conn:
            record = await conn.fetchrow(formatted_sql, *params)
            return dict(record) if record else None

    @classmethod
    async def fetchall(cls, sql: str, args: SqlArgs = None) -> List[Dict[str, Any]]:
        """查询多行结果，转换为 dict 列表。

        用法: rows = await PostgreSQLHelper.fetchall("SELECT * FROM t WHERE flag=%s", (True,))
        """
        formatted_sql, params = cls._format_sql(sql, args)
        async with cls.get_pool().acquire() as conn:
            records = await conn.fetch(formatted_sql, *params)
            return [dict(record) for record in records]

    @classmethod
    async def insert(cls, table: str, data: Dict[str, Any]) -> str:
        """根据字段字典构造 INSERT 语句并执行。

        用法: await PostgreSQLHelper.insert("users", {"name": "alice", "age": 18})
        """
        columns = ", ".join(data.keys())
        placeholders = cls._build_placeholders(len(data))
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        return await cls.execute(sql, tuple(data.values()))

    @classmethod
    async def insert_many(cls, table: str, data: List[Dict[str, Any]]) -> None:
        """批量插入多条记录，保持列顺序一致。

        用法: await PostgreSQLHelper.insert_many("users", [{"name": "a"}, {"name": "b"}])
        """
        if not data:
            return
        columns = ", ".join(data[0].keys())
        placeholders = cls._build_placeholders(len(data[0]))
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        args = [tuple(item.values()) for item in data]
        await cls.executemany(sql, args)

    @classmethod
    async def update(
        cls,
        table: str,
        data: Dict[str, Any],
        condition: str,
        args: SqlArgs = None,
    ) -> str:
        """根据字段字典构造 UPDATE 语句，condition 使用原始 SQL。

        用法: await PostgreSQLHelper.update("users", {"name": "bob"}, "id=%s", (1,))
        """
        set_clause, values = cls._build_set_clause(data)
        sql = f"UPDATE {table} SET {set_clause} WHERE {condition}"
        merged_args = tuple(values) + cls._normalize_args(args)
        return await cls.execute(sql, merged_args)

    @classmethod
    async def delete(
        cls,
        table: str,
        condition: str,
        args: SqlArgs = None,
    ) -> str:
        """执行 DELETE 语句，condition 由调用方提供。

        用法: await PostgreSQLHelper.delete("users", "id=%s", (1,))
        """
        sql = f"DELETE FROM {table} WHERE {condition}"
        return await cls.execute(sql, args)

    @classmethod
    async def get_by_id(
        cls,
        table: str,
        id_value: Any,
        id_column: str = "id",
    ) -> Optional[Dict[str, Any]]:
        """按主键列查询单条记录，默认列名为 id。

        用法: row = await PostgreSQLHelper.get_by_id("users", 1)
        """
        sql = f"SELECT * FROM {table} WHERE {id_column} = %s"
        return await cls.fetchone(sql, (id_value,))

    @classmethod
    async def query(
        cls,
        table: str,
        columns: Union[str, List[str]] = "*",
        condition: Optional[str] = None,
        args: SqlArgs = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """提供常用 SELECT 组合，包括列筛选、条件、排序与分页。

        用法: rows = await PostgreSQLHelper.query("users", ["id","name"], order_by="id DESC")
        """
        if isinstance(columns, list):
            columns = ", ".join(columns)

        sql = f"SELECT {columns} FROM {table}"
        if condition:
            sql += f" WHERE {condition}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        if limit is not None:
            sql += f" LIMIT {limit}"
            if offset is not None:
                sql += f" OFFSET {offset}"

        return await cls.fetchall(sql, args)

    @classmethod
    async def count(
        cls,
        table: str,
        condition: Optional[str] = None,
        args: SqlArgs = None,
    ) -> int:
        """统计满足条件的记录数。

        用法: total = await PostgreSQLHelper.count("users", "flag=%s", (True,))
        """
        sql = f"SELECT COUNT(*) AS count FROM {table}"
        if condition:
            sql += f" WHERE {condition}"
        result = await cls.fetchone(sql, args)
        return int(result["count"]) if result else 0

    @classmethod
    def transaction(cls) -> "TransactionContext":
        """返回一个事务上下文，方便在 async with 中使用。

        用法:
            async with PostgreSQLHelper.transaction() as conn:
                await conn.execute(...)
        """
        return TransactionContext(cls.get_pool())

    @staticmethod
    def _build_placeholders(count: int) -> str:
        """生成与 MariaDB 相同的 %s 占位符，后续再转换为 $n。"""
        return ", ".join(["%s"] * count)

    @classmethod
    def _build_set_clause(cls, data: Dict[str, Any]) -> Tuple[str, List[Any]]:
        """根据字段构造 SET 片段，并返回对应的值数组。"""
        assignments = []
        values: List[Any] = []
        for key, value in data.items():
            assignments.append(f"{key} = %s")
            values.append(value)
        return ", ".join(assignments), values

    @staticmethod
    def _normalize_args(args: SqlArgs) -> Tuple[Any, ...]:
        """把各种参数形式统一成 tuple，便于传递给 asyncpg。"""
        if args is None:
            return ()
        if isinstance(args, dict):
            return tuple(args.values())
        if isinstance(args, (list, tuple)):
            return tuple(args)
        return (args,)

    @classmethod
    def _format_sql(cls, sql: str, args: SqlArgs) -> Tuple[str, Tuple[Any, ...]]:
        """把 %s 或 %(name)s 占位符转换为 asyncpg 需要的 $1/$2..."""
        if args is None:
            return sql, ()
        if isinstance(args, dict):
            return cls._format_named_sql(sql, args)
        return cls._format_positional_sql(sql, args)

    @staticmethod
    def _format_positional_sql(sql: str, args: Union[Sequence[Any], Any]) -> Tuple[str, Tuple[Any, ...]]:
        """处理位置占位符：%s -> $n，并返回参数元组。"""
        params = PostgreSQLHelper._normalize_args(args)
        placeholder_pattern = re.compile(r"%s")
        counter = 0

        def replacer(_: re.Match) -> str:
            nonlocal counter
            counter += 1
            return f"${counter}"

        formatted_sql = placeholder_pattern.sub(replacer, sql)
        return formatted_sql, params

    @staticmethod
    def _format_named_sql(sql: str, args: Dict[str, Any]) -> Tuple[str, Tuple[Any, ...]]:
        """处理命名占位符：%(name)s -> $n，保持调用端写法一致。"""
        params: List[Any] = []

        def replacer(match: re.Match) -> str:
            key = match.group(1)
            params.append(args[key])
            return f"${len(params)}"

        formatted_sql = re.sub(r"%\(([^)]+)\)s", replacer, sql)
        return formatted_sql, tuple(params)


class TransactionContext:
    """简单事务上下文，封装 acquire / release 与 commit / rollback。"""
    def __init__(self, pool: asyncpg.Pool):
        """保存连接池引用，延迟获取连接。"""
        self.pool = pool
        self.conn: Optional[asyncpg.Connection] = None
        self.tx: Optional[asyncpg.Transaction] = None

    async def __aenter__(self) -> asyncpg.Connection:
        """进入上下文时获取连接并开启事务，返回 raw connection。"""
        self.conn = await self.pool.acquire()
        self.tx = self.conn.transaction()
        await self.tx.start()
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """根据异常情况提交或回滚，并归还连接到连接池。"""
        try:
            if exc_type is None:
                await self.tx.commit()  # type: ignore[union-attr]
            else:
                await self.tx.rollback()  # type: ignore[union-attr]
        finally:
            if self.conn:
                await self.pool.release(self.conn)
                self.conn = None
                self.tx = None

