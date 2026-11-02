# 子项目 1：Bug 修复与稳定性 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 RinBot 已知 bug、消除多服务器下的稳定性隐患，并建立“推送即部署、预检失败不重启”的上线流水线。

**Architecture:** 新增共享包 `rinbot/rincore/`（存储登记 + WAL、变更日志同步、纯逻辑工具），bot 与网页都引用它；各 cog 的整表轮询替换为变更日志回调；纯逻辑抽到 `rincore` 后用 pytest 覆盖；服务器端用裸仓库 + post-receive hook 部署。

**Tech Stack:** Python 3.11、discord.py 2.7.1、aiosqlite 0.22.1、Quart 0.20 / quart-discord、Pillow、pytest + pytest-asyncio、git、rsync、systemd。

**Spec:** `docs/superpowers/specs/2026-11-02-stability-bugfix-design.md`

## Global Constraints

- 生产环境在用：每个修复先写失败测试再改代码；部署 hook 预检任一失败即中止且不重启服务。
- 不改用户可见文案（多语言是子项目 2）；新增的提示语沿用现有中文风格。
- 数据库迁移只增不删、可重复执行；不修改现有 130 处 `aiosqlite.connect(...)` 调用方式。
- 提交直接在 `master`，作者为用户 git 身份，不开分支、不开 PR；推送 GitHub 不在本计划内。
- 同步轮询间隔 3 秒；变更日志保留 24 小时，每小时清理。
- 服务器依赖安装方式：`pip3 install --break-system-packages`。
- 测试只覆盖纯逻辑与临时 SQLite 库，不连接 Discord。
- 本地运行测试：仓库根目录 `python -m pytest -q`。

## Review Focus

1. **变更日志在 bot 停机期间写入的记录** —— bot 启动时游标取当前最大 id，因为各 cog 已全量加载；重启后不得重放旧记录导致重复 API 调用（如重复改在线状态）。→ Task 3 测试 `test_watcher_starts_after_existing_rows`。
2. **回调抛异常** —— 某个 cog 的 reload 出错不能卡住游标或影响其他模块。→ Task 3 测试 `test_failing_callback_does_not_block_others`。
3. **旧库迁移在生产库上重复执行**（hook 每次部署都会重启 → `cog_load` 重跑迁移）—— 案件号不得重编或冲突。→ Task 7 测试 `test_migration_is_idempotent`。
4. **违禁词列表含空字符串、纯空白或大小写混合条目**（网页可能写入）—— 不得误判所有消息为违规。→ Task 6 测试 `test_blank_words_ignored`。
5. **服务器列表恰好 200 的整数倍** —— 分页必须再取一页确认结束，不能少取或死循环。→ Task 4 测试 `test_exact_multiple_of_page_size`。

---

## 文件结构

| 路径 | 职责 |
|---|---|
| `rinbot/rincore/__init__.py` | 空包标记 |
| `rinbot/rincore/storage.py` | `BOT_DIR`、`DB_FILES` 登记、`enable_wal()` |
| `rinbot/rincore/sync.py` | `notify()`、`ChangeWatcher` |
| `rinbot/rincore/textmatch.py` | `normalize`、`find_badword`、`find_links`、`host_of`、`is_whitelisted` |
| `rinbot/rincore/durations.py` | `parse_duration`、`format_duration` |
| `rinbot/rincore/roles.py` | `exclusive_changes` |
| `rinbot/rincore/throttle.py` | `Debouncer` |
| `rinbot/rincore/cases.py` | 案件号迁移与分配 |
| `website/guild_ids.py` | `collect_guild_ids` 分页 |
| `tests/conftest.py` | 把 `rinbot/`、`website/` 加入 `sys.path` |
| `tests/test_*.py` | 各模块测试 |
| `deploy/post-receive` | 服务器部署 hook（入库，scp 安装） |
| `pytest.ini`、`requirements-dev.txt` | 测试配置 |

---

### Task 1: 部署流水线（先于一切代码改动，用基线验证）

**Files:**
- Create: `deploy/post-receive`
- Create: `pytest.ini`、`requirements-dev.txt`、`tests/conftest.py`
- Modify: 本地 `~/.ssh/config`（追加主机条目）

**Interfaces:**
- Produces: 本地 remote `prod`；`git push prod master` 触发部署；hook 输出 `DEPLOY OK` 或 `DEPLOY ABORTED: <原因>`。

- [ ] **Step 1: 测试骨架**

`pytest.ini`：
```ini
[pytest]
testpaths = tests
asyncio_mode = auto
```
`requirements-dev.txt`：`pytest==8.3.3`、`pytest-asyncio==0.24.0`。
`tests/conftest.py`：把仓库根下 `rinbot` 与 `website` 绝对路径插入 `sys.path` 开头。另建 `tests/test_smoke.py`，内容 `def test_smoke(): assert True`。

- [ ] **Step 2: 本地安装并运行**

Run: `python -m pip install -r requirements-dev.txt && python -m pytest -q`
Expected: `1 passed`

- [ ] **Step 3: 编写 `deploy/post-receive`（bash，`set -euo pipefail`）**

行为（按序，任一失败 `echo "DEPLOY ABORTED: <步骤>"` 并 `exit 1`，不触及 `/root/rinbot`、`/root/website`、不重启）：
1. 读 stdin 的 `oldrev newrev ref`，`ref` 不是 `refs/heads/master` 则跳过。
2. `rm -rf /root/rinbot-src && mkdir -p /root/rinbot-src && git --git-dir=/root/rinbot.git --work-tree=/root/rinbot-src checkout -f master`
3. `python3 -m compileall -q /root/rinbot-src/rinbot /root/rinbot-src/website`
4. 复制真实配置供测试与冒烟导入：`cp /root/rinbot/config.py /root/rinbot-src/rinbot/config.py` 与 `cp /root/website/config.py /root/rinbot-src/website/config.py`；用 `trap` 保证脚本退出时（无论成败）删除这两个副本。
5. 若存在 `/root/rinbot-src/tests`：`cd /root/rinbot-src && python3 -m pytest -q`
6. 导入冒烟：`cd /root/rinbot-src/rinbot && python3 -c "import importlib,os,sys; sys.path.insert(0,'cogs'); [importlib.import_module('cogs.'+f[:-3]) for f in sorted(os.listdir('cogs')) if f.endswith('.py') and not f.startswith('_')]"`
7. `rsync -a --delete` 两次（`rinbot/`→`/root/rinbot/`，`website/`→`/root/website/`），共同排除：`*.db`、`*.db-wal`、`*.db-shm`、`*.db-journal`、`config.py`、`uploads/`、`health.json`、`*.log`、`__pycache__/`、`*.bak*`、`.env`。
8. 若 `git diff --name-only $oldrev $newrev` 含 `rinbot/requirements.txt`（`oldrev` 全零时视为含）：`pip3 install --break-system-packages -r /root/rinbot/requirements.txt`
9. `systemctl restart discordbot mysite; sleep 5`；输出两服务 `systemctl is-active` 与各自 `journalctl -n 20 --no-pager -o cat`；两者都 `active` 打印 `DEPLOY OK`，否则打印 `DEPLOY FAILED: service not active` 并 `exit 1`。

- [ ] **Step 4: 服务器备份与准备**

Run（经 `ssh -i ~/.ssh/rinbot_ed25519 -o IdentitiesOnly=yes root@192.168.2.18`）：
```bash
mkdir -p /root/deploy-backups && tar czf /root/deploy-backups/pre-rincore-$(date +%Y%m%d-%H%M%S).tar.gz /root/rinbot /root/website
git init -q --bare -b master /root/rinbot.git
pip3 install --break-system-packages pytest==8.3.3 pytest-asyncio==0.24.0
```
Expected: tar 文件存在且 `tar tzf` 可列出 `root/rinbot/main.py`；`/root/rinbot.git/HEAD` 存在。

首次推送 `oldrev` 为全零，hook 会执行 `pip install`。推送前先核对：`pip3 freeze` 中 `rinbot/requirements.txt` 每个包的已装版本与固定版本一致；若有不一致，停下来把差异报告给用户，由用户决定是先改 `requirements.txt` 对齐线上版本，还是接受升级。

- [ ] **Step 5: 安装 hook 与本地 remote**

`scp deploy/post-receive` 到 `/root/rinbot.git/hooks/post-receive` 并 `chmod +x`。本地 `~/.ssh/config` 追加：
```
Host rinbot-prod
    HostName 192.168.2.18
    User root
    IdentityFile ~/.ssh/rinbot_ed25519
    IdentitiesOnly yes
```
`git remote add prod rinbot-prod:/root/rinbot.git`

- [ ] **Step 6: 提交并推送基线以验证流水线**

```bash
git add deploy pytest.ini requirements-dev.txt tests
git commit -m "Add deploy hook and test scaffolding"
git push prod master
```
Expected: 推送输出末尾 `DEPLOY OK`，两服务 `active`；之后在服务器执行 `diff -rq /root/rinbot-src/rinbot /root/rinbot -x '*.db*' -x config.py -x uploads -x health.json -x '*.log' -x __pycache__ -x '*.bak*'` 仅报告 `config.example.py` 差异以外无内容差异。bot 在 Discord 中恢复在线。

---

### Task 2: `rincore.storage` 与 WAL

**Files:**
- Create: `rinbot/rincore/__init__.py`、`rinbot/rincore/storage.py`
- Modify: `rinbot/main.py`（`setup_hook` 开头）、`website/routes.py:167-185`（DB 常量改引用）、`website/routes.py` 中 `ensure_tables()` 开头
- Test: `tests/test_storage.py`

**Interfaces:**
- Produces: `storage.BOT_DIR: str`；`storage.DB_FILES: dict[str, str]`（键：`welcome automod moderation giveaway leveling botconfig reactionroles commandtoggle musicconfig botlog serverlog globalsettings music sync`，值为 `BOT_DIR` 下绝对路径）；`storage.db_path(name: str) -> str`；`async storage.enable_wal(paths: Iterable[str] | None = None) -> None`（默认全部 `DB_FILES`，文件不存在也创建并设 WAL）。

- [ ] **Step 1: 写失败测试** `test_enable_wal_sets_journal_mode`（`tmp_path` 下两个库，调用后 `PRAGMA journal_mode` 返回 `wal`）与 `test_db_files_cover_dashboard_constants`（断言 `DB_FILES` 包含上表全部键，且 `db_path("sync")` 以 `sync.db` 结尾）。
- [ ] **Step 2: 运行** `python -m pytest tests/test_storage.py -q` → FAIL（模块不存在）。
- [ ] **Step 3: 实现** `storage.py`；`main.py` `setup_hook` 首行 `await storage.enable_wal()`；`routes.py` 在 `BOT_DIR` 定义后 `sys.path.insert(0, BOT_DIR)`，`DB_*` 常量改为 `storage.db_path(...)`，`ensure_tables()` 首行 `await storage.enable_wal()`。
- [ ] **Step 4: 运行** 全部测试 → PASS；`python -m compileall -q rinbot website` 无输出。
- [ ] **Step 5: 提交** `git commit -m "Add rincore.storage and enable SQLite WAL for bot and dashboard"`

---

### Task 3: `rincore.sync` 变更日志

**Files:**
- Create: `rinbot/rincore/sync.py`
- Modify: `rinbot/main.py`（`HybridBot.__init__` 创建 `self.change_watcher`；`setup_hook` 在加载 cog 之前 `await self.change_watcher.start()`）
- Test: `tests/test_sync.py`

**Interfaces:**
- Consumes: `storage.db_path("sync")`
- Produces:
  - `MODULES = ("welcome","automod","moderation","music","botlog","serverlog","reactionroles","commands","global")`
  - `async notify(module: str, guild_id: int, *, path: str | None = None) -> None`（未知 module 抛 `ValueError`）
  - `class ChangeWatcher(path: str | None = None, interval: float = 3.0, retention: float = 86400.0)`
    - `register(module: str, callback: Callable[[int], Awaitable[None]]) -> None` / `unregister(module, callback) -> None`
    - `async start() -> None`（建表、游标=当前最大 id、启动后台任务）/ `async stop() -> None`
    - `async poll_once() -> int`（处理一次新记录，返回分发的 `(module, guild_id)` 数，供测试直接调用）
    - `async prune(now: float | None = None) -> int`（删除早于 `retention` 的行，返回删除数；后台任务每小时调用）

- [ ] **Step 1: 写失败测试**
  - `test_notify_then_poll_dispatches_once`：两次 `notify("automod", 1)` + 一次 `notify("automod", 2)` → `poll_once()` 返回 2，回调收到 `{1, 2}`。
  - `test_watcher_starts_after_existing_rows`：先 `notify` 一条，再 `start()`，`poll_once()` 返回 0。
  - `test_failing_callback_does_not_block_others`：`automod` 回调抛异常、`serverlog` 回调正常 → 后者被调用；再次 `poll_once()` 返回 0（游标已推进）。
  - `test_prune_removes_old_rows`：写入后 `prune(now=time.time()+86401)` 返回 1。
  - `test_unknown_module_rejected`：`notify("nope", 1)` 抛 `ValueError`。
- [ ] **Step 2: 运行** `python -m pytest tests/test_sync.py -q` → FAIL。
- [ ] **Step 3: 实现** `sync.py`（表结构见 spec 1.2；分发前按 `(module, guild_id)` 去重；回调异常 `print` 后继续）与 `main.py` 接线。
- [ ] **Step 4: 运行** 全部测试 → PASS。
- [ ] **Step 5: 提交** `git commit -m "Add rincore.sync change log for dashboard-to-bot config propagation"`

---

### Task 4: 网页端通知与服务器列表分页

**Files:**
- Create: `website/guild_ids.py`
- Modify: `website/routes.py`：`fetch_bot_guild_ids`（:516）；写入接口 —— welcome POST（:1159）与图片路由（:1219）、automod POST（:1398）、moderation POST（:1488）、music POST（:1621）、botlog POST（:1683）、serverlog POST（:1815）、reactionroles/send（:2282）、commands/toggle（:2667）、commands/bulk-toggle（:2705）、bot/maintenance POST（:1976）、bot/blacklist POST（:2008）、bot/blacklist/remove（:2027）、bot/commands/toggle（:2129）、bot/personalizer POST（:2172）、bot/username（:2199）、bot/avatar POST（:2220）
- Test: `tests/test_guild_ids.py`

**Interfaces:**
- Consumes: `sync.notify`
- Produces: `async collect_guild_ids(fetch_page: Callable[[int | None], Awaitable[list[dict]]], page_size: int = 200) -> set[int]`（`fetch_page(after)` 返回该页 guild 字典列表；按最后一个 `id` 继续，直到返回数 < `page_size`）

- [ ] **Step 1: 写失败测试** `test_collects_all_pages`（假 `fetch_page` 共 450 个 id → 返回 450 个）、`test_exact_multiple_of_page_size`（400 个 → 返回 400，`fetch_page` 被调用 3 次）、`test_single_short_page`（5 个 → 调用 1 次）。
- [ ] **Step 2: 运行** → FAIL。
- [ ] **Step 3: 实现** `collect_guild_ids`；`fetch_bot_guild_ids` 改用它（`after` 拼进 `?limit=200&after=`），模块级缓存 `(时间戳, 集合)` 60 秒，异常时返回旧缓存或空集合。每个写入接口在写库成功、返回响应前 `await sync.notify(<module>, g)`：映射为 welcome→`welcome`、automod→`automod`、moderation→`moderation`、music→`music`、botlog→`botlog`、serverlog→`serverlog`、reactionroles→`reactionroles`、guild commands 两个→`commands`、所有 `/api/bot/*` 写入→`("global", 0)`。
- [ ] **Step 4: 运行** 全部测试 → PASS；逐个打开上面列出的 17 个路由函数，确认每个成功写库的分支都调用了 `sync.notify`（同一函数有多个写库分支，如图片上传与删除，则每个分支各调用一次）。
- [ ] **Step 5: 提交** `git commit -m "Dashboard: paginate bot guild list and notify bot of config changes"`

---

### Task 5: cog 轮询替换为同步回调

**Files:**
- Modify: `rinbot/cogs/automod.py`（删 `_refresh`，加 `reload_guild`）、`rinbot/cogs/serverlog.py`（删 `_refresh`）、`rinbot/cogs/botlog.py`（删 `_refresh`）、`rinbot/cogs/commandtoggle.py`（删 `refresh_loop`）、`rinbot/cogs/botconfig.py`（删 `check_presence` 循环，保留其主体为 `apply_presence`）、`rinbot/cogs/globalsettings.py`（`_tick` 去掉 `_reload`；加载 `global_disabled_cmds`；`blocked_reason`）、`rinbot/cogs/musicconfig.py`（内存缓存）、`rinbot/cogs/reactionroles.py`（缓存权威化 + 按服务器重载）
- Test: `tests/test_globalsettings_logic.py`

**Interfaces:**
- Consumes: `bot.change_watcher.register/unregister`
- Produces:
  - 各 cog `async reload_guild(guild_id: int) -> None`（`cog_load` 中 `register`，`cog_unload` 中 `unregister`）；`botconfig` 与 `globalsettings` 注册在 `global` 上，忽略参数做全量重载（只一行/一张小表）。
  - `GlobalSettings.blocked_reason(user_id: int, command_name: str | None = None) -> str | None`：主人返回 `None`；黑名单返回 `""`（静默拒绝）；维护模式返回维护提示；`command_name` 在全局禁用集合中返回 `"⛔ 该指令已被全局停用。"`。
  - `MusicConfig.get_config(guild_id) -> dict` 签名不变，读内存。
  - `ReactionRoles`：`_cache` 视为权威，`on_raw_reaction_add/remove` 与 `on_interaction` 缓存未命中直接返回（删除回退查库）。

- [ ] **Step 1: 写失败测试**：把判定逻辑写成模块级纯函数 `decide_block(user_id, owner_id, blacklist, maintenance, maint_msg, disabled, command_name) -> str | None`（放在 `globalsettings.py`，`blocked_reason` 调用它），测试 `test_owner_never_blocked`、`test_blacklisted_silent`（返回 `""`）、`test_maintenance_message`、`test_globally_disabled_command`、`test_normal_user_allowed`。
- [ ] **Step 2: 运行** → FAIL。
- [ ] **Step 3: 实现** 上述 cog 改动；`_global_check` 改为调用 `blocked_reason(ctx.author.id, ctx.command.qualified_name.split()[0])`，结果为 `None` 放行，`""` 静默拒绝，其他字符串 ephemeral 发送后拒绝。
- [ ] **Step 4: 运行** 全部测试 → PASS；`grep -nE "tasks.loop" rinbot/cogs/{automod,serverlog,botlog,commandtoggle,botconfig}.py` 无输出。
- [ ] **Step 5: 提交** `git commit -m "Replace config polling loops with change-log callbacks; honor global command disable"`

---

### Task 6: 自动审核匹配与刷屏处理

**Files:**
- Create: `rinbot/rincore/textmatch.py`
- Modify: `rinbot/cogs/automod.py:192-375`（`on_message` 第 1、3、4、5 段）、`__init__`（缓存结构）
- Test: `tests/test_textmatch.py`

**Interfaces:**
- Produces: `normalize(text: str) -> str`；`find_badword(text: str, words: Iterable[str]) -> str | None`；`find_links(text: str) -> list[str]`；`host_of(link: str) -> str`；`is_whitelisted(host: str, whitelist: Iterable[str]) -> bool`。规则见 spec 2.1。

- [ ] **Step 1: 写失败测试**（每条一个测试函数，值来自 spec）：
  - `find_badword("this is class", ["ass"]) is None`
  - `find_badword("ＡＳＳ", ["ass"]) == "ass"`；`find_badword("a​ss", ["ass"]) == "ass"`
  - `find_badword("违 禁 词", ["违禁词"]) == "违禁词"`；`find_badword("违.禁.词", ["违禁词"]) == "违禁词"`
  - `test_blank_words_ignored`：`find_badword("hello", ["", "  "]) is None`
  - `find_badword("You ASS", ["Ass"]) == "Ass"`（返回原始词）
  - `find_links` 识别：`"see example.com/x"`、`"www.example.com"`、`"discord.gg/abc"`、`"https://a.b/c"` 各返回 1 条
  - `find_links` 不识别：`"me@example.com"`、`"v1.2.3"`、`"pi is 3.14"` 返回 `[]`
  - `is_whitelisted("cdn.example.com", ["example.com"])` 为真；`is_whitelisted("badexample.com", ["example.com"])` 为假；`is_whitelisted("x.example.com", ["*.example.com"])` 为真
- [ ] **Step 2: 运行** → FAIL。
- [ ] **Step 3: 实现** `textmatch.py`；`automod.on_message`：违禁词段改用 `find_badword`；链接段改用 `find_links` + `host_of` + `is_whitelisted`；刷屏缓存改为 `list[tuple[float, int, int]]`（时间、频道 id、消息 id），触发时按频道分组 `channel.delete_messages(...)`，`HTTPException` 时逐条 `delete` 并忽略失败；大写段删除后调用 `_log_action`（标题 `📢 大写轰炸`）；新增 `tasks.loop(minutes=10)` `_prune_caches`，删除最近记录早于 60 秒的用户与空服务器条目。
- [ ] **Step 4: 运行** 全部测试 → PASS。
- [ ] **Step 5: 提交** `git commit -m "Automod: normalized word matching, scheme-less/invite link detection, spam cleanup"`

---

### Task 7: 管理模块（案件号、按 ID 封禁）与共享时长解析

**Files:**
- Create: `rinbot/rincore/durations.py`、`rinbot/rincore/cases.py`
- Modify: `rinbot/cogs/moderation.py`（`cog_load` 迁移、`_log_case`、`ban`、`tempban`、DM 异常、`modlog` 查询 :782/:787、展示 :806-812）、`rinbot/cogs/giveaway.py`（`_parse_duration` 改调 `durations.parse_duration`）、`website/routes.py:1525-1567`（返回 `case_no`）、`website/static/js/server.js` 中显示案件 `id` 处改用 `case_no`
- Test: `tests/test_durations.py`、`tests/test_cases.py`

**Interfaces:**
- Produces:
  - `parse_duration(s: str) -> int | None`（giveaway 现行规则：`(?:\d+[dhms])+`、单位不重复、`0 < 秒 ≤ 365*86400`）；`format_duration(seconds: int) -> str`（沿用 moderation 现有 `_format_duration` 输出格式）
  - `async cases.migrate(db: aiosqlite.Connection) -> None`（幂等，见 spec 2.2）
  - `async cases.next_case(db, guild_id, action, user_id, mod_id, reason, duration, created_at) -> int`（`BEGIN IMMEDIATE` 内分配并插入，返回 `case_no`）

- [ ] **Step 1: 写失败测试**
  - durations：`parse_duration("1d12h") == 129600`；`parse_duration("1h1h") is None`；`parse_duration("366d") is None`；`parse_duration("abc") is None`；`format_duration(3600)` 等于迁移前 moderation `_format_duration(3600)` 的输出（先在测试里写死当前实际输出字符串）。
  - cases：`test_migration_numbers_per_guild`（guild A、B 交错插 5 行旧数据 → A 为 1..3、B 为 1..2，按原 id 顺序）；`test_migration_is_idempotent`（迁移两次结果相同）；`test_next_case_continues`（迁移后 A 新案件为 4）；`test_unique_index_exists`。
- [ ] **Step 2: 运行** → FAIL。
- [ ] **Step 3: 实现**；`ban` 参数改 `user: discord.User`、新增 `delete_days: commands.Range[int, 0, 7] = 0`，目标在服务器内时做层级检查与私信，调用 `ctx.guild.ban(user, reason=..., delete_message_seconds=delete_days * 86400)`；`tempban` 改 `delete_message_seconds=0`；所有私信 `except (discord.Forbidden, discord.HTTPException)`；用户可见“案件 #N”全部使用 `case_no`。
- [ ] **Step 4: 运行** 全部测试 → PASS。
- [ ] **Step 5: 提交** `git commit -m "Moderation: per-guild case numbers, ban by user ID with message deletion, shared duration parsing"`

---

### Task 8: 等级与欢迎

**Files:**
- Modify: `rinbot/cogs/leveling.py:172-219`（`on_message`）、`:265`（`rank` 画图）、`rinbot/cogs/welcome.py:349-360`（`_render_card_file`）、`:407-487`（加入/离开监听），新增 `on_member_update`
- Test: `tests/test_leveling_logic.py`

**Interfaces:**
- Produces: `leveling.prune_cooldowns(cooldowns: dict, now: float, ttl: float, max_size: int = 5000) -> None`（超过 `max_size` 时就地删除早于 `ttl` 的条目）；`welcome.Welcome._assign_auto_roles(member, config) -> None`。

- [ ] **Step 1: 写失败测试** `test_prune_noop_under_limit`、`test_prune_removes_stale_when_over_limit`（5001 条旧 + 1 条新 → 只剩新条目）。
- [ ] **Step 2: 运行** → FAIL。
- [ ] **Step 3: 实现**：leveling `on_message` 在同一连接内先 `commit` 再发升级提示，发送包 `try/except (Forbidden, HTTPException)`；写入冷却后调用 `prune_cooldowns`；`rank` 用 `await asyncio.to_thread(...)`；welcome `_render_card_file` 用 `asyncio.to_thread`；`_assign_auto_roles` 一次 `add_roles(*roles)`，`Forbidden` 时 `print`；`on_member_join` 若 `member.pending` 不发身份组（欢迎消息照发）；`on_member_update` 在 `before.pending and not after.pending` 时调用 `_assign_auto_roles`；欢迎/道别 `channel.send` 包 `try/except (Forbidden, HTTPException)`。
- [ ] **Step 4: 运行** 全部测试 → PASS。
- [ ] **Step 5: 提交** `git commit -m "Leveling/welcome: keep XP on send failure, render cards off the event loop, respect membership screening"`

---

### Task 9: 抽奖节流与反应身份组单选

**Files:**
- Create: `rinbot/rincore/throttle.py`、`rinbot/rincore/roles.py`
- Modify: `rinbot/cogs/giveaway.py:28-106`（`GiveawayEntryButton.enter`）、`rinbot/cogs/reactionroles.py:447-487`（`on_raw_reaction_add`）、`:533-622`（按钮单选改用 `exclusive_changes`）
- Test: `tests/test_throttle.py`、`tests/test_roles.py`

**Interfaces:**
- Produces:
  - `class Debouncer(delay: float)`；`schedule(key: Hashable, coro_factory: Callable[[], Awaitable[None]]) -> None`：同一 key 在 `delay` 秒内多次调度只在窗口结束时执行最后一次的 factory。
  - `exclusive_changes(member_role_ids: set[int], panel_role_ids: set[int], chosen: int) -> tuple[set[int], set[int]]` 返回 `(to_add, to_remove)`：已有 `chosen` 时 `to_add` 为空；`to_remove = (member ∩ panel) − {chosen}`。

- [ ] **Step 1: 写失败测试**：`test_debounce_coalesces`（`delay=0.05`，同 key 调度 10 次，`await asyncio.sleep(0.1)` 后只执行 1 次且为最后一次）、`test_debounce_separate_keys`；`test_exclusive_switch`（成员有 {1,9}，面板 {1,2,3}，选 2 → `({2},{1})`）、`test_exclusive_already_has`（有 {2} 选 2 → `(set(), set())`）。
- [ ] **Step 2: 运行** → FAIL。
- [ ] **Step 3: 实现**；giveaway：Cog 持有 `Debouncer(5.0)`，`enter` 只做 ephemeral 回复，再 `schedule(message_id, 编辑按钮标签为最新人数)`；reactionroles：反应添加时若面板 `exclusive`，按 `exclusive_changes` 移除身份组，并对该消息上该用户的其他映射表情 `message.remove_reaction(emoji, member)`（`Forbidden/HTTPException` 忽略）；按钮单选改用同一函数。
- [ ] **Step 4: 运行** 全部测试 → PASS。
- [ ] **Step 5: 提交** `git commit -m "Throttle giveaway button edits; exclusive mode for reaction-role panels"`

---

### Task 10: 错误上报、组件拦截与私信防护

**Files:**
- Modify: `rinbot/cogs/botlog.py`（新增 `report_exception`，改写 `on_command_error` :144-170）、`rinbot/cogs/errors.py:56-112`、`rinbot/cogs/music.py:567-598`（`after_play` 中 botlog 调用）、`NowPlayingView` / `SearchView`（music.py）、`GiveawayEntryButton`、`netease._OwnerView.interaction_check`（:106）、`reactionroles.on_interaction`；所有 cog 中使用 `ctx.guild` 的 hybrid 指令与组
- Test: `tests/test_guild_only.py`、`tests/test_error_id.py`

**Interfaces:**
- Consumes: `GlobalSettings.blocked_reason`
- Produces:
  - `botlog.new_error_id() -> str`（8 位大写十六进制）
  - `BotLog.report_exception(guild_id: int | None, title: str, exc: BaseException, **fields) -> str`：完整 traceback 只发到 `DEV_GUILD_ID` 的 bot 日志（`error` 等级，附来源服务器 ID）并 `print`；`guild_id` 非空时向该服务器日志发送不含 traceback 的条目“出错了（错误编号 XXXX）”；返回错误编号。
  - `async def check_component(bot, interaction: discord.Interaction) -> bool`（位于 `rinbot/cogs/_botlog_helper.py`）：调用 `blocked_reason(interaction.user.id)`，被拦截时 ephemeral 回复（黑名单静默用“❌ 你无法使用此功能。”）并返回 `False`。

- [ ] **Step 1: 写失败测试**
  - `test_error_id_format`：`re.fullmatch(r"[0-9A-F]{8}", new_error_id())`。
  - `test_guild_commands_are_guild_only`：用 `ast` 解析 `rinbot/cogs/*.py`（排除 `general.py`、`help.py`、`dev.py`），每个带 `hybrid_command`/`hybrid_group` 装饰器且函数体引用 `ctx.guild` 的函数，装饰器列表必须包含 `guild_only`；失败信息列出 `文件:函数名`。
- [ ] **Step 2: 运行** → FAIL（列出缺失 `guild_only` 的指令）。
- [ ] **Step 3: 实现**：为测试列出的指令加 `@commands.guild_only()`；`errors._on_app_error` 与 `on_command_error` 的未知错误改为 `report_exception`，用户看到“😵 出了点问题（错误编号 XXXX），请稍后再试。”；`botlog.on_command_error` 改为调用 `report_exception`；music `after_play` 同；上述各 View 的 `interaction_check` 与 `reactionroles.on_interaction` 开头调用 `check_component`。
- [ ] **Step 4: 运行** 全部测试 → PASS。
- [ ] **Step 5: 提交** `git commit -m "Route tracebacks to dev guild only, gate components on blacklist/maintenance, guild-only commands"`

---

### Task 11: 清理

**Files:**
- Delete: `rinbot/serverlog.py`、`rinbot/help.py`
- Move: `rinbot/diag_automod.py` → `rinbot/tools/diag_automod.py`（更新文件头注释中的运行方式与 `DB_PATH` 相对路径）

- [ ] **Step 1: 确认无引用** `grep -rnE "^\s*(from|import)\s+(serverlog|help)\b" rinbot website` → 无输出。
- [ ] **Step 2: 删除/移动**，`python -m compileall -q rinbot website` 无输出，全部测试 PASS。
- [ ] **Step 3: 提交** `git commit -m "Remove duplicate root modules and move automod diagnostic to tools/"`

---

### Task 12: 上线与验收

- [ ] **Step 1: 本地全量** `python -m pytest -q` 全绿；`python -m compileall -q rinbot website` 无输出。
- [ ] **Step 2: 推送** `git push prod master` → 末尾 `DEPLOY OK`。若 `DEPLOY ABORTED`，按输出修复后重推，线上不受影响。
- [ ] **Step 3: 服务器手改 OAuth 配置**：备份 `website/config.py` 为 `config.py.bak-<时间戳>`，删除 `os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"` 一行，`systemctl restart mysite`；本地同步修改 `website/config.example.py` 并提交。浏览器访问 https://rin-bot.com 完成一次 Discord 登录；若回调报 `InsecureTransportError`，还原备份并在 `mysite.service` 加 `Environment=RINBOT_ALLOW_HTTP=1` 后 `daemon-reload` + 重启，记录待查。
- [ ] **Step 4: 日志观察** `journalctl -u discordbot -u mysite -f` 10 分钟，无新增 Traceback；`sqlite3 /root/rinbot/automod.db "PRAGMA journal_mode"` 输出 `wal`。
- [ ] **Step 5: 开发服务器手动验收**（spec 第 4 部分第 6 条全部 12 项），逐项记录通过/失败。
- [ ] **Step 6: 提交** 验收记录追加到 spec 末尾“验收记录”小节，`git commit -m "Record sub-project 1 acceptance results"`；`git push prod master`（仅文档变更，确认 hook 照常 `DEPLOY OK`）。
