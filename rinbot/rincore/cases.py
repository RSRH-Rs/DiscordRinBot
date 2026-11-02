"""RinBot 每服务器案件编号（moderation.db 的 mod_cases.case_no）。

bot 与网站面板启动时都会调用 migrate()，两者可能同时运行，因此：
  • 加列时把 "duplicate column name" 视为已迁移；
  • 编号 UPDATE 放在一个 BEGIN IMMEDIATE 事务里，并在事务内重新读取 case_no IS NULL 的行；
  • 唯一索引使用 IF NOT EXISTS。
"""
import sqlite3

import aiosqlite


async def _has_case_no(db: aiosqlite.Connection) -> bool:
    async with db.execute("PRAGMA table_info(mod_cases)") as cur:
        return any(row[1] == "case_no" for row in await cur.fetchall())


async def migrate(db: aiosqlite.Connection) -> None:
    """幂等迁移：补 case_no 列、按服务器编号旧数据、建 (guild_id, case_no) 唯一索引。"""
    if db.in_transaction:
        await db.commit()

    if not await _has_case_no(db):
        try:
            await db.execute("ALTER TABLE mod_cases ADD COLUMN case_no INTEGER")
        except sqlite3.OperationalError as e:
            # 另一个进程刚加好列
            if "duplicate column name" not in str(e).lower():
                raise
        await db.commit()

    await db.execute("BEGIN IMMEDIATE")
    try:
        # 拿到写锁后再读，保证并发迁移不会重复编号同一批行
        async with db.execute(
            "SELECT id, guild_id FROM mod_cases WHERE case_no IS NULL ORDER BY id"
        ) as cur:
            pending = await cur.fetchall()
        if pending:
            async with db.execute(
                "SELECT guild_id, MAX(case_no) FROM mod_cases "
                "WHERE case_no IS NOT NULL GROUP BY guild_id"
            ) as cur:
                counters = {gid: mx for gid, mx in await cur.fetchall()}
            updates = []
            for row_id, gid in pending:
                counters[gid] = (counters.get(gid) or 0) + 1
                updates.append((counters[gid], row_id))
            await db.executemany(
                "UPDATE mod_cases SET case_no = ? WHERE id = ? AND case_no IS NULL",
                updates,
            )
        await db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_mod_cases_guild_case "
            "ON mod_cases (guild_id, case_no)"
        )
        await db.commit()
    except BaseException:
        await db.rollback()
        raise


async def next_case(
    db: aiosqlite.Connection,
    guild_id: int,
    action: str,
    user_id: int,
    mod_id: int,
    reason: str,
    duration: str,
    created_at: float,
) -> int:
    """在 BEGIN IMMEDIATE 事务内分配本服务器的下一个案件号并插入，返回 case_no。"""
    if db.in_transaction:
        await db.commit()
    await db.execute("BEGIN IMMEDIATE")
    try:
        async with db.execute(
            "SELECT COALESCE(MAX(case_no), 0) + 1 FROM mod_cases WHERE guild_id = ?",
            (guild_id,),
        ) as cur:
            case_no = (await cur.fetchone())[0]
        await db.execute(
            "INSERT INTO mod_cases "
            "(guild_id, action, user_id, mod_id, reason, duration, created_at, case_no) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (guild_id, action, user_id, mod_id, reason, duration, created_at, case_no),
        )
        await db.commit()
    except BaseException:
        await db.rollback()
        raise
    return case_no
