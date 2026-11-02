import asyncio
import sqlite3

import aiosqlite

from rincore import cases

OLD_SCHEMA = """
    CREATE TABLE mod_cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        mod_id INTEGER NOT NULL,
        reason TEXT DEFAULT '未提供原因',
        duration TEXT DEFAULT '',
        created_at REAL NOT NULL
    )
"""

# 两个服务器交错插入：A=100, B=200
SEED = [100, 200, 100, 100, 200]


def make_old_db(path):
    con = sqlite3.connect(path)
    con.execute(OLD_SCHEMA)
    for i, gid in enumerate(SEED):
        con.execute(
            "INSERT INTO mod_cases (guild_id, action, user_id, mod_id, reason, duration, created_at)"
            " VALUES (?, 'warn', 1, 2, 'r', '', ?)",
            (gid, float(i)),
        )
    con.commit()
    con.close()


async def dump(path):
    async with aiosqlite.connect(path) as db:
        cur = await db.execute(
            "SELECT id, guild_id, case_no FROM mod_cases ORDER BY id"
        )
        return await cur.fetchall()


async def test_migration_numbers_per_guild(tmp_path):
    path = str(tmp_path / "moderation.db")
    make_old_db(path)
    async with aiosqlite.connect(path) as db:
        await cases.migrate(db)
    rows = await dump(path)
    assert rows == [
        (1, 100, 1),
        (2, 200, 1),
        (3, 100, 2),
        (4, 100, 3),
        (5, 200, 2),
    ]


async def test_migration_is_idempotent(tmp_path):
    path = str(tmp_path / "moderation.db")
    make_old_db(path)
    async with aiosqlite.connect(path) as db:
        await cases.migrate(db)
    first = await dump(path)
    async with aiosqlite.connect(path) as db:
        await cases.migrate(db)
        await cases.migrate(db)
    assert await dump(path) == first


async def test_migration_continues_after_existing_numbers(tmp_path):
    """部分行已有 case_no 时，新编号续接该服务器已有最大值。"""
    path = str(tmp_path / "moderation.db")
    make_old_db(path)
    async with aiosqlite.connect(path) as db:
        await cases.migrate(db)
        await db.execute(
            "INSERT INTO mod_cases (guild_id, action, user_id, mod_id, created_at)"
            " VALUES (100, 'warn', 1, 2, 9.0)"
        )
        await db.commit()
        await cases.migrate(db)
    rows = await dump(path)
    assert rows[-1] == (6, 100, 4)
    assert rows[:5] == [(1, 100, 1), (2, 200, 1), (3, 100, 2), (4, 100, 3), (5, 200, 2)]


async def test_migration_on_empty_table(tmp_path):
    path = str(tmp_path / "moderation.db")
    con = sqlite3.connect(path)
    con.execute(OLD_SCHEMA)
    con.commit()
    con.close()
    async with aiosqlite.connect(path) as db:
        await cases.migrate(db)
        assert await cases.next_case(db, 100, "ban", 1, 2, "r", "", 1.0) == 1


async def test_next_case_continues(tmp_path):
    path = str(tmp_path / "moderation.db")
    make_old_db(path)
    async with aiosqlite.connect(path) as db:
        await cases.migrate(db)
        assert await cases.next_case(db, 100, "ban", 5, 6, "why", "1小时", 99.0) == 4
        assert await cases.next_case(db, 200, "kick", 5, 6, "why", "", 99.0) == 3
        assert await cases.next_case(db, 300, "kick", 5, 6, "why", "", 99.0) == 1
        assert await cases.next_case(db, 100, "ban", 5, 6, "why", "", 99.0) == 5
        cur = await db.execute(
            "SELECT action, user_id, mod_id, reason, duration, created_at"
            " FROM mod_cases WHERE guild_id=100 AND case_no=4"
        )
        assert await cur.fetchone() == ("ban", 5, 6, "why", "1小时", 99.0)


async def test_next_case_concurrent_unique(tmp_path):
    path = str(tmp_path / "moderation.db")
    make_old_db(path)
    async with aiosqlite.connect(path) as db:
        await cases.migrate(db)

    async def one(i):
        async with aiosqlite.connect(path) as db:
            return await cases.next_case(db, 100, "warn", i, 2, "r", "", float(i))

    got = await asyncio.gather(*[one(i) for i in range(10)])
    assert sorted(got) == list(range(4, 14))


async def test_unique_index_exists(tmp_path):
    path = str(tmp_path / "moderation.db")
    make_old_db(path)
    async with aiosqlite.connect(path) as db:
        await cases.migrate(db)
        cur = await db.execute("PRAGMA index_list(mod_cases)")
        idx = [r for r in await cur.fetchall() if r[2]]  # unique
        names = []
        for r in idx:
            c = await db.execute(f"PRAGMA index_info({r[1]})")
            names.append([x[2] for x in await c.fetchall()])
        assert ["guild_id", "case_no"] in names
        try:
            await db.execute(
                "INSERT INTO mod_cases (guild_id, action, user_id, mod_id, created_at, case_no)"
                " VALUES (100, 'warn', 1, 2, 1.0, 1)"
            )
            raise AssertionError("duplicate case_no accepted")
        except sqlite3.IntegrityError:
            pass


async def test_concurrent_migrations_equal_single(tmp_path):
    """bot 与网站同时启动：两个连接并发迁移，结果与单次迁移一致。"""
    single = str(tmp_path / "single.db")
    multi = str(tmp_path / "multi.db")
    make_old_db(single)
    make_old_db(multi)
    async with aiosqlite.connect(single) as db:
        await cases.migrate(db)

    async def run():
        async with aiosqlite.connect(multi) as db:
            await cases.migrate(db)

    await asyncio.gather(run(), run(), run())
    assert await dump(multi) == await dump(single)
    async with aiosqlite.connect(multi) as db:
        cur = await db.execute("PRAGMA index_list(mod_cases)")
        assert sum(1 for r in await cur.fetchall() if r[2]) == 1


async def test_migrate_tolerates_column_added_by_other_process(tmp_path):
    path = str(tmp_path / "moderation.db")
    make_old_db(path)
    con = sqlite3.connect(path)
    con.execute("ALTER TABLE mod_cases ADD COLUMN case_no INTEGER")
    con.commit()
    con.close()
    async with aiosqlite.connect(path) as db:
        await cases.migrate(db)
    assert [r[2] for r in await dump(path)] == [1, 1, 2, 3, 2]
