# 指令与消息改版一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 机器人和网页发到 Discord 的所有 embed 走同一套模板和五种颜色；机器人不再触发全服或身份组提醒；管理指令默认对普通成员隐藏，开发和主人指令只在开发服务器出现；报错、`/status`、`/help` 按规范重写。

**Architecture:** 新增不依赖 discord.py 的 `rinbot/rincore/embeds.py`，生成 embed 的 JSON，机器人和网页共用。机器人侧新增两个 cog 辅助模块：`cogs/_messages.py`（转成 `discord.Embed`、私密发送、提示文案）和 `cogs/_perms.py`（`require` / `owner_only` 装饰器）。各 cog 改为只经过这两个模块生成消息和声明权限，AST 测试防止回退。

**Tech Stack:** Python 3.11, discord.py 2.7.1, aiosqlite, Quart（网页），pytest（`asyncio_mode = auto`），Node 内置测试（控制台 JS）。

**Spec:** `docs/superpowers/specs/2026-11-04-bot-messages-foundation-design.md`

## Global Constraints

- 五种颜色：信息 `0xEB8BAC`，成功 `0x3BA55D`，注意 `0xF0B232`，失败 `0xED4245`，日志 `0x80848E`。种类名 `info` / `success` / `warning` / `error` / `log`。
- 标题和字段名不加 emoji、不用英文大写；页脚不写"请求者"和品牌口号；时间戳只加在日志类消息上。
- Discord 上限：标题 256，正文 4096，字段名 256，字段值 1024，页脚 2048，作者行 256，字段 25 个，总计 6000；超长以"…"结尾。
- `rinbot/rincore/embeds.py` 不得导入 discord（网页进程也用它）。
- 不新增依赖。`rinbot/cogs/netease.py` 不进仓库，不修改、不提交。
- 直接在 master 上提交（用户的固定要求，不开分支、不开 PR）；提交标题 `feat:` / `fix:` / `style:` / `docs:` 加小写祈使句；不加署名行。不推送，推送前要问用户。
- 测试命令：根目录 `python -m pytest -q`；网页 `cd website && python -m pytest -q tests`；控制台 JS `cd website && node --test tests/*.test.cjs`。每个任务结束时三套都要绿。
- 文案以 spec 为准；本计划里出现的中文文案逐字照抄。

## Review Focus

1. **机器人在频道里没有「嵌入链接」权限时用前缀指令出错**：提示要退回纯文字（`**标题**\n正文`），不能因为发 embed 失败而什么都不显示。测试在 Task 2。
2. **用户写的超长文字**（300 字的奖品名、2000 字的原因、超过 25 个字段）：截断后照常发出，不报 400。测试在 Task 1。
3. **交互已经 defer 之后才出错**（如 `/unban` 先 defer 再失败）：提示走 followup，仍是私密。测试在 Task 2。
4. **私信里或没有任何权限的成员用 `/help`**：只列不需要权限的指令，主人指令永远不列。测试在 Task 8。
5. **在开发服务器里执行 `/sync guild` 或 `/hot_update sync:guild`**：开发指令不能被清掉。测试在 Task 4。

---

### Task 1: 消息模板核心

**Files:**
- Create: `rinbot/rincore/embeds.py`
- Modify: `rinbot/rincore/cases.py`（加 `ACTION_NAMES`）
- Test: `tests/test_embeds.py`

**Interfaces:**
- Produces:
  - `COLORS: dict[str, int]`，键为五种种类名。
  - `build(kind: str, title: str | None = None, description: str | None = None, *, fields: Iterable[tuple] = (), footer: str | None = None, footer_icon: str | None = None, author: str | None = None, author_icon: str | None = None, url: str | None = None, timestamp: datetime | None = None) -> dict`。`fields` 每项是 `(name, value)` 或 `(name, value, inline)`，`inline` 默认 `True`。返回 Discord embed JSON（键：`color`、`title`、`description`、`url`、`fields`、`footer`、`author`、`timestamp`，没有的不出现）。未知 `kind` 抛 `ValueError`。
  - `event_kind(event: str) -> str`；未知事件抛 `KeyError`。
  - `LOG_LEVELS: dict[str, tuple[str, str]]`：`{"error": ("error", "错误"), "warning": ("warning", "警告"), "config": ("success", "配置变更"), "info": ("log", "信息")}`（值为 种类名、中文名）。
  - `giveaway_running(prize: str, winners: int, end_ts: int, *, host_id: int | None = None, role_id: int | None = None) -> dict`
  - `giveaway_ended(prize: str, giveaway_id: int, winner_ids: Sequence[int]) -> dict`
  - `cases.ACTION_NAMES: dict[str, str]`

- [ ] **Step 1: 写失败的测试** `tests/test_embeds.py`，至少包含：

```python
from rincore import cases, embeds

def test_colors():
    assert embeds.COLORS == {"info": 0xEB8BAC, "success": 0x3BA55D, "warning": 0xF0B232, "error": 0xED4245, "log": 0x80848E}

def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        embeds.build("pink", "x")

def test_truncates_each_part():
    e = embeds.build("info", "t" * 300, "d" * 5000, fields=[("n" * 300, "v" * 2000)], footer="f" * 3000, author="a" * 300)
    assert len(e["title"]) == 256 and e["title"].endswith("…")
    assert len(e["description"]) == 4096
    assert len(e["fields"][0]["name"]) == 256 and len(e["fields"][0]["value"]) == 1024
    assert len(e["footer"]["text"]) == 2048 and len(e["author"]["name"]) == 256

def test_keeps_25_fields_and_6000_total():
    e = embeds.build("info", "t", "d" * 4000, fields=[(f"字段{i}", "v" * 1000) for i in range(30)])
    assert len(e["fields"]) == 25
    total = len(e["title"]) + len(e.get("description", "")) + sum(len(f["name"]) + len(f["value"]) for f in e["fields"])
    assert total <= 6000

def test_skips_empty_fields_and_defaults_inline():
    e = embeds.build("log", "t", fields=[("原因", ""), ("成员", None), ("", "x"), ("时长", "1 小时"), ("内容", "长", False)])
    assert e["fields"] == [{"name": "时长", "value": "1 小时", "inline": True}, {"name": "内容", "value": "长", "inline": False}]

def test_timestamp_only_when_given():
    assert "timestamp" not in embeds.build("info", "t")
    assert embeds.build("log", "t", timestamp=datetime(2026, 11, 4, tzinfo=timezone.utc))["timestamp"].startswith("2026-11-04T")
```

再加：
- `test_event_kinds`：spec 第 4.1 节表里每个事件逐个断言，事件键固定为：
  - `success`：`member_join, member_unban, member_timeout_end, channel_create, role_create, unban, unmute`
  - `warning`：`message_edit, nick_change, member_roles, channel_update, role_update, guild_update, member_timeout, warn, mute, automod`
  - `error`：`message_delete, message_bulk_delete, member_kick, member_ban, channel_delete, role_delete, kick, ban, tempban, purge`
  - `log`：`member_leave, voice_join, voice_leave, voice_move, emoji_update, clearwarns`
  - 外加 `event_kind("nope")` 抛 `KeyError`。
- `test_log_levels`：等于上面 Interfaces 里的字典。
- `test_giveaway_running`：`giveaway_running("Nitro", 2, 1800000000, host_id=5, role_id=7)` 的 `color == 0xEB8BAC`，`title == "抽奖：Nitro"`，字段依次为 `("中奖人数", "2 人")`、`("结束时间", "<t:1800000000:R>（<t:1800000000:f>）")`、`("发起人", "<@5>")`、`("参加条件", "需要 <@&7>")`，全部 inline，页脚 `"点下方按钮参加"`；不传 `host_id` / `role_id` 时没有对应字段。
- `test_giveaway_long_prize_still_fits`：300 字的奖品名，标题长度 256 且以"…"结尾。
- `test_giveaway_ended`：`giveaway_ended("Nitro", 3, [1, 2])` 为成功色，标题 `"抽奖结束：Nitro"`，唯一字段 `("中奖者", "<@1>、<@2>", inline False)`，页脚 `"抽奖 #3"`；`giveaway_ended("Nitro", 3, [])` 为日志色，正文 `"没有符合条件的参加者。"`，没有字段，页脚 `"抽奖 #3"`。
- `test_action_names_match_dashboard`：`cases.ACTION_NAMES` 等于 `website/i18n/zh.json` 里 `moderation.action` 整个对象（用 `json.load` 读文件比较，包括 `other`）。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest -q tests/test_embeds.py`
Expected: FAIL，`cannot import name 'embeds'`

- [ ] **Step 3: 实现 `rinbot/rincore/embeds.py` 并给 `cases.py` 加 `ACTION_NAMES`**

截断写法：超长时取前 `limit - 1` 个字再加"…"。先逐项截断，字段只留前 25 个；总字数（标题、正文、字段名和值、页脚、作者行）超过 6000 时先缩短正文，正文缩到空还超就从最后一个字段开始删。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest -q tests/test_embeds.py`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add rinbot/rincore/embeds.py rinbot/rincore/cases.py tests/test_embeds.py
git commit -m "feat: add a shared embed template with five colours"
```

---

### Task 2: 机器人发送辅助和全局 @ 限制

**Files:**
- Create: `rinbot/cogs/_messages.py`
- Modify: `rinbot/main.py:20`（`super().__init__`）
- Test: `tests/test_messages.py`

**Interfaces:**
- Consumes: `rincore.embeds.build`
- Produces（`_messages.py`，cog 里用 `from _messages import ...` 导入）：
  - `embed(kind: str, title: str | None = None, description: str | None = None, **kw) -> discord.Embed`：参数同 `build`，用 `discord.Embed.from_dict` 转换。
  - `class Notice(NamedTuple): kind: str; title: str; description: str | None = None`
  - `async def send(target, embed: discord.Embed, *, private: bool = False, view=None) -> None`
  - `async def send_notice(target, notice: Notice) -> None`：等于 `send(target, embed(notice.kind, notice.title, notice.description), private=True)`。
  - `def block_notice(block, *, component: bool = False) -> Notice | None`：`block` 有 `kind` 和 `text` 两个属性（Task 5 的 `Block`）。

`send` 的规则：
- `target` 有 `response` 属性就当交互：`response.is_done()` 时用 `followup.send`，否则 `response.send_message`；都带 `ephemeral=private`。
- 否则当指令上下文：`ctx.send(embed=..., ephemeral=private)`；`private` 且 `ctx.interaction is None` 时再加 `delete_after=15`。
- 前缀调用、在服务器里、且 `ctx.channel.permissions_for(ctx.me).embed_links` 为假时，改发纯文字 `f"**{title}**\n{description}"`（没有正文就只发标题行），`delete_after` 规则不变。
- `view` 只在不为 `None` 时传。
- 发送抛 `discord.HTTPException` 时吞掉，不往外抛。

`block_notice` 的文案：
- `kind == "maintenance"`：`Notice("warning", "小凛正在维护", block.text or "暂时用不了，请稍后再试。")`
- `kind == "disabled"`：`Notice("warning", "这条指令已停用", "机器人主人暂时关闭了这条指令。")`
- `kind == "blacklist"`：指令时返回 `None`；`component=True` 时返回 `Notice("error", "你现在不能使用这个功能")`

- [ ] **Step 1: 写失败的测试** `tests/test_messages.py`，用 `SimpleNamespace` 和记录调用的假对象，至少包含：
  - `test_embed_converts_template`：`embed("success", "完成", fields=[("成员", "<@1>")])` 是 `discord.Embed`，`color.value == 0x3BA55D`，`fields[0].name == "成员"`。
  - `test_private_slash_reply_is_ephemeral`：`ctx.interaction` 非空时，`ctx.send` 收到 `ephemeral=True`，且没有 `delete_after`。
  - `test_private_prefix_reply_deletes_after_15s`：`ctx.interaction is None`，`delete_after == 15`。
  - `test_prefix_without_embed_links_falls_back_to_text`（Review Focus 1）：`permissions_for(...).embed_links` 为假时，`ctx.send` 第一个参数是 `"**小凛缺少「嵌入链接」权限**\n请服务器管理员…"`，且不带 `embed`。
  - `test_deferred_interaction_uses_followup`（Review Focus 3）：`response.is_done()` 为真时，调用的是 `followup.send(..., ephemeral=True)`，`response.send_message` 没被调用。
  - `test_view_omitted_when_none`：`send(..., view=None)` 时假对象收到的关键字参数里没有 `view`。
  - `test_send_swallows_http_errors`：`ctx.send` 抛 `discord.HTTPException(SimpleNamespace(status=400, reason="x"), "x")` 时 `send` 正常返回。
  - `test_block_notices`：上面三种 `kind` 以及 `component=True` 时的四个结果；维护说明为空串时正文是 `"暂时用不了，请稍后再试。"`。
  - `test_bot_limits_mentions`：用 `ast` 解析 `rinbot/main.py`，找到 `HybridBot.__init__` 里的 `super().__init__(...)`，其 `allowed_mentions` 关键字参数源码等于 `discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=False)`（用 `ast.unparse` 比较）。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest -q tests/test_messages.py`
Expected: FAIL，`No module named '_messages'`

- [ ] **Step 3: 实现 `_messages.py`，并在 `main.py` 的 `super().__init__(...)` 里加上 `allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=False)`**

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest -q tests/test_messages.py`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add rinbot/cogs/_messages.py rinbot/main.py tests/test_messages.py
git commit -m "feat: send bot notices privately and stop role and everyone pings"
```

---

### Task 3: 权限装饰器和指令可见性

**Files:**
- Create: `rinbot/cogs/_perms.py`
- Modify: `rinbot/cogs/{automod,commandtoggle,giveaway,moderation,reactionroles,serverlog,welcome}.py`（56 处 `@commands.has_permissions`）、`rinbot/cogs/dev.py`（6 处 `is_owner`）、`rinbot/cogs/general.py`（3 处 `is_owner`）、`rinbot/cogs/health.py`（`_command_snapshot`）
- Test: `tests/test_perms.py`

**Interfaces:**
- Produces（`_perms.py`）：
  - `DEV_GUILD_ID: int`：`from config import DEV_GUILD_ID`，导入失败时为 `0`（写法同 `botlog.py`）。
  - `require(**perms) -> Callable`：对函数依次套 `commands.has_permissions(**perms)` 和 `app_commands.default_permissions(**perms)`。
  - `owner_only() -> Callable`：套 `commands.is_owner()`；调用时读模块变量 `DEV_GUILD_ID`，非 0 时套 `app_commands.guilds(DEV_GUILD_ID)`，为 0 时套 `app_commands.guilds()`（空列表，discord.py 不会注册斜杠版）；再设 `func.__rinbot_owner_only__ = True`。
  - `is_owner_only(command) -> bool`：读 `command.callback` 上的标记。
  - `required_permissions(command) -> discord.Permissions | None`：取 `(command.root_parent or command).app_command.default_permissions`；没有 `app_command` 时返回 `None`。
- 两个装饰器都写在 `@commands.hybrid_command(...)` / `@xxx.command(...)` 的下面（紧贴函数的一侧），位置和现在的 `has_permissions` 一样。

- [ ] **Step 1: 写失败的测试** `tests/test_perms.py`：
  - `test_require_sets_check_and_default_permissions`：在测试里定义一个 `@commands.hybrid_command(name="t")` + `@require(kick_members=True)` 的函数，断言 `cmd.app_command.default_permissions == discord.Permissions(kick_members=True)` 且 `len(cmd.checks) == 1`。
  - `test_owner_only_registers_in_dev_guild`：`monkeypatch.setattr(_perms, "DEV_GUILD_ID", 123)` 后新定义的指令 `cmd.app_command._guild_ids == [123]`，`is_owner_only(cmd)` 为真。
  - `test_owner_only_without_dev_guild_has_no_slash`：`DEV_GUILD_ID = 0` 时 `cmd.app_command._guild_ids == []`；再建一个 `commands.Bot(command_prefix="r!", intents=discord.Intents.none())`，`bot.add_command(cmd)` 后 `bot.tree.get_commands() == []`。
  - `test_no_bare_permission_checks`：AST 扫描 `rinbot/cogs/*.py`（跳过 `netease.py`、`_perms.py`），任何 `Attribute.attr` 为 `has_permissions` 或 `is_owner` 的节点都算失败。
  - `test_groups_cover_subcommand_permissions`：AST 找出每个 `hybrid_group` 函数和挂在它下面的 `@<组名>.command` 子指令；只要有子指令用了 `require(...)`，组函数自己也必须有 `require(...)`，且组的权限关键字集合包含每个子指令的权限关键字。
  - `test_owner_commands_use_owner_only`：AST 断言 `hot_update, load, unload, extensions, sync, eval, setstatus, resetstatus, setbio` 这 9 个指令的函数都带 `owner_only()` 装饰器。
  - `test_health_snapshot_skips_owner_commands`：用 `SimpleNamespace(commands=[...])` 构造一个 bot，里面一条普通指令、一条 `owner_only()` 指令，`Health(bot)._command_snapshot()` 只返回普通那条。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest -q tests/test_perms.py`
Expected: FAIL，`No module named '_perms'`

- [ ] **Step 3: 实现 `_perms.py`，再改各 cog**
  - 56 处 `@commands.has_permissions(x=True)` 换成 `@require(x=True)`，各文件 `from _perms import require`。
  - `/giveaway` 组函数 `giveaway_group` 加 `@require(manage_guild=True)`（放在 `@commands.guild_only()` 下面）。`/automod`、`/serverlog` 组上原有的检查已经在第一步里换成 `require`。
  - `dev.py` 的 6 处、`general.py` 的 3 处 `@commands.is_owner()` 换成 `@owner_only()`。
  - `health.py` 的 `_command_snapshot` 跳过 `is_owner_only(command)` 为真的指令。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest -q`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
git add rinbot/cogs tests/test_perms.py
git commit -m "feat: hide admin commands by default and keep owner commands in the dev server"
```

---

### Task 4: 同步不再清掉开发指令

**Files:**
- Modify: `rinbot/cogs/dev.py`（`hot_update` 的同步部分、`sync_cmd`）
- Test: `tests/test_dev_sync.py`

**Interfaces:**
- Consumes: `_perms.DEV_GUILD_ID`
- Produces: `dev.py` 模块级 `async def sync_commands(tree, scope: str, guild, dev_guild_id: int) -> str`，`scope` 为 `"global"` / `"guild"` / `"clear_guild"`；`guild` 是当前服务器（可为 `None`），返回给主人看的一行结果。`/sync` 和 `/hot_update`（`sync` 参数为 `guild` / `global` 时）都调用它，传 `_perms.DEV_GUILD_ID`。

调用顺序：
- `global`：`await tree.sync()`；`dev_guild_id` 非 0 时再 `await tree.sync(guild=discord.Object(dev_guild_id))`。
- `guild`：当前服务器不是开发服务器时先 `tree.clear_commands(guild=guild)`、`await tree.sync(guild=guild)`；然后同 `global`。
- `clear_guild`：当前服务器是开发服务器时什么都不调用，返回 `"开发服务器的指令不能清掉，改用 global。"`；否则 `clear_commands` + `sync(guild=guild)`，返回 `"已清除本服务器的斜杠指令缓存。"`。
- `global` 和 `guild` 返回 `f"已同步 {n} 个全局指令"`，有开发服务器时接 `f"，开发服务器 {m} 个"`；`guild` 在非开发服务器时前面加 `"已清理本服务器的旧指令，"`。

- [ ] **Step 1: 写失败的测试** `tests/test_dev_sync.py`：假 tree 记录每次调用 `("clear", guild_id)` / `("sync", guild_id 或 None)`，`sync` 返回长度为 3（全局）或 2（开发服务器）的列表。
  - `test_global_syncs_dev_guild_too`：调用记录为 `[("sync", None), ("sync", 9)]`，返回 `"已同步 3 个全局指令，开发服务器 2 个"`。
  - `test_guild_in_dev_server_keeps_dev_commands`（Review Focus 5）：`guild.id == 9 == dev_guild_id`，记录里没有 `("clear", 9)`。
  - `test_guild_elsewhere_clears_that_guild_first`：记录为 `[("clear", 4), ("sync", 4), ("sync", None), ("sync", 9)]`。
  - `test_clear_guild_refused_in_dev_server`：记录为空，返回拒绝文案。
  - `test_no_dev_guild`：`dev_guild_id = 0` 时 `global` 只有 `[("sync", None)]`，返回 `"已同步 3 个全局指令"`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest -q tests/test_dev_sync.py`
Expected: FAIL，`cannot import name 'sync_commands'`

- [ ] **Step 3: 实现 `sync_commands`，`sync_cmd` 和 `hot_update` 改为调用它**（结果行照旧放进各自的回复里）

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add rinbot/cogs/dev.py tests/test_dev_sync.py
git commit -m "fix: sync the dev server without clearing its commands"
```

---

### Task 5: 报错和拦截提示

**Files:**
- Modify: `rinbot/cogs/errors.py`（整体重写 `_friendly` 和两个处理函数）、`rinbot/cogs/globalsettings.py:21-35, 103-125`、`rinbot/cogs/_botlog_helper.py:33-50`、`rinbot/cogs/dev.py`（删掉 `cog_command_error`）
- Test: `tests/test_errors_friendly.py`（重写）、`tests/test_error_id.py`（check_component 部分）、`tests/test_globalsettings_logic.py`

**Interfaces:**
- Consumes: `_messages.Notice`、`send_notice`、`block_notice`
- Produces:
  - `errors.PERMISSION_NAMES: dict[str, str]`；`errors.permission_list(perms: Iterable[str]) -> str`，例：`["manage_messages", "embed_links"]` → `"「管理消息」「嵌入链接」"`；表里没有的权限把下划线换成空格。
  - `errors.usage(command, *, slash: bool) -> str`，例：`"/kick <member> [reason]"`、`"r!kick <member> [reason]"`。指令对象有 `clean_params` 就用它（`param.required`），否则用 `parameters`（`p.required`）。不显示默认值。
  - `errors.UNEXPECTED: object`；`errors.notice_for(error, *, command=None, slash: bool = False, now: float | None = None) -> Notice | None | object`；`errors.unexpected_notice(error_id: str) -> Notice`。
  - `globalsettings.Block(NamedTuple): kind: str; text: str = ""`；`decide_block(...)` 和 `blocked_reason(...)` 改为返回 `Block | None`：黑名单 `Block("blacklist")`，维护 `Block("maintenance", maint_msg)`，停用 `Block("disabled")`。删掉 `DEFAULT_MAINT_MSG`、`DISABLED_MSG`。
  - `check_component(bot, interaction) -> bool` 签名不变（`music.py`、`giveaway.py`、`reactionroles.py` 和本地的 `netease.py` 都在用）。

`PERMISSION_NAMES` 至少包含：`administrator 管理员, view_channel 查看频道, manage_channels 管理频道, manage_roles 管理身份组, manage_guild 管理服务器, kick_members 踢出成员, ban_members 封禁成员, moderate_members 禁言成员, manage_messages 管理消息, manage_nicknames 管理昵称, send_messages 发送消息, embed_links 嵌入链接, attach_files 附加文件, read_message_history 阅读消息历史记录, add_reactions 添加反应, use_external_emojis 使用外部表情符号, mention_everyone 提及 @everyone、@here 和所有身份组, connect 连接, speak 说话`。实现时对照 Discord 简体中文客户端逐个核对，不一致就以客户端为准并在 ledger 里记一条 Ruling。

`notice_for` 的匹配顺序（`commands.HybridCommandError` 先取 `.original`）和文案，逐字照抄：

| 错误 | Notice |
| --- | --- |
| `CommandNotFound` | `None` |
| `MissingPermissions`（commands 和 app_commands） | `("error", "你没有权限使用这条指令", f"需要{permission_list(...)}权限。")` |
| `BotMissingPermissions`（两种） | `("error", f"小凛缺少{permission_list(...)}权限", "请服务器管理员在 服务器设置 → 身份组 里给小凛打开这个权限，再试一次。")` |
| `MissingRequiredArgument` | `("error", f"缺少参数「{error.param.name}」", f"用法：`{usage}`")`；没有 `command` 时正文为 `None` |
| `CommandOnCooldown`（两种） | `("warning", "操作太快了", f"<t:{math.ceil(now + error.retry_after)}:R>可以再用。")`，`now` 默认 `time.time()` |
| `NoPrivateMessage`（两种） | `("error", "这条指令只能在服务器里用")` |
| `MemberNotFound` | `("error", "找不到这个成员", "检查一下有没有打错，或者直接 @ 对方。")` |
| `UserNotFound` | `("error", "找不到这个用户", "检查一下有没有打错，或者直接 @ 对方。")` |
| `RoleNotFound` | `("error", "找不到这个身份组", "检查一下名字有没有打错，或者直接 @ 这个身份组。")` |
| `ChannelNotFound` | `("error", "找不到这个频道", "检查一下名字有没有打错，或者直接 # 这个频道。")` |
| 其余 `BadArgument` / `UserInputError` | `("error", "参数格式不对", f"用法：`{usage}`")`；没有 `command` 时正文为 `None` |
| `NotOwner` | `("error", "只有机器人主人能用这条指令")` |
| 其余 `CheckFailure`（两种） | `None` |
| 其他 | `UNEXPECTED` |

`unexpected_notice(id)` = `("error", "这条指令没有执行成功", f"已自动记录，错误编号 `{id}`。稍后再试；一直出错的话，反馈时带上这个编号。")`。

处理函数：`on_command_error` 调 `notice_for(error, command=ctx.command, slash=ctx.interaction is not None)`；`_on_app_error` 调 `notice_for(error, command=interaction.command, slash=True)`；`UNEXPECTED` 时照旧 `_report` 拿编号再发 `unexpected_notice`；都用 `send_notice` 发出。全局检查 `_global_check` 和 `check_component` 改用 `block_notice(block)` / `block_notice(block, component=True)` + `send_notice`，返回值逻辑不变。

- [ ] **Step 1: 改写测试**
  - `tests/test_errors_friendly.py`：表里每一行各一个测试，断言 `notice_for(...)` 返回的三元组；外加 `test_permission_list_joins_and_falls_back`（`["manage_messages", "embed_links", "create_events"]` → `"「管理消息」「嵌入链接」「create events」"`）、`test_usage_slash_and_prefix`（用一个测试里定义的 `hybrid_command`，参数 `member: discord.Member, *, reason: str = "x"`，得到 `"/kick <member> [reason]"` 和 `"r!kick <member> [reason]"`）、`test_cooldown_uses_discord_timestamp`（`now=1000.0`、`retry_after=2.5` → 正文 `"<t:1003:R>可以再用。"`）、`test_hybrid_error_is_unwrapped`、`test_unexpected_notice_text`。
  - `tests/test_globalsettings_logic.py`：期望值改成 `Block(...)`，维护说明为空时 `Block("maintenance", "")`。
  - `tests/test_error_id.py` 的 check_component 部分：假的 `blocked_reason` 改为返回 `Block`；假的 `send_message` / `followup.send` 改为接收 `embed=`；断言 embed 的标题（黑名单 `"你现在不能使用这个功能"`，维护 `"小凛正在维护"`）和 `ephemeral=True`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest -q tests/test_errors_friendly.py tests/test_globalsettings_logic.py tests/test_error_id.py`
Expected: FAIL（`notice_for`、`Block` 不存在）

- [ ] **Step 3: 实现**，删掉 `dev.py` 的 `cog_command_error`（`NotOwner` 交给 `errors.py`），删掉不再用的 `_friendly`

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add rinbot/cogs tests
git commit -m "feat: explain errors and blocks in plain chinese with private notices"
```

---

### Task 6: 日志类消息套模板

**Files:**
- Modify: `rinbot/cogs/moderation.py`（`_log_case`、4 种处罚私信、`warns`、`modlog`、`warn_config` 的 embed）、`rinbot/cogs/serverlog.py`（23 种事件和状态面板）、`rinbot/cogs/automod.py`（5 种记录、配置面板、忽略列表）、`rinbot/cogs/botlog.py`（`log`，删掉 `LEVEL_META` 改用 `embeds.LOG_LEVELS`）
- Test: `tests/test_embed_style.py`

**Interfaces:**
- Consumes: `_messages.embed`、`rincore.embeds.event_kind`、`rincore.embeds.LOG_LEVELS`、`rincore.cases.ACTION_NAMES`

规则（spec 第 5.1 节，各文件逐处套用）：
- 所有 `discord.Embed(...)` 换成 `embed(kind, title, description, fields=[...], footer=..., author=..., timestamp=...)`；原来的 `add_field` / `set_footer` / `set_author` 并进参数；`set_thumbnail`、`set_image` 和 `serverlog._send` 里给 `embed.timestamp` 赋值保持不变。
- 管理日志：`embed(event_kind(action), f"案件 #{case_id}：{ACTION_NAMES[action]}", fields=[("成员", f"{user.mention}（{user.id}）"), ("管理员", mod.mention), ("时长", duration), ("原因", reason, False)], timestamp=utcnow)`，删掉 `action_emoji` 表。
- 处罚私信：标题 `f"你已被踢出 {guild}"`、`f"你已被封禁：{guild}"`、`f"你已被临时封禁：{guild}"`、`f"你在 {guild} 收到一次警告"`；种类 `event_kind("kick" / "ban" / "tempban" / "warn")`；字段 `原因`（不并排）、`时长`、`管理员`（显示 `str(ctx.author)`）。
- 审计日志：每个事件用对应的 `event_kind` 键（见 Task 1），标题只去掉 emoji；状态面板标题 `"审计日志设置"`，信息色（不再按开关状态变色）。
- 自动审核记录：种类 `event_kind("automod")`，标题 `"自动审核：刷屏"` / `"自动审核：重复消息"` / `"自动审核：违禁词"` / `"自动审核：链接"` / `"自动审核：大写"`；正文里的 `**用户:** …` 等标签行改成字段 `成员`、`频道`、`处理` 或 `内容`；保留时间戳。配置面板 `"自动审核设置"`、忽略列表 `"自动审核忽略列表"`，信息色。
- 系统日志：`kind, label = LOG_LEVELS.get(level, LOG_LEVELS["info"])`；标题去 emoji；作者行 `f"系统日志 · {label}"`；页脚 `f"Guild ID: {guild_id}"` 保留。
- 警告记录 `f"{member.display_name} 的警告记录"`、管理日志查询 `"管理日志"`（有成员时 `f"管理日志：{member}"`）、警告处罚配置 `"警告自动处罚"`，信息色。

- [ ] **Step 1: 写失败的测试** `tests/test_embed_style.py`：

```python
MIGRATED = ["rinbot/cogs/moderation.py", "rinbot/cogs/serverlog.py", "rinbot/cogs/automod.py", "rinbot/cogs/botlog.py"]
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿️]")
```

对 `MIGRATED` 里每个文件参数化三个测试：
  - `test_no_raw_colours`：源码里没有 `discord.Color.`、`discord.Colour.`，也没有匹配 `colou?r\s*=\s*0x` 或 `"colou?r":\s*0x` 的文字。
  - `test_no_direct_embed_building`：AST 里没有调用对象正好是 `discord.Embed` 的调用（`discord.Embed.from_dict(...)` 不算），也没有 `add_field` / `set_footer` / `set_author` 的属性调用。
  - `test_titles_and_field_names_have_no_emoji`：AST 里每个 `embed(...)` 调用，第二个位置参数（或 `title=`）是字符串常量或 f-string 时，其常量部分不匹配 `EMOJI`；`fields=` 是列表字面量时，每个元组第一个元素的常量部分同样不匹配。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest -q tests/test_embed_style.py`
Expected: FAIL（4 个文件都有原始颜色）

- [ ] **Step 3: 按上面的规则改 4 个文件**

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add rinbot/cogs tests/test_embed_style.py
git commit -m "style: put moderation, audit and system logs on the shared template"
```

---

### Task 7: 其余机器人消息套模板，抽奖共用一个生成函数

**Files:**
- Modify: `rinbot/cogs/giveaway.py`、`music.py`、`reactionroles.py`、`welcome.py`、`commandtoggle.py`、`leveling.py`、`globalsettings.py`（公告）、`dev.py`（热更新、扩展状态、eval）
- Test: `tests/test_embed_style.py`（扩大范围）、`tests/test_giveaway_embeds.py`

**Interfaces:**
- Consumes: `_messages.embed`、`rincore.embeds.giveaway_running`、`rincore.embeds.giveaway_ended`

逐处套用 spec 第 5.1 节的表，要点：
- 抽奖：`/giveaway start` 用 `discord.Embed.from_dict(giveaway_running(prize, winners, end_ts, host_id=ctx.author.id))`；`_end_giveaway` 用 `giveaway_ended(prize, giveaway_id, winners)`；列表 `"进行中的抽奖"`，信息色。
- 音乐：`_now_playing_embed(song, state, status: str | None = None)`：作者行为 `status or "正在播放 ♪"`（图标为机器人头像）；字段 `时长`、`音量`、`循环`，`status` 为空时再加 `接下来`（不并排）；页脚 `f"由 {song.requester.display_name} 点歌"`，图标为点歌人头像。`_close_player` 改为传 `status`，删掉按字段名删"⏭ 接下来"的循环。"已加入队列" / "歌单已加入队列"成功色；搜索结果 `f"“{query[:100]}” 的搜索结果"`、`"播放队列"`、`"已保存的队列"`，信息色。
- 身份组面板：标题直接用 `title`（不加 🏷），信息色；面板列表 `"身份组面板"`。
- 迎新：欢迎 `info`（作者行为欢迎标题，带图标）；道别 `log`，页脚 `f"现在有 {member.guild.member_count} 位成员"`；设置面板 `"迎新和道别设置"`。
- `"已停用的指令"`、`f"{ctx.guild.name} 等级排行榜"`、公告 `"机器人主人的公告"`（无页脚）：信息色。
- 热更新：全部成功时 `("success", "热更新完成")`，有失败时 `("warning", "热更新完成，有模块失败")`；扩展状态 `"扩展状态"`；eval：`("success", "执行完成")` / `("error", "执行出错")`，字段名 `stdout`、`返回值`、`错误`，不再加时间戳。

- [ ] **Step 1: 写失败的测试**
  - `tests/test_embed_style.py`：把 `MIGRATED` 换成 `rinbot/cogs/*.py` 里除 `netease.py`、`_messages.py`、`general.py`、`help.py` 之外的全部文件（用 `glob` 生成，以后新加的 cog 自动受约束）。`general.py` 和 `help.py` 在 Task 8 里改，那时再去掉这两个例外。
  - `tests/test_giveaway_embeds.py`：AST 断言 `giveaway.py` 里调用了 `giveaway_running` 和 `giveaway_ended`，并且源码里不再出现 `"中奖名额"` 和 `"抽奖活动！"`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest -q tests/test_embed_style.py tests/test_giveaway_embeds.py`
Expected: FAIL（未改的文件仍有原始颜色）

- [ ] **Step 3: 按上面的要点改 8 个文件**

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add rinbot/cogs tests
git commit -m "style: put giveaways, music, panels and the remaining bot messages on the shared template"
```

---

### Task 8: `/status` 和 `/help`

**Files:**
- Modify: `rinbot/cogs/general.py`（`/status`、`/avatar`、`/setbio`）、`rinbot/cogs/help.py`、`rinbot/requirements.txt`（删 `psutil`）
- Test: `tests/test_status_help.py`、`tests/test_embed_style.py`（去掉 Task 7 留下的两个例外）

**Interfaces:**
- Consumes: `_messages.embed`、`_messages.send_notice`、`_messages.Notice`、`_perms.is_owner_only`、`_perms.required_permissions`
- Produces（`help.py`）：`visible(command, perms: discord.Permissions | None) -> bool`：主人指令为 `False`；`required_permissions(command)` 为 `None` 时为 `True`；`perms` 为 `None`（私信）且需要权限时为 `False`；否则为 `perms >= required`。`_collect_commands(cog, bot, guild_id=None, perms=None)` 多一个 `perms` 参数并用 `visible` 过滤。

`/status`：`embed("info", "小凛的运行状态", fields=[("延迟", f"{round(self.bot.latency * 1000)} 毫秒"), ("上次启动", f"<t:{int(self.bot.start_time)}:R>"), ("服务器", f"{len(self.bot.guilds)} 个")])`；指令说明改成 `"查看小凛的运行状态"`；删掉 `psutil`、`platform` 导入和页脚。

`/avatar`：信息色，标题 `f"{target.name} 的头像"`，按钮文字 `"查看原图"`，按钮的 emoji 去掉。`/setbio`：成功色 `"简介已更新"`。

`/help`：
- 斜杠调用 `ctx.send(embed=..., view=..., ephemeral=True)`；前缀调用照旧公开发送。
- `HelpView(bot, guild_id, perms, owner_id)`；`interaction_check` 在 `interaction.user.id != owner_id` 时用 `send_notice` 发 `Notice("warning", f"这个菜单是 {发起人显示名} 打开的", "你可以自己输入 /help。")` 并返回 `False`。
- `perms` 取 `ctx.author.guild_permissions`（私信时 `None`）。`HelpDropdown` 的选项和回调、`_build_home_embed` 都传同一个 `perms`，过滤后没有指令的模块不出现在菜单和首页里（现有的空模块判断照旧生效）。
- 首页：标题 `"小凛 RinBot 指令中心"`，正文保留颜文字；模块列表每行 `f"**{label}** — {desc}"`（去掉每行的 emoji 和斜体），字段名 `"已加载的模块"`；页脚 `"菜单 2 分钟后失效"`。模块页标题为 `label`，页脚 `f"共 {n} 个指令"`。找不到模块时 `send_notice` 发 `Notice("error", "找不到这个模块")`。下拉选项的 emoji 保留。

- [ ] **Step 1: 写失败的测试** `tests/test_status_help.py`：
  - `test_status_fields`：用假 bot（`latency=0.041`、`start_time=1790000000`、两个 guild）和记录 `send` 的假 ctx 调 `General.status.callback(cog, ctx)`，断言标题、颜色 `0xEB8BAC`，字段为 `[("延迟", "41 毫秒"), ("上次启动", "<t:1790000000:R>"), ("服务器", "2 个")]`，没有页脚。
  - `test_status_has_no_host_info`：`general.py` 源码里没有 `psutil`、`platform`；`requirements.txt` 里没有 `psutil`。
  - `test_member_sees_no_admin_commands`（Review Focus 4）：`visible(kick 指令, discord.Permissions.none())` 为 `False`，`visible(roll 指令, discord.Permissions.none())` 为 `True`。
  - `test_dm_shows_only_open_commands`：`perms=None` 时 kick 为 `False`、roll 为 `True`。
  - `test_manager_sees_giveaway_subcommands`：`discord.Permissions(manage_guild=True)` 时 `/giveaway list` 子指令为 `True`。
  - `test_owner_commands_never_visible`：`discord.Permissions.all()` 时 `setstatus` 为 `False`。
  - `test_menu_rejects_other_users`（async 测试，`discord.ui.View` 需要运行中的事件循环）：`HelpView(..., owner_id=1)` 的 `interaction_check` 对 `user.id == 2` 的假交互返回 `False`，并私密发出上面的提示。
  - `tests/test_embed_style.py`：`MIGRATED` 去掉 `general.py`、`help.py` 两个例外。
  - 测试用的指令对象从真实 cog 模块里取：`moderation.Moderation.kick`、`general.General.roll`、`general.General.setstatus`、`giveaway.Giveaway.giveaway_group` 的 `list` 子指令。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest -q tests/test_status_help.py`
Expected: FAIL

- [ ] **Step 3: 实现**

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add rinbot/cogs/general.py rinbot/cogs/help.py rinbot/requirements.txt tests/test_status_help.py tests/test_embed_style.py
git commit -m "feat: hide host details in /status and filter /help by permission"
```

---

### Task 9: 网页发出的消息和控制台预览

**Files:**
- Modify: `website/routes.py`（`_AUDIT_LEVEL_META` 和 `_botlog_send`、系统日志测试、审计日志测试、`api_rr_send`、抽奖创建）、`website/static/js/message-preview.js`、`website/static/css/console.css:528`、`website/templates/*.html`（6 个模板的 `?v=20261103c` 改为 `?v=20261104a`）
- Test: `tests/test_embed_style.py`（加入 `website/routes.py`）、`tests/test_website_embeds.py`、`website/tests/test_dashboard_templates.py`

**Interfaces:**
- Consumes: `rincore.embeds.build`、`LOG_LEVELS`、`giveaway_running`

要点：
- 删掉 `_AUDIT_LEVEL_META`；`_botlog_send` 用 `kind, label = LOG_LEVELS.get(level, LOG_LEVELS["info"])` 和 `build(kind, title, desc, fields=..., author=f"系统日志 · {label}", footer=f"网页控制台 · Guild ID: {guild_id}", timestamp=datetime.now(timezone.utc))`。
- 两种测试消息：`build("success", "测试消息", "看到这条消息，说明日志频道设置正确。", footer=f"由网页控制台触发 · Guild ID: {g}")`。
- 身份组面板：默认标题 `"身份组选择"`；`build("info", title, desc_with_hint)`。
- 抽奖：先算出 `host_id`（登录用户的 ID，取不到为 0），再用 `giveaway_running(prize, winners_count, end_ts, host_id=host_id or None, role_id=restrict_role or None)`，删掉手拼的 `embed_desc` 和"🔒 限制身份组"行。
- 预览：`message-preview.js` 里身份组面板默认标题改成 `'身份组选择'`，去掉 `preview-embed--roles` 类；`console.css` 删掉 `.preview-embed--roles` 这条规则。

- [ ] **Step 1: 写失败的测试**
  - `tests/test_embed_style.py`：新增 `WEB = ["website/routes.py"]`，`test_no_raw_colours` 参数化在 `MIGRATED + WEB` 上；另外两个 AST 测试仍只跑 `MIGRATED`。
  - `tests/test_website_embeds.py`：AST 或源码断言 `routes.py` 不再有 `_AUDIT_LEVEL_META`、`"🏷 身份组选择"`、`"中奖名额"`，并且调用了 `giveaway_running`。
  - `website/tests/test_dashboard_templates.py`：断言 `console.css` 里没有 `preview-embed--roles`，`message-preview.js` 里没有 `'🏷 身份组选择'`；把第 246 行附近的 `js/theme.js?v=20261103c` 改为 `?v=20261104a`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest -q tests/test_embed_style.py tests/test_website_embeds.py; cd website && python -m pytest -q tests/test_dashboard_templates.py`
Expected: FAIL

- [ ] **Step 3: 实现**

- [ ] **Step 4: 运行三套测试，确认全部通过**

Run: `python -m pytest -q; cd website && python -m pytest -q tests && node --test tests/*.test.cjs`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add website tests
git commit -m "style: send dashboard logs, role panels and giveaways with the shared template"
```

---

## 收尾（不是任务，执行完全部任务后）

- 跑一遍三套测试，记下通过数。
- 本计划不推送。推送前按用户的固定要求列出全部待推送提交的完整标题和说明，等用户确认。
- 推送并部署后，提醒用户在开发服务器发 `r!sync global`，再按 spec 第 1 节的成功标准检查。
