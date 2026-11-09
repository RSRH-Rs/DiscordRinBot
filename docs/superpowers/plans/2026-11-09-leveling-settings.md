# 等级设置 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给等级系统加上每个服务器独立的总开关、升级提示去向和等级奖励，并在控制台的等级页提供设置界面。

**Architecture:** 配置存在 `leveling.db` 的新表 `level_config`，每个服务器一行，奖励是同一行里的 JSON。机器人启动时读入内存，网页保存后经 `change_watcher` 只重读这一个服务器。网页端用 `/api/guild/<gid>/leveling` 读写，等级页分“设置”“排行榜”两个标签。

**Tech Stack:** discord.py、aiosqlite、Quart、Jinja2、原生 JS；测试用 pytest（`asyncio_mode = auto`）、unittest、Node test runner（`vm` + 手写 DOM 桩）。

**Spec:** `docs/superpowers/specs/2026-11-09-leveling-settings-design.md`

## Global Constraints

- 没有配置行的服务器：开启、提示发在原频道、无奖励，行为和现在完全一样。
- 升级提示原文不变：`🎉 恭喜 **{message.author.mention}**！你升级到了 **Level {new_level}**！✨`。
- 奖励最多 20 条，等级 1 到 999，等级和身份组都不重复。`role_id` 在存储和接口里都是字符串。
- `notify_mode` 只有 `here`、`channel`、`off`；不是 `channel` 时 `notify_channel` 写 0。
- 配色和控件沿用现有令牌与宏。`console.css`：字号只能是 `{12,13,14,16,22}`；`padding`/`margin`/`gap` 只能是 `{0,1,4,8,12,16,24,32,40,48}`；圆角只能用 `0,4px,8px,12px,999px,50%,var(--radius)`；不用 `!important`；每个 `var(--x)` 都在 `:root` 定义；`transition` 不写 `all`。
- 改过的前端文件把缓存版本从 `?v=20261108b` 提到 `?v=20261108c`（现有测试要求版本串包含 `20261108`）。`console.css` 的版本写在 `_console_base.html`、`error.html`、`login_gate.html` 三处。
- 控制台文案全部写进 `website/i18n/zh.json`。接口错误信息沿用 `routes.py` 里的中文字面量。
- 375px 宽没有横向滚动，触控目标不小于 44px。
- 提交到本地 master，只 `git add` 本任务的文件，标题用 `feat:/fix:/style:/docs:/test:/chore:` 加小写祈使句，不推送，`rinbot/cogs/netease.py` 永远不提交。
- 测试命令：根目录 `python -m pytest -q`；`cd website && python -m pytest -q tests`；`cd website && node --test tests/*.cjs`。

## Review Focus

- 总开关关闭时，一条已删除的身份组或频道不能让管理员关不掉等级系统。测试在 Task 3（`test_post_disabled_skips_discord_checks`）和 Task 6（`off skips lost resources`）。
- 输入框失去焦点时重新排序，如果此刻鼠标正按在另一行的移除按钮上，行不能在按下和松开之间移动，否则点错行。测试在 Task 6（`sort waits for the pointer`）。
- 打开页面时读不到 Discord，已存的身份组不能被当成已删除，也不能在保存时丢失。测试在 Task 6（`discord down keeps saved roles`）。
- 多行奖励的输入框如果没有各自的 `name`，草稿系统按 className 取键，“设置”标签上的未保存圆点会一直亮着。测试在 Task 6（`rows get positional names`）。
- 消息作者不是 `discord.Member`（如 webhook）时，发奖励不能抛异常。测试在 Task 2（`test_rewards_skip_non_member_author`）。

---

### Task 1: 机器人端的配置、开关和提示去向

**Files:**
- Modify: `rinbot/cogs/leveling.py`、`rinbot/rincore/sync.py:14-24`、`rinbot/rincore/guild_cleanup.py:38-52`
- Test: `tests/test_leveling_logic.py`、`tests/test_guild_cleanup.py`、`tests/test_sync.py`

**Interfaces:**
- Produces（Task 2 使用）：
  - `parse_rewards(raw) -> list[tuple[int, int]]`：`(等级, 身份组 id)`；任何非法内容打印日志并返回 `[]`。
  - `Leveling.get_config(guild_id) -> dict`：键为 `enabled: bool`、`notify_mode: str`、`notify_channel: int`、`rewards: list[tuple[int, int]]`；未配置时返回默认值的新副本。
  - `Leveling.reload_guild(guild_id: int) -> None`。
  - `Leveling._send_level_notice(message, new_level: int, config: dict) -> None`。
  - `on_message` 拆成：DB 块结束后再发提示；用局部变量 `leveled_to: int | None` 和 `current_level: int` 把结果带出 DB 块。

- [ ] **Step 1: 写失败的测试**

`tests/test_leveling_logic.py` 增加夹具：`monkeypatch.setattr(leveling, "DB_PATH", str(tmp_path / "leveling.db"))`，`cog = Leveling(SimpleNamespace(change_watcher=None))`，`await cog.cog_load()`。假消息用 `SimpleNamespace`，`channel.send`、`guild.get_channel` 返回的频道 `.send` 都是 `AsyncMock`。辅助函数 `save_config(gid, enabled=1, mode="here", channel=0, rewards="[]")` 直接写 `level_config` 再 `await cog.reload_guild(gid)`。经验触发升级：预先把 `users.xp` 写成 `cog.get_total_xp_for_level(1) - 1`。

```python
def test_parse_rewards_reads_pairs():
    assert parse_rewards('[{"level": 5, "role_id": "42"}]') == [(5, 42)]

@pytest.mark.parametrize("raw", ["", None, "not json", "{}", '[{"level": "x"}]', '[{"role_id": "1"}]', "[1]"])
def test_parse_rewards_rejects_bad_content(raw):
    assert parse_rewards(raw) == []

async def test_unconfigured_guild_keeps_current_behaviour(cog, message): ...
    # 升级后 message.channel.send 恰好调用一次，内容含 "Level 1"
async def test_disabled_guild_gains_no_xp(cog, message): ...
    # enabled=0：users 表没有新行，cog.cooldowns 为空，send 未调用
async def test_notice_goes_to_chosen_channel(cog, message): ...
    # mode="channel", channel=77：77 频道 send 一次，message.channel.send 未调用
async def test_missing_channel_sends_nothing_and_keeps_xp(cog, message): ...
    # get_channel 返回 None：两处 send 都未调用，users.level == 1
async def test_notice_off_sends_nothing(cog, message): ...
async def test_notice_failure_keeps_xp(cog, message): ...
    # send 抛 discord.HTTPException：users.level == 1，不向外抛
async def test_reload_guild_updates_and_clears_cache(cog): ...
```

`tests/test_sync.py` 增加 `assert "leveling" in sync.MODULES`。`tests/test_guild_cleanup.py` 的 `"leveling"` 建表语句增加 `CREATE TABLE level_config (guild_id INTEGER PRIMARY KEY)`，`GUILD_TABLES` 增加 `("leveling", "level_config")`，`_seed_guild` 写一行。

- [ ] **Step 2: 运行并确认失败**

Run: `python -m pytest -q tests/test_leveling_logic.py tests/test_sync.py tests/test_guild_cleanup.py`
Expected: FAIL，`parse_rewards` 无法导入，`"leveling"` 不在 `MODULES` 中，清理后 `level_config` 仍有数据。

- [ ] **Step 3: 实现**

- `level_config` 建表语句按规格第 5 节，在 `cog_load` 中执行，然后全量读入 `self._config`，并注册 `change_watcher`，写法照 `cogs/musicconfig.py`；`cog_unload` 注销。
- `on_message`：过滤机器人和私信后读配置，`enabled` 为假直接返回，放在冷却判断之前。
- DB 块内只写经验和等级并提交，`async with` 结束后才调用 Discord。
- `_send_level_notice`：`off` 返回；`channel` 用 `message.guild.get_channel(id)`，为 `None` 就返回，不回退到原频道；捕获 `discord.Forbidden`、`discord.HTTPException` 并打印日志。
- `sync.MODULES` 增加 `"leveling"`，`GUILD_TABLES` 增加 `("leveling", "level_config")`。

- [ ] **Step 4: 运行并确认通过**

Run: `python -m pytest -q tests/test_leveling_logic.py tests/test_sync.py tests/test_guild_cleanup.py`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add rinbot/cogs/leveling.py rinbot/rincore/sync.py rinbot/rincore/guild_cleanup.py tests/test_leveling_logic.py tests/test_sync.py tests/test_guild_cleanup.py
git commit -m "feat: let each server switch leveling and route level-up notices"
```

---

### Task 2: 机器人端发放等级奖励

**Files:**
- Modify: `rinbot/cogs/leveling.py`
- Test: `tests/test_leveling_logic.py`

**Interfaces:**
- Consumes: Task 1 的 `get_config`、`leveled_to`、`current_level`。
- Produces: `due_role_ids(rewards, level, owned_ids) -> list[int]`；`Leveling._grant_rewards(member, level: int, config: dict) -> None`。

- [ ] **Step 1: 写失败的测试**

假成员要通过 `isinstance(author, discord.Member)`：

```python
class FakeMember(discord.Member):
    id = 7
    bot = False
    mention = "<@7>"
    roles = property(lambda self: self.fake_roles)
    def __init__(self, role_ids=()):
        self.fake_roles = [SimpleNamespace(id=r) for r in role_ids]
        self.add_roles = AsyncMock()
```

假身份组是带 `position`、`managed`、`__lt__` 的小类；`guild.get_role` 查字典；`guild.me` 带 `top_role` 和 `guild_permissions.manage_roles`。

```python
def test_due_role_ids():
    rewards = [(5, 1), (10, 2), (20, 3)]
    assert due_role_ids(rewards, 4, set()) == []
    assert due_role_ids(rewards, 5, set()) == [1]
    assert due_role_ids(rewards, 20, {1}) == [2, 3]
    assert due_role_ids(rewards, 20, {1, 2, 3}) == []

async def test_reward_granted_on_level_up(cog, message): ...
async def test_backfill_without_level_up(cog, message): ...
    # users.level=10，本次不升级，配置 5 级奖励：add_roles 收到该身份组
async def test_rewards_are_cumulative(cog, message): ...
    # level=20，缺 5、10、20 三条：add_roles 收到三个身份组
async def test_no_missing_role_makes_no_call(cog, message): ...
async def test_skips_when_bot_lacks_manage_roles(cog, message): ...
async def test_skips_role_above_bot_and_managed_role(cog, message): ...
    # 只有合格的身份组传给 add_roles；全部不合格时未调用
async def test_skips_deleted_role(cog, message): ...
async def test_rewards_skip_non_member_author(cog, message): ...
    # author 是 SimpleNamespace(id=7, bot=False, mention="<@7>")，不抛异常
async def test_grant_failure_keeps_xp(cog, message): ...
    # add_roles 抛 discord.Forbidden：users.xp 已增加，不向外抛
async def test_notice_failure_still_grants(cog, message): ...
```

- [ ] **Step 2: 运行并确认失败**

Run: `python -m pytest -q tests/test_leveling_logic.py`
Expected: FAIL，`due_role_ids` 无法导入。

- [ ] **Step 3: 实现**

`on_message` 发完提示后，`if isinstance(message.author, discord.Member): await self._grant_rewards(message.author, leveled_to or current_level, config)`。`_grant_rewards` 先判断 `guild.me.guild_permissions.manage_roles`，用 `due_role_ids`，再按规格第 6 节过滤，过滤后为空直接返回，否则 `await member.add_roles(*roles, reason="等级奖励")`，捕获 `discord.Forbidden`、`discord.HTTPException` 并打印日志。

- [ ] **Step 4: 运行并确认通过**

Run: `python -m pytest -q tests/test_leveling_logic.py`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add rinbot/cogs/leveling.py tests/test_leveling_logic.py
git commit -m "feat: grant level reward roles as members earn xp"
```

---

### Task 3: 读写接口

**Files:**
- Modify: `website/permcheck.py`、`website/routes.py`（`ensure_tables` 约 520 行；`_bot_permission_checkup` 之后加辅助函数；排行榜接口旁加路由）
- Create: `website/tests/test_leveling_settings.py`
- Test: `tests/test_permcheck.py`

**Interfaces:**
- Produces（Task 5、6 使用）：
  - `permcheck.role_limits(roles, bot_member, guild_id) -> {"can_manage_roles": bool, "blocked": {role_id_str: "above"|"managed"}}`。
  - `GET /api/guild/<gid>/leveling` → `{"enabled": bool, "notify_mode": str, "notify_channel": str, "rewards": [{"level": int, "role_id": str}], "blocked_roles": {id: reason}, "can_manage_roles": bool|null}`。
  - `POST` 同一地址，请求体 `{enabled, notify_mode, notify_channel, rewards}`，成功返回 `{"ok": true}`。

- [ ] **Step 1: 写失败的测试**

`tests/test_permcheck.py`：

```python
def test_role_limits():
    roles = [
        {"id": "1", "name": "@everyone", "permissions": "0", "position": 0},
        {"id": "2", "name": "Rin", "permissions": str(1 << 28), "position": 5, "managed": True},
        {"id": "3", "name": "low", "permissions": "0", "position": 2},
        {"id": "4", "name": "same", "permissions": "0", "position": 5},
        {"id": "5", "name": "high", "permissions": "0", "position": 9},
        {"id": "6", "name": "bot", "permissions": "0", "position": 1, "managed": True},
    ]
    result = role_limits(roles, {"roles": ["2"]}, "1")
    assert result == {"can_manage_roles": True, "blocked": {"2": "managed", "4": "above", "5": "above", "6": "managed"}}

def test_role_limits_permission_bits():
    # 缺权限时 can_manage_roles 为 False；ADMINISTRATOR (1 << 3) 为 True
```

`website/tests/test_leveling_settings.py` 用 `test_checkup_and_invite.py` 的 `FakeDiscord` 写法，`from test_bot_avatar import routes`；`DB_LEVELING` 指向临时文件并建 `level_config`；`_notify_bot`、`audit`、`_resolve_actor` 打桩。测试：

- `test_get_defaults_without_row`：返回默认值，且未写入任何行。
- `test_get_marks_blocked_roles`：`blocked_roles` 含 `above` 和 `managed`，不含 `@everyone`。
- `test_get_when_discord_is_down`：`blocked_roles == {}`，`can_manage_roles is None`，状态 200。
- `test_get_requires_access`：401。
- `test_post_saves_sorted_and_notifies`：提交等级 `[20, 5]`，库内按 `[5, 20]`，`_notify_bot` 收到 `("leveling", 123)`。
- `test_post_rejects_bad_body`（子测试逐条期望 400）：非对象、`enabled` 非布尔、`notify_mode="x"`、`channel` 模式无频道、21 条、`level` 为 `0`/`1000`/`True`/`1.5`/`"5"`、`role_id` 为 `"0"`/`"abc"`/`5`、`rewards` 非数组、等级重复、身份组重复。
- `test_post_rejects_foreign_role`：`_validate_guild_resources` 返回 `False` 时 400，不写库。
- `test_post_when_discord_is_down`：返回 `None` 时 502，不写库。
- `test_post_allows_role_above_bot`：`_validate_guild_resources` 调用时没有 `assignable_roles`。
- `test_post_clears_channel_when_not_channel_mode`：`notify_mode="off"`、`notify_channel="77"`，库内为 0，且校验时不含 77。
- `test_post_disabled_skips_discord_checks`：`enabled=False` 时 `_validate_guild_resources` 未被调用，保存成功，失效的 id 原样写入。

- [ ] **Step 2: 运行并确认失败**

Run: `python -m pytest -q tests/test_permcheck.py && cd website && python -m pytest -q tests/test_leveling_settings.py`
Expected: FAIL，`role_limits` 无法导入，接口 404/405。

- [ ] **Step 3: 实现**

- `role_limits`：`MANAGE_ROLES = 1 << 28`；权限用 `base_permissions`；`top` 为小凛自身身份组的最大 `position`；跳过 `guild_id` 对应的 `@everyone`；`managed` 优先于 `above`；`position >= top` 记为 `above`。
- `_bot_role_limits(gid) -> dict | None`：依次读 `/users/@me`、`/guilds/{gid}/roles`、成员信息，任何一步为空返回 `None`。不缓存，这样改完身份组顺序刷新页面就能看到。
- `ensure_tables` 建 `level_config`，语句和机器人端相同。
- `_parse_leveling_body(d) -> (cfg, error)`：纯校验，整数用 `type(v) is int` 排除布尔值，id 用 `re.fullmatch(r"[1-9][0-9]{0,19}", v)`，错误信息用中文：`升级提示设置无效`、`请选择要发到哪个频道`、`等级奖励最多 20 条`、`等级要在 1 到 999 之间`、`身份组无效`、`等级奖励里有重复的等级或身份组`。
- POST 校验资源时错误信息：`频道或身份组不属于当前服务器`（400）、`暂时读不到 Discord，请稍后再试`（502）。写库用 `INSERT OR REPLACE`，`rewards` 用 `json.dumps` 存。审计文案：`等级设置已更新`。

- [ ] **Step 4: 运行并确认通过**

Run: `python -m pytest -q tests/test_permcheck.py && cd website && python -m pytest -q tests/test_leveling_settings.py`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add website/permcheck.py website/routes.py website/tests/test_leveling_settings.py tests/test_permcheck.py
git commit -m "feat: add the leveling settings api"
```

---

### Task 4: 概览页的开关和摘要

**Files:**
- Modify: `website/routes.py:340-375`、`:389-414`、`:1299-1304`，`website/static/js/modules/overview.js:4,9-48`，`website/templates/server.html:9,362`，`website/i18n/zh.json`
- Test: `website/tests/test_dashboard_status.py`、`website/tests/test_dashboard_templates.py`、`website/tests/overview.test.cjs`

**Interfaces:**
- Consumes: Task 1 的表结构。
- Produces: 摘要 `{"enabled": int, "rewards": int}`；`overview.leveling.rewards` 字符串。

- [ ] **Step 1: 写失败的测试**

`test_dashboard_status.py`：

```python
async def test_leveling_counts_as_on_without_row(self): ...
    # 建好 level_config 但没有行：_guild_module_config == 'enabled'；摘要 == {'enabled': 1}
async def test_leveling_state_follows_enabled(self): ...
    # enabled=0 → 'disabled'；摘要 {'rewards': 2, 'enabled': 0}
async def test_leveling_missing_db_counts_as_on(self): ...
async def test_leveling_quick_toggle_creates_row(self): ...
    # POST /modules/leveling/enabled {'enabled': False}：写入 enabled=0，rewards 仍是 '[]'，通知 ('leveling', 123)
```

把 `test_summary_missing_db_and_broken_db_are_none` 里的 `'leveling'` 换成 `'utility'`（leveling 现在有摘要）。

`test_dashboard_templates.py`：把 `test_overview_lists_every_module_once_with_toggles_for_four` 改名为 `..._for_five`，期望 `['welcome','leveling','automod','botlog','serverlog']`。

`overview.test.cjs`：

```js
test('leveling summary counts rewards and falls back to the blurb without any', () => {
    assert.deepEqual(plain(Overview.summaryText('leveling', {enabled: 1, rewards: 2}, [])), {text: 'overview.leveling.rewards:2', warn: false});
    assert.equal(Overview.summaryText('leveling', {enabled: 1}, []), null);
});
```

断言中的文本形式按该文件现有的 `tr` 桩调整。

- [ ] **Step 2: 运行并确认失败**

Run: `cd website && python -m pytest -q tests/test_dashboard_status.py tests/test_dashboard_templates.py && node --test tests/overview.test.cjs`
Expected: FAIL

- [ ] **Step 3: 实现**

- `_guild_module_config`：`specs` 加 `"leveling": (DB_LEVELING, "level_config")`；`default` 对 leveling 取 `"enabled"`；`leveling` 加入按 `enabled` 判断的集合，启用时返回 `"enabled"`。
- `_SUMMARY_SPECS["leveling"] = ("DB_LEVELING", "SELECT * FROM level_config WHERE guild_id=?", _with_enabled(lambda row: {"rewards": len(json.loads(row["rewards"] or "[]"))}))`；`_ENABLED_WITHOUT_ROW["leveling"] = 1`。
- `_TOGGLE_TABLES["leveling"] = ("DB_LEVELING", "level_config")`。
- `overview.js`：`TOGGLE_SLUGS` 加 `leveling`；`summaryText` 加分支，`summary.rewards` 为假时 `return null`，否则 `parts.push(tr('overview.leveling.rewards', {n: summary.rewards}))`。
- `server.html`：`toggle_slugs` 加 `'leveling'`；`overview.js` 版本提到 `20261108c`。
- `zh.json` 的 `overview` 下加 `"leveling": {"rewards": "{n} 个等级奖励"}`。

- [ ] **Step 4: 运行并确认通过**

Run: `cd website && python -m pytest -q tests/test_dashboard_status.py tests/test_dashboard_templates.py && node --test tests/overview.test.cjs`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add website/routes.py website/static/js/modules/overview.js website/templates/server.html website/i18n/zh.json website/tests/test_dashboard_status.py website/tests/test_dashboard_templates.py website/tests/overview.test.cjs
git commit -m "feat: show leveling on the overview with a quick switch"
```

---

### Task 5: 页面结构、文案和样式

**Files:**
- Modify: `website/templates/server.html:302-308`、`website/i18n/zh.json:468-472`、`website/static/css/console.css`、`website/templates/_console_base.html`、`error.html`、`login_gate.html`
- Test: `website/tests/test_dashboard_templates.py`、`website/tests/test_i18n.py`

**Interfaces:**
- Produces（Task 6 使用）的元素 id：`lv-enabled`、`lv-mode`、`lv-channel-row`、`lv-channel`、`lv-no-permission`、`lv-empty`、`lv-rewards`、`lv-add`、`lv-limit`、`lb-list`。类名：`lv-reward`、`lv-level`、`lv-dot`、`lv-role`、`lv-note`、`lv-note--bad`。

- [ ] **Step 1: 写失败的测试**

`test_dashboard_templates.py` 新增 `test_leveling_page_has_settings_and_board`：

- `pg-leveling` 所在标签带 `data-draft`。
- 含 `id="lv-enabled"`、`tab-leveling-settings`、`tab-leveling-board`、`panel-leveling-board`，`lb-list` 在 `panel-leveling-board` 之后。
- 上面列出的 id 全部存在；`lv-mode` 有 `value="here"`、`value="channel"`、`value="off"` 三个选项。
- `console.css` 含 `.lv-reward`。

`test_i18n.py` 新增 `test_leveling_strings`，逐条断言下表每个键的文案，`leveling.board` 已移除。

- [ ] **Step 2: 运行并确认失败**

Run: `cd website && python -m pytest -q tests/test_dashboard_templates.py tests/test_i18n.py`
Expected: FAIL

- [ ] **Step 3: 实现文案**

`leveling` 下的键：

| 键 | 文案 |
|---|---|
| `intro` | 聊天攒经验，小凛会按经验给大家排名。关闭后已有等级会保留。 |
| `master` | 开启等级系统 |
| `tab.settings` / `tab.board` | 设置 / 排行榜 |
| `notify` | 升级提示 |
| `notify_here` / `notify_channel` / `notify_off` | 发在原频道 / 发到指定频道 / 不发 |
| `channel` | 发到哪个频道 |
| `rewards` | 等级奖励 |
| `rewards_hint` | 成员达到等级后自动获得身份组，升到更高等级也会保留。手动摘掉的身份组，成员下次获得经验时会再发回来。 |
| `add` | 添加奖励 |
| `no_rewards` | 还没有等级奖励。 |
| `max` | 最多 20 条奖励 |
| `level_unit` | 级 |
| `level_label` | 等级 |
| `role_label` | 身份组 |
| `pick_role` | — 选择身份组 — |
| `remove` | 移除这条奖励 |
| `unknown_role` | 未知身份组 |
| `unknown_channel` | 未知频道 |
| `warn.above` | 这个身份组排在小凛之上，发不出去。到服务器设置里把小凛的身份组拖到它上面。 |
| `warn.managed` | 这个身份组由其他机器人或集成管理，小凛不能发放。 |
| `warn.deleted` | 这个身份组已不存在，请换一个或删掉这条奖励。 |
| `warn.no_permission` | 小凛没有“管理身份组”权限，等级奖励暂时发不出去。加上这个权限后会自动恢复。 |
| `error.duplicate_level` | 这个等级已经有奖励了。 |
| `error.duplicate_role` | 这个身份组已经用在别的等级上了。 |
| `error.need_channel` | 请选择要发到哪个频道。 |
| `error.need_role` | 请选择一个身份组。 |
| `error.level_range` | 等级要在 1 到 999 之间。 |
| `error.fix_first` | 请先改正页面上标出的内容。 |

`empty` 保留。

- [ ] **Step 4: 实现模板**

```jinja
<section class="page" id="pg-leveling" data-slug="leveling" data-group="{{ tr('nav.group.community') }}" data-title="{{ tr('nav.module.leveling') }}" data-draft>
    {{ page_head(tr('nav.module.leveling'), tr('leveling.intro'), 'lv-enabled', tr('leveling.master')) }}
    {{ tabs('leveling', [('settings', tr('leveling.tab.settings')), ('board', tr('leveling.tab.board'))]) }}
    {% call tab_panel('leveling', 'settings') %}
        ...
    {% endcall %}
    {% call tab_panel('leveling', 'board') %}<div class="lb-list" id="lb-list"></div>{% endcall %}
</section>
```

设置面板：

- 一个 `.section > .list`，放两行：`row(tr('leveling.notify'), None, 'lv-mode', depends='lv-enabled')`，内含普通 `select.select#lv-mode`；`div#lv-channel-row[hidden]` 包住 `row(tr('leveling.channel'), None, 'lv-channel', depends='lv-enabled')`，内含 `select.select#lv-channel[data-search]`。
- 第二个 `.section`：`h3.section-title`、`p.section-hint`（`rewards_hint`）、`p#lv-no-permission.note.note--warn[hidden]`（图标 `triangle-alert`，文案 `warn.no_permission`）、`p#lv-empty.section-hint[hidden]`、`div#lv-rewards.lv-rewards[data-depends-on="lv-enabled"]`，最后是 `.actions`，内含 `button#lv-add.btn.btn--secondary`（`icon('plus')` 加文案）和 `span#lv-limit.unit[hidden]`。`#lv-add` 不放在 `data-depends-on` 容器里，由 JS 同时按总开关和条数控制禁用，否则总开关一变 `dependencies()` 会把上限禁用状态覆盖掉。

- [ ] **Step 5: 实现样式**

加到 `.rr-row` 规则附近：

```css
.lv-rewards { display: flex; flex-direction: column; margin-top: 12px; }
.lv-reward { position: relative; display: grid; grid-template-columns: 104px 12px minmax(0, 1fr) 36px; align-items: center; column-gap: 8px; padding-bottom: 16px; }
.lv-reward:last-child { padding-bottom: 0; }
.lv-reward:not(:last-child)::before { content: ""; position: absolute; left: 20px; top: var(--control-h); bottom: 0; border-left: 1px solid var(--line); }
.lv-reward .num-field { width: 100%; min-width: 0; }
.lv-reward .search-select { width: 100%; }
.lv-reward .num { font-variant-numeric: tabular-nums; }
.lv-dot { width: 12px; height: 12px; border-radius: 50%; background: var(--muted); outline: 1px solid var(--img-line); outline-offset: -1px; }
.lv-note { grid-column: 3 / -1; margin-top: 4px; font-size: 13px; color: var(--warn); }
.lv-note--bad { color: var(--bad); }
```

在现有 `.rr-row` 的窄屏媒体查询中加 `.lv-reward { grid-template-columns: 96px 12px minmax(0, 1fr) 44px; }`。`console.css` 版本提到 `20261108c`，三个模板都改。

- [ ] **Step 6: 运行并确认通过**

Run: `cd website && python -m pytest -q tests`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add website/templates/server.html website/templates/_console_base.html website/templates/error.html website/templates/login_gate.html website/i18n/zh.json website/static/css/console.css website/tests/test_dashboard_templates.py website/tests/test_i18n.py
git commit -m "feat: add the leveling settings page layout"
```

---

### Task 6: 等级页的前端逻辑

**Files:**
- Modify: `website/static/js/modules/leveling.js`、`website/templates/server.html:369`（版本提到 `20261108c`）
- Create: `website/tests/leveling_ui.test.cjs`

**Interfaces:**
- Consumes: Task 3 的接口，Task 5 的元素 id。现有的 `Console.channels/roles/api/channelOptions/roleOptions/go/dependencies`、`DashboardUI.changed`、`DashboardExtras.enhanceSelects`。
- Produces: `window.LevelRewards = {nextLevel, warningKey, problems}`，都是纯函数：
  - `nextLevel(levels: number[]) -> number`：无奖励时 5，否则 `min(max + 5, 999)`。
  - `warningKey(roleId, blocked: object) -> string | null`：`leveling.warn.above`、`leveling.warn.managed` 或 `null`。
  - `problems({enabled, mode, channel, channelLost, rows}) -> [{index, key}]`：`rows` 元素是 `{level: string, role: string, lost: boolean}`；频道问题的 `index` 为 `'channel'`；重复只标在靠后的一行。

每行的子元素顺序固定：`.num-field`（内含 `input.num.lv-level` 和 `.num-unit`）、`.lv-dot`、`select.select.lv-role[data-search]`、移除按钮、`.lv-note[hidden]`。

- [ ] **Step 1: 写失败的测试**

`website/tests/leveling_ui.test.cjs`，用 `vm` 加载 `modules/leveling.js`。DOM 桩需要支持 `createElement`、`append`、`remove`、`children`、`dataset`、`hidden`、`disabled`、`value`、`style`、`classList`、`setAttribute`、`addEventListener` 和事件派发，`append` 已有子节点时要把它移动到末尾（并计数，用于断言“没有移动”）。`Console.channelOptions` 和 `roleOptions` 的桩要按真实行为把选项写进 select，列表中没有 `selected` 时 `value` 为 `'0'`。`Console.api` 按路径返回 `/leveling` 和 `/leaderboard`，`POST` 记录请求体。

```js
test('nextLevel starts at 5 and adds 5 up to the cap', () => {
    assert.equal(R.nextLevel([]), 5);
    assert.equal(R.nextLevel([5, 20]), 25);
    assert.equal(R.nextLevel([997]), 999);
});
test('warningKey names the reason', () => {
    assert.equal(R.warningKey('1', {1: 'above'}), 'leveling.warn.above');
    assert.equal(R.warningKey('2', {2: 'managed'}), 'leveling.warn.managed');
    assert.equal(R.warningKey('3', {}), null);
});
test('problems flags duplicates on the later row only', ...);
    // rows 等级 [5,5]：[{index: 1, key: 'leveling.error.duplicate_level'}]；身份组重复同理
test('problems covers empty role, range and missing channel', ...);
    // role '0' → need_role；level ''/'0'/'1000'/'1.5' → level_range；mode 'channel' 且 channel '0' → {index:'channel', key:'leveling.error.need_channel'}
test('problems reports deleted roles while on', ...);
    // {role:'0', lost:true} → leveling.warn.deleted
test('off skips lost resources', ...);
    // enabled:false 时 lost 角色和 channelLost 不算问题；未选身份组的新行仍算 need_role
```

其余测试通过 `def.load()` 渲染后操作：

- `load renders rows in order with the role colour`：圆点 `style.background` 为 `#ff0000`（`color: 16711680`）；颜色 0 时为空字符串。
- `rows get positional names`：两行的 level 和 select 的 `name` 分别是 `lv-level-0`、`lv-level-1`、`lv-role-0`、`lv-role-1`；排序、删除后重新编号。
- `sort runs on blur not on input`：`input` 事件后顺序不变，`blur` 后按等级升序。
- `sort leaves the DOM alone when the order is right`：顺序正确时 `blur` 不移动节点。
- `sort waits for the pointer`：先派发 document `pointerdown`，再 `blur`，顺序不变；`pointerup` 后等一个宏任务，顺序更新。
- `add row uses nextLevel and stops at twenty`：第 20 行后 `lv-add.disabled` 为真，`lv-limit.hidden` 为假；删除一行后恢复。
- `add stays disabled while the master switch is off`。
- `empty state follows the row count`。
- `picking a blocked role warns at once`：select 派发 `change` 后 `.lv-note` 为 `leveling.warn.above`，且没有 `lv-note--bad`。
- `deleted role shows the bad note`。
- `discord down keeps saved roles`：`can_manage_roles: null`，`Console.roles` 返回 `[]`：select 的 `value` 是原 id，没有警告，`lv-no-permission.hidden` 为真。
- `no permission shows the banner`：`can_manage_roles: false`。
- `channel row follows the mode`：`mode` 为 `channel` 时 `lv-channel-row.hidden` 为假；切换后为真，提交的 `notify_channel` 为 `'0'`。
- `save posts sorted rows`：请求体 `{enabled:true, notify_mode:'here', notify_channel:'0', rewards:[{level:5, role_id:'1'}, {level:20, role_id:'2'}]}`，`level` 是数字。
- `save refuses problems and marks the row`：`def.save()` 被拒绝，错误信息为 `leveling.error.fix_first`，没有发 POST，对应行 `.lv-note` 有错误文案和 `lv-note--bad`；改正后错误消失。
- `save off keeps lost ids`：关闭状态下，已删除身份组的行提交原 id。

- [ ] **Step 2: 运行并确认失败**

Run: `cd website && node --test tests/leveling_ui.test.cjs`
Expected: FAIL，`LevelRewards` 未定义。

- [ ] **Step 3: 实现**

保留现有的排行榜渲染和 `isLoaded`。行状态放在模块内数组，元素是 `{node, level, dot, select, note, lost}`，其中 `lost` 是已删除身份组的原 id 或空字符串。

`load`：`Promise.all` 取频道、身份组、`/leveling`、`/leaderboard`。`can_manage_roles === null` 视为读不到 Discord：

- 频道：把 `[{id: saved, name: tr('leveling.unknown_channel')}]` 作为列表传给 `channelOptions`（仅当频道列表为空且有已存频道）。
- 身份组：把已存 id 以 `{id, name: tr('leveling.unknown_role'), color: 0}` 追加到本次渲染用的列表，不写回 `Console.roles` 的缓存。
- 读得到 Discord 时，已存身份组不在列表中记为 `lost`；已存频道不在列表中记为 `channelLost`（`channelOptions` 会显示现有的频道失效提示）。

排序算法（点错行的问题由这里解决）：

```js
function sortRows() {
    const next = [...rows].sort((a, b) => levelOf(a) - levelOf(b)); // 非法等级视为 Infinity，stable
    if (next.every((row, i) => row === rows[i])) return;
    const focused = document.activeElement;
    rows = next;
    rows.forEach(row => list.append(row.node));
    if (focused?.isConnected && document.activeElement !== focused) focused.focus?.({preventScroll: true});
    renumber();
}
function queueSort() { if (pointerDown) pendingSort = true; else sortRows(); }
// document: pointerdown 置 pointerDown；pointerup/pointercancel 清除，且 pendingSort 时 setTimeout(sortRows, 0)，让 click 先落到按下的元素上
```

`save`：先 `sortRows()`，算 `problems`。有问题时置 `showErrors = true`、渲染错误、`Console.go('leveling', 'settings')`、对第一处问题的行调用 `scrollIntoView?.({block: 'center'})`，并抛 `new Error(tr('leveling.error.fix_first'))`。通过时：`role_id` 取 `select.value`，为 `'0'` 时取 `row.lost`；`notify_channel` 仅在 `channel` 模式下提交，选择为 `'0'` 时取失效的已存 id，否则 `'0'`。成功后 `showErrors = false`。

每次 `input`/`change`/删除后都更新说明行，优先级：`showErrors` 时的错误 > `lost` > `warningKey`。调用 `DashboardUI.changed('pg-leveling')`。选择框 `change` 时清掉该行的 `lost`，并更新圆点。

`#lv-add` 的禁用条件：`!lv-enabled.checked || rows.length >= 20`，`lv-enabled` 的 `change` 也要重新计算。新行要调用 `enhanceSelects(row.node)` 并聚焦等级框。

- [ ] **Step 4: 运行并确认通过**

Run: `cd website && node --test tests/leveling_ui.test.cjs`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add website/static/js/modules/leveling.js website/templates/server.html website/tests/leveling_ui.test.cjs
git commit -m "feat: edit level rewards in the console"
```

---

### Task 7: 真实浏览器检查和收尾

**Files:**
- Modify: `README.md:11`、`README.zh-CN.md:11`（测试数徽章），以及检查中发现需要修的文件
- Test: 全部测试

**Interfaces:**
- Consumes: Task 1 到 6 的全部结果。

- [ ] **Step 1: 跑全部测试并记下总数**

Run: `python -m pytest -q`、`cd website && python -m pytest -q tests`、`cd website && node --test tests/*.cjs`
Expected: 全部 PASS。把三项总数相加。

- [ ] **Step 2: 在真实浏览器里走一遍**

用 `.claude/launch.json` 的 `polish-preview`（端口 5094），假数据里配好：一个正常奖励、一个排在小凛之上的身份组、一个托管身份组、一个已删除的身份组。检查：

- 标签切换、未保存状态、自动排序、添加和移除、20 条上限。
- 选“发到指定频道”时频道行出现。
- 关闭总开关后主提示出现，行不可编辑，保存成功。
- 概览页出现第五个开关，摘要显示奖励数。
- `read_console_messages` 没有报错。

- [ ] **Step 3: 截图自查**

浅色、深色、375px 宽分别截图，竖线和行的对齐、警告换行、横向溢出都要看。逐条列出发现的问题和修改。样式修复单独提交：`style: ...`。

- [ ] **Step 4: 更新徽章并提交**

把两份 README 的 `tests-994_passing` 改成 Step 1 的总数。

```bash
git add README.md README.zh-CN.md
git commit -m "docs: update the test count for leveling settings"
```

- [ ] **Step 5: 确认范围**

Run: `git status --short`（只应剩 `?? .claude/`）、`git log --oneline origin/master..master`
Expected: 没有推送，`rinbot/cogs/netease.py` 不在任何提交中。
