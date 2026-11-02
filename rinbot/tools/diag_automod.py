#!/usr/bin/env python3
# 在仓库根目录运行（任意目录均可）：python rinbot/tools/diag_automod.py
# 用来确认 bot 和网站读写的是不是同一个 automod.db，以及里面到底存了什么

import os
import sqlite3
import time

here = os.path.dirname(os.path.abspath(__file__))

# cog 用的路径：DB_PATH = dirname(dirname(cogs/automod.py)) + automod.db
# 脚本位于 rinbot/tools/，所以 cog 的 db 是 rinbot/automod.db（与 CWD 无关）
cog_db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "automod.db")
print(f"📁 脚本所在目录: {here}")
print(f"🤖 cog 期望的 automod.db: {os.path.realpath(cog_db)}")
print(f"   存在吗: {os.path.exists(cog_db)}\n")

# 在祖父目录范围内有限深度扫描所有 automod.db，找出是否存在第二个文件
SKIP = {"node_modules", ".git", ".venv", "venv", "__pycache__", ".cache"}
scan_root = os.path.dirname(here)  # rinbot 的上一级（website 应该也在这）
found = {}
for root, dirs, files in os.walk(scan_root):
    depth = root[len(scan_root):].count(os.sep)
    if depth > 3:
        dirs[:] = []
        continue
    dirs[:] = [d for d in dirs if d not in SKIP]
    if "automod.db" in files:
        rp = os.path.realpath(os.path.join(root, "automod.db"))
        found[rp] = os.path.getmtime(rp)

print(f"🔎 在 {scan_root} 下找到 {len(found)} 个 automod.db 文件：\n")
for p, mt in sorted(found.items(), key=lambda x: -x[1]):
    print("=" * 64)
    print(f"路径: {p}")
    print(f"最后修改: {time.ctime(mt)}")
    try:
        con = sqlite3.connect(p)
        rows = con.execute(
            "SELECT guild_id, enabled, log_channel, anti_repeat, anti_spam "
            "FROM automod_config"
        ).fetchall()
        con.close()
        if not rows:
            print("  ⚠️ automod_config 表为空（没有任何服务器配置）")
        for r in rows:
            print(f"  guild={r[0]}  enabled={r[1]}  log_channel={r[2]}  "
                  f"anti_repeat={r[3]}  anti_spam={r[4]}")
    except Exception as e:
        print(f"  读取失败: {e}")

print("\n" + "=" * 64)
print("判断：")
print("• 若上面出现 >1 个不同路径 → bot 和网站各写各的文件，这就是根因。")
print("• 若只有 1 个文件，但你的服务器那行 enabled=0 → 自动审核根本没开。")
print("• 若 log_channel=0 → 网站存的日志频道没写进去。")
print("• 若你的服务器在表里压根没有 → 网站的保存没落到这个文件。")