# 指令与消息改版二：指令易用性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 顶层斜杠指令从 66 条降到 38 条，参数和说明中英双语，编号类参数改自动补全，时长统一写法，新增 `/case` 和 `/help 指令`，旧前缀名照常可用。

**Architecture:** 纯逻辑放在 `rinbot/rincore/`：时长解析和候选（`durations.py`）、翻译表读取和 discord.py 翻译器（`command_i18n.py`）、旧名字改写和停用记录迁移（`legacy.py`）、案件查询和修改（`cases.py`）。机器人侧共用的输入工具放在 `cogs/_inputs.py`：时长转换器、补全过滤、语言判断。各 cog 按新指令表改名、分组、加补全；中文全部写进 `rinbot/i18n/commands.zh.json`，测试保证它完整。

**Tech Stack:** Python 3.11, discord.py 2.7.1（hybrid 指令、`app_commands.Translator`、autocomplete、`commands.Range`），aiosqlite，pytest（`asyncio_mode = auto`）。

**Spec:** `docs/superpowers/specs/2026-11-04-bot-commands-usability-design.md`

## Global Constraints

- 顶层斜杠指令（不含主人指令和网易云）正好 38 条，见 spec 第 4.1 节。
- 指令名和子指令名英文；代码里的 `description` 和参数说明改成英文（一句话、句首大写、不加句号）；中文只放在翻译表里，`zh-CN` 和 `zh-TW` 用同一份。
- 名字最多 32 字符，说明最多 100 字符，中英文都一样；中文参数名 2–4 个字，同一条指令里不重复。
- 时长上限：`/mute` 28 天，`/ban` 365 天，`/giveaway start` 365 天，`/slowmode` 6 小时。
- 补全最多 25 个候选，3 秒内返回，出错时返回空列表、不抛异常。候选里的固定词按 `is_zh(interaction)` 显示中文或英文：剩 / left、已结束 / ended、首 / songs。
- 子项目一的约定照旧：消息只走 `_messages.embed` / `send` / `send_notice`；权限只用 `_perms.require` / `owner_only`；标题和字段名不加 emoji。
- `netease.py` 不修改、不提交；9 条开发和主人指令不改名、不要求翻译。
- 直接在 master 上提交，标题 `feat:` / `fix:` / `style:` / `docs:` 加小写祈使句，不加署名；推送前要问用户。
- 测试命令：根目录 `python -m pytest -q`；网页 `cd website && python -m pytest -q tests`；控制台 JS `cd website && node --test tests/*.test.cjs`；cog 导入检查（同部署脚本的 import smoke）。每个任务结束时全部要绿。
- 文案以 spec 为准；本计划里的中文文案逐字照抄。

## Review Focus

1. **前缀 `r!ban @小明 刷屏不听劝`（没填时长）**：原因不能被当成时长吃掉，按永久封禁处理，原因完整。测试在 Task 4。
2. **补全拿不到数据**（服务器没有封禁、机器人没有封禁权限、存档为空、队列为空）：返回空列表，不报未知错误。测试在 Task 4、6。
3. **旧名字改写的边界**：`r!warnsx`、`R!WARNS`、正文中间出现的 `r!warns`、只有前缀的 `r!`。只改写前缀后面的完整指令名，不区分大小写，其他原样不动。测试在 Task 3。
4. **非中文客户端和翻译表缺条目**：翻译器返回 `None`，Discord 显示英文，不报错。测试在 Task 2。
5. **`/case duration` 碰到已经失效的处罚**（禁言已到期、成员已离开服务器、临时封禁已解封）：提示"这个案件没有可以修改的时长"，不报错。测试在 Task 5。

---

### Task 1: 时长解析、候选和转换器

**Files:**
- Modify: `rinbot/rincore/durations.py`
- Create: `rinbot/cogs/_inputs.py`
- Modify: `rinbot/cogs/errors.py`（两种时长错误的提示）
- Test: `tests/test_durations.py`（扩充）、`tests/test_inputs.py`

**Interfaces:**
- Produces（`rincore/durations.py`）：
  - `parse_duration(s: str) -> Optional[int]`：签名不变，单位扩展为 s/m/h/d/w 和 秒、分、分钟、时、小时、天、日、周、星期；允许空格，不区分大小写；同一单位不能重复，总时长 > 0 且 ≤ 365 天。
  - `canonical(seconds: int) -> str`：规范写法，只用 d/h/m/s，如 5400 → `"1h30m"`，604800 → `"7d"`。
  - `label(seconds: int, zh: bool) -> str`：中文 `"1 小时 30 分钟"`，英文 `"1 hour 30 minutes"`（单数不加 s）；0 时中文 `"关闭"`、英文 `"Off"`。
  - `suggest(current: str, presets: Sequence[int], max_seconds: int, zh: bool) -> list[tuple[str, str]]`：返回 `(显示文字, 值)`，最多 25 个，去重。规则：
    - 输入为空：给常用值。
    - 纯数字 n：依次给 n 分钟、n 小时、n 天、n 周，只留不超上限的。
    - 能解析：把它放第一个，后面接常用值。
    - 其他输入：给常用值。
    - 常用值里的 0 代表"关闭"，值为 `"0"`。
  - `PRESETS`：`{"mute": [600, 3600, 86400, 604800, 2419200], "ban": [86400, 604800, 2592000], "giveaway": [3600, 86400, 259200, 604800], "slowmode": [0, 5, 30, 60, 300, 3600]}`；`LIMITS`：`{"mute": 2419200, "ban": 31536000, "giveaway": 31536000, "slowmode": 21600}`。
- Produces（`cogs/_inputs.py`）：
  - `class BadDuration(commands.BadArgument)`、`class DurationTooLong(commands.BadArgument)`，后者有属性 `limit: int`（秒）。
  - `Duration(kind: str) -> type[commands.Converter]`：`kind` 是 `PRESETS` 的键。`convert` 返回秒数；`slowmode` 接受 `0`、`关闭`、`off` 并返回 0；解析失败抛 `BadDuration`，超上限抛 `DurationTooLong(limit)`。
  - `duration_autocomplete(kind: str)`：返回 `async (interaction, current) -> list[app_commands.Choice[str]]`，内部调 `suggest(..., zh=is_zh(interaction))`。
  - `is_zh(interaction) -> bool`：`interaction.locale` 是 `discord.Locale.chinese` 或 `discord.Locale.taiwan_chinese`。
  - `choices(items: Iterable[tuple[str, object]], current: str, limit: int = 25) -> list[app_commands.Choice]`：按显示文字不区分大小写地包含 `current` 过滤，保持原顺序，最多 `limit` 个；值是 int 时用 int Choice，否则 str。
- Produces（`errors.notice_for`）：`BadDuration` → `("error", "时长格式不对", "可以写 10m、1h30m、2d、1w，或者 10分钟、1小时、2天。")`；`DurationTooLong` → `("error", "时长太长了", f"最长 {label(e.limit, zh=True)}。")`。这两条放在通用 `BadArgument` 分支之前。

- [ ] **Step 1: 写失败的测试**
  - `tests/test_durations.py` 新增：
    - `test_parse_weeks_and_chinese_units`：`"1w"`→604800，`"10分钟"`→600，`"1小时30分钟"`→5400，`"2 天"`→172800，`"1星期"`→604800，`"3日"`→259200，`"1H30M"`→5400。
    - `test_parse_rejects_repeated_mixed_units`：`"1h1小时"` 返回 None（同一单位重复）。
    - `test_canonical_and_label`：`canonical(5400)=="1h30m"`，`canonical(604800)=="7d"`；`label(5400, True)=="1 小时 30 分钟"`，`label(5400, False)=="1 hour 30 minutes"`，`label(3600, False)=="1 hour"`，`label(0, True)=="关闭"`，`label(0, False)=="Off"`。
    - `test_suggest_empty_gives_presets`、`test_suggest_digit_spreads_units_within_limit`（`suggest("3", PRESETS["mute"], LIMITS["mute"], True)` 的值为 `["3m","3h","3d","21d"]`，`"5"` 在 mute 下不含 `"35d"`）、`test_suggest_parsed_first`（`"1h30m"` 第一个是 `("1 小时 30 分钟", "1h30m")`）、`test_suggest_off_preset`（slowmode 空输入第一个是 `("关闭", "0")`）、`test_suggest_at_most_25`。
    - 原有 6 个测试保持通过。
  - `tests/test_inputs.py`：
    - `test_duration_converter`：`Duration("mute")` 转 `"10m"` 得 600；`"刷屏"` 抛 `BadDuration`；`"29d"` 抛 `DurationTooLong`，`limit == 2419200`。
    - `test_slowmode_accepts_off`：`"0"`、`"关闭"`、`"off"` 都得 0；`"7h"` 抛 `DurationTooLong`。
    - `test_choices_filters_and_caps`。
    - `test_is_zh`。
    - `test_duration_notices`：`notice_for(BadDuration("x"))`、`notice_for(DurationTooLong(2419200))` 等于上面的文案，后者正文 `"最长 28 天。"`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest -q tests/test_durations.py tests/test_inputs.py`
Expected: FAIL（`canonical` / `_inputs` 不存在）

- [ ] **Step 3: 实现**：`durations.py` 和 `_inputs.py`，`errors.notice_for` 加两个分支（`from _inputs import BadDuration, DurationTooLong`）

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add rinbot/rincore/durations.py rinbot/cogs/_inputs.py rinbot/cogs/errors.py tests/test_durations.py tests/test_inputs.py
git commit -m "feat: parse durations in one format with chinese units and suggestions"
```

---

### Task 2: 翻译表和翻译器

**Files:**
- Create: `rinbot/i18n/commands.zh.json`、`rinbot/rincore/command_i18n.py`
- Modify: `rinbot/main.py`（`setup_hook` 装翻译器）、`rinbot/cogs/health.py`、`rinbot/cogs/help.py`（说明改从翻译表取）
- Test: `tests/test_command_i18n.py`

**Interfaces:**
- 表结构：

```json
{
  "commands": {
    "ban": {
      "description": "封禁一名成员，填了时长就是临时封禁",
      "params": {"member": {"name": "成员", "description": "要封禁的成员或用户 ID"}},
      "examples": ["/ban @小明 7d 刷屏"]
    }
  },
  "choices": {"off": "关闭", "single": "单曲", "queue": "队列"}
}
```

键是 app command 的 `qualified_name`（如 `"warnings remove"`）。组本身也有条目（只有 `description`）。
- Produces（`rincore/command_i18n.py`）：
  - `TABLE_PATH`：指向 `rinbot/i18n/commands.zh.json`。
  - `load(path=TABLE_PATH) -> dict`：结果缓存。
  - `zh_description(path: str, table=None) -> Optional[str]`。
  - `zh_param(path: str, name: str, table=None) -> Optional[dict]`。
  - `examples(path: str, table=None) -> list[str]`。
  - `ZH_LOCALES = {discord.Locale.chinese, discord.Locale.taiwan_chinese}`。
  - `class CommandTranslator(app_commands.Translator)`，`__init__(self, table: Optional[dict] = None)`；`translate(string, locale, context)` 规则：
    - 非中文语言返回 `None`。
    - `command_name`、`group_name` 返回 `None`（名字不翻）。
    - `command_description`、`group_description` 用 `context.data.qualified_name` 查说明。
    - `parameter_name`、`parameter_description` 用 `context.data.command.qualified_name` 和 `context.data.name` 查参数。
    - `choice_name` 用 `context.data.value` 查 `choices`。
    - 查不到返回 `None`。
- Produces（测试辅助，`tests/command_tree.py`）：`top_level_app_commands() -> list`，遍历 `rinbot/cogs/` 下除 `netease.py` 外每个模块里的 `commands.Cog` 子类的 `__cog_commands__`，取 `parent is None` 且不是主人指令的 hybrid 指令的 `app_command`；`walk(app_cmd)` 产出它自己和所有子指令、子组。后面的任务都用它。
- `health._command_snapshot` 的 `desc` 改为 `zh_description(name) or command.description`；`help._format_command` 同样先取中文。

- [ ] **Step 1: 写失败的测试** `tests/test_command_i18n.py`：
  - `test_translator_ignores_other_languages`（Review Focus 4）：对英语、日语返回 `None`。
  - `test_translator_fills_descriptions_params_and_choices`：
    - 在测试里定义一个 hybrid 指令 `t`（参数 `member: discord.Member`），再定义一个带 `app_commands.choices` 的指令；
    - 用 `CommandTranslator(table=样例表)` 调 `await cmd.app_command.get_translated_payload(tree, translator)`，`tree` 用 `commands.Bot(command_prefix="r!", intents=discord.Intents.none()).tree`；
    - 断言 `payload["description_localizations"] == {"zh-CN": 中文, "zh-TW": 中文}`；
    - 断言参数的 `name_localizations` 和 `description_localizations`、选项的 `name_localizations` 有中文；
    - 断言 `name_localizations` 为空或没有这个键（指令名不翻）。
  - `test_translator_missing_entry_returns_none`（Review Focus 4）。
  - `test_snapshot_and_help_prefer_chinese`：表里有条目时 `health` 快照和 `help._format_command` 用中文，没有时用英文 `description`。
  - `test_every_command_is_translated[path]`：参数化在模块级 `DONE: set[str] = set()` 上（本任务为空，后面的任务往里加顶层指令名）。对 `top_level_app_commands()` 里名字在 `DONE` 中的每条指令，逐个检查它自己和所有子指令：
    - 表里有中文说明；英文和中文说明都在 1–100 字符之间；
    - 每个参数有中文名（1–32 字符，同一条指令内不重复）和中文说明；
    - 每个选项的值在 `choices` 里；
    - 每个叶子指令（不是组）至少一个例子。
  - `test_bot_installs_translator`：AST 断言 `main.py` 的 `setup_hook` 里调用了 `self.tree.set_translator(CommandTranslator())`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest -q tests/test_command_i18n.py`
Expected: FAIL（`command_i18n` 不存在）

- [ ] **Step 3: 实现**：表文件先放 `{"commands": {}, "choices": {}}`，以后各任务往里加条目

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add rinbot/i18n rinbot/rincore/command_i18n.py rinbot/main.py rinbot/cogs/health.py rinbot/cogs/help.py tests/test_command_i18n.py tests/command_tree.py
git commit -m "feat: translate command descriptions and parameters for chinese clients"
```

---

### Task 3: 旧名字改写、移到控制台的提示、停用记录迁移、组权限规则

**Files:**
- Create: `rinbot/rincore/legacy.py`
- Modify: `rinbot/main.py`（`HybridBot.get_context`）、`rinbot/cogs/errors.py`（找不到指令分支）、`rinbot/cogs/_messages.py`（链接按钮）、`rinbot/cogs/commandtoggle.py`、`rinbot/cogs/globalsettings.py`（加载时迁移）、`rinbot/cogs/giveaway.py`（`gw_list` 加 `@require(manage_guild=True)`）
- Test: `tests/test_legacy.py`、`tests/test_perms.py`（改写组权限测试）

**Interfaces:**
- Produces（`rincore/legacy.py`，不依赖 discord）：
  - `PREFIX = "r!"`。
  - `RENAMED: dict[str, str]`：spec 第 4.3 节的 16 个旧名 → 新指令路径，例如 `"warns": "warnings list"`、`"toggle": "commands toggle"`、`"automod_words": "automod words"`、`"tempban": "ban"`。
  - `REMOVED: dict[str, tuple[str, str]]`：旧名或旧路径 → `(控制台页面 slug, 页面名)`。spec 第 4.2 节每一条都要有：
    - `welcome_*` 八条 → `("welcome", "欢迎新成员")`；
    - `rr_*` 六条 → `("roles", "领取身份组")`；
    - `"automod enable"` 等六条 → `("automod", "自动审核")`；
    - `"serverlog"` → `("serverlog", "服务器事件日志")`；
    - `modlog_channel`、`warn_config` → `("moderation", "管理模块")`。
  - `DASHBOARD = "https://rin-bot.com"`；`dashboard_url(guild_id: int, slug: str) -> str` 返回 `f"{DASHBOARD}/dashboard/server/{guild_id}#{slug}"`。
  - `rewrite(content: str) -> str`：`content` 去掉前导空白后以 `PREFIX` 开头（不区分大小写），而且紧跟着的完整单词是 `RENAMED` 的键（单词后面是空白或结尾）时，把这个单词换成新路径；其他情况原样返回。
  - `migrate_disabled(names: set[str]) -> set[str]`：旧名换新名（多对一取并集），`tempban` 和 `REMOVED` 里的名字删掉，其他原样保留。
- Produces（`_messages.py`）：
  - `link_view(label: str, url: str) -> discord.ui.View`。
  - `async def send_moved(ctx, key: str) -> bool`：`key` 在 `legacy.REMOVED` 里而且 `ctx.guild` 不为空时，私密发出"已移到控制台"提示并返回 True，否则返回 False。`errors.py` 和 Task 8 的 `/automod` 组回调都调用它。
- `HybridBot.get_context(self, origin, /, *, cls=commands.Context)`：`origin` 是消息且 `rewrite(origin.content)` 有变化时，用 `copy.copy(origin)` 改它的 `content` 再交给 `super().get_context`。不改原消息对象，因为自动审核等监听器还要读原文。
- `send_moved` 发的提示：`send(ctx, embed("info", "这项设置已移到控制台", f"在控制台的「{页面名}」里修改。"), private=True, view=link_view("打开控制台", dashboard_url(ctx.guild.id, slug)))`。
- `errors.on_command_error`：`CommandNotFound` 时调用 `send_moved(ctx, ctx.invoked_with.lower())`；返回 False 时照旧不回复。
- 迁移：`CommandToggle.cog_load` 建表后，按服务器读出停用名单，用 `migrate_disabled` 算新名单，有变化就整组替换这个服务器的行。`GlobalSettings._ensure_tables` 之后对 `global_disabled_cmds` 做同样的事。两者都是幂等的，每次加载跑一遍也没关系。
- 组权限新规则（spec 第 9 节）：组有 `require` 时，组下面的每个子指令也必须有 `require`，而且它的权限关键字集合包含组的。替换 `tests/test_perms.py` 的 `test_groups_cover_subcommand_permissions`。

- [ ] **Step 1: 写失败的测试** `tests/test_legacy.py`：
  - `test_rewrite_renamed_names`：
    - `"r!warns @小明"` → `"r!warnings list @小明"`；
    - `"r!tempban @x 1d 刷屏"` → `"r!ban @x 1d 刷屏"`；
    - `"r!automod_words add 坏词"` → `"r!automod words add 坏词"`；
    - `"r!toggle play"` → `"r!commands toggle play"`。
  - `test_rewrite_edges`（Review Focus 3）：
    - `"R!WARNS"` 改写为 `"r!warnings list"`；
    - `"r!warnsx"`、`"hello r!warns"`、`"r!"`、`"r!play song"`、`""` 原样返回。
  - `test_every_removed_name_has_a_page`：`REMOVED` 正好包含 spec 4.2 的 23 个名字，每个都是五个页面 slug 之一。
  - `test_migrate_disabled`：`{"warns", "clearwarns", "play"}` → `{"warnings", "play"}`；`{"tempban", "welcome_image", "rr_add"}` → 空集合；`{"togglelist"}` → `{"commands"}`；对结果再迁移一次不变。
  - `test_get_context_rewrites_a_copy`：AST 断言 `HybridBot` 定义了 `get_context` 并调用 `copy.copy` 和 `legacy.rewrite`。
  - `test_removed_command_points_to_the_dashboard`：
    - 用假 ctx（`invoked_with="welcome_image"`、有 `guild.id=5`、`interaction=None`、`send` 记录器）调 `ErrorHandler.on_command_error(cog, ctx, commands.CommandNotFound("x"))`；
    - 断言 embed 标题 `"这项设置已移到控制台"`、正文 `"在控制台的「欢迎新成员」里修改。"`、`view` 里按钮的 url 为 `"https://rin-bot.com/dashboard/server/5#welcome"`、`delete_after == 15`；
    - `invoked_with="nope"` 时什么都不发。
  - `test_toggle_migration_rewrites_rows`：用临时 sqlite 文件跑 `CommandToggle` 的迁移函数（把迁移写成可单测的 `async def migrate_rows(db) -> None`），旧行被替换、无关行保留。
  - `tests/test_perms.py`：新规则的测试，以及 `test_giveaway_list_checks_manage_guild`（`gw_list` 带 `require(manage_guild=True)`）。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest -q tests/test_legacy.py tests/test_perms.py`
Expected: FAIL

- [ ] **Step 3: 实现**

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add rinbot tests
git commit -m "feat: keep old prefix names working and point removed settings to the dashboard"
```

---

### Task 4: 管理指令

**Files:**
- Modify: `rinbot/cogs/moderation.py`、`rinbot/i18n/commands.zh.json`
- Test: `tests/test_moderation_commands.py`、`tests/test_command_i18n.py`（`DONE` 加名字）、`tests/test_ban_args.py`（保持通过）

**Interfaces:**
- Consumes: `Duration("ban" | "mute" | "slowmode")`、`duration_autocomplete`、`choices`、`is_zh`（Task 1）；翻译表（Task 2）
- 指令签名（参数名就是英文参数名）：
  - `ban(self, ctx, member: discord.User, duration: Optional[Duration("ban")] = None, delete_days: commands.Range[int, 0, 7] = 0, *, reason: str = DEFAULT_REASON)`：有 `duration` 时走原来 `tempban` 的流程（私信、封禁、写 `tempbans`、案件动作 `"tempban"`），没有时走原来 `ban` 的流程。原来 `tempban` 只收服务器里的成员，现在不在服务器的用户也能临时封禁，此时跳过层级检查和私信。`resolve_ban_args` 照旧用于前缀调用。
  - `unban(self, ctx, user: str, *, reason: str = DEFAULT_REASON)`：`user` 是数字就当 ID，否则在封禁名单里按名字精确匹配；找不到时私密提示 `("error", "找不到这个用户", "检查一下有没有打错，或者直接填用户 ID。")`。
  - `mute(self, ctx, member: discord.Member, duration: Duration("mute") = 600, *, reason: str = DEFAULT_REASON)`。
  - `slowmode(self, ctx, duration: Duration("slowmode") = 0)`。
  - `purge(self, ctx, amount: commands.Range[int, 1, 500], member: discord.Member = None)`：去掉函数里手写的 1–500 检查。
  - `/warnings` 组：`warnings_group`（`@require(manage_messages=True)`、`guild_only`；前缀不带子指令时显示用法），子指令：
    - `list(member)`：原 `warns` 的逻辑。
    - `remove(warning: int)`：原 `delwarn` 的逻辑。
    - `clear(member)`：原 `clearwarns` 的逻辑，`@require(manage_messages=True, manage_guild=True)`。
- 补全：
  - `unban.user`：列封禁名单，`async for` 遍历 `guild.bans(limit=1000)`；结果按 `(guild_id, 时间)` 缓存 60 秒；遇到 `discord.Forbidden` / `HTTPException` 返回 `[]`。显示 `f"{user}（{user.id}）"`，值是 ID 字符串。
  - `warnings remove.warning`：本服务器最近 25 条警告，新的在前，显示 `f"#{id} {成员名} {原因前 40 字}"`，值是 int。
  - `ban.duration`、`mute.duration`、`slowmode.duration`：`duration_autocomplete(...)`。
- 删除：`tempban`、`warns`、`clearwarns`、`delwarn`、`modlog_channel`、`warn_config`。`modlog` 留到 Task 5。
- 所有保留和新增的指令：`description` 和参数说明改英文；翻译表补齐 `ban`、`unban`、`kick`、`mute`、`unmute`、`warn`、`purge`、`slowmode`、`lock`、`unlock`、`warnings`（及三个子指令）；把这 11 个顶层名字加进 `test_command_i18n.DONE`。

- [ ] **Step 1: 写失败的测试** `tests/test_moderation_commands.py`：
  - `test_moderation_command_names`：用 `command_tree.top_level_app_commands()` 取 Moderation 的顶层名字，等于 `{"ban","unban","kick","mute","unmute","warn","purge","slowmode","lock","unlock","warnings","modlog"}`；`warnings` 的子指令为 `{"list","remove","clear"}`。
  - `test_ban_takes_an_optional_duration`：`ban` 的 app 参数依次为 `member, duration, delete_days, reason`，`duration` 不是必填。
  - `test_reason_is_not_eaten_as_duration`（Review Focus 1）：`await Duration("ban")().convert(ctx, "刷屏不听劝")` 抛 `BadDuration`（这是前缀解析把 Optional 参数跳过、交给 reason 的前提）。
  - `test_purge_range`：`purge` 的 `amount` 参数 `min_value == 1`、`max_value == 500`。
  - `test_unban_autocomplete_without_permission_is_empty`（Review Focus 2）：假 guild 的 `bans()` 抛 `discord.Forbidden`，补全返回 `[]`。
  - `test_unban_autocomplete_lists_and_filters`：三个假封禁记录，输入 `"小"` 只剩名字含"小"的，值是 ID 字符串。
  - `test_warning_autocomplete_newest_first`：用临时 DB（`monkeypatch` 掉 `DB_PATH`）写入 30 条警告，返回 25 条，第一条是最新的。
  - 往 `tests/test_command_i18n.py` 的 `DONE` 里加上述 11 个名字。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest -q tests/test_moderation_commands.py tests/test_command_i18n.py`
Expected: FAIL

- [ ] **Step 3: 实现**

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest -q`
Expected: PASS（`test_ban_args.py`、`test_guild_only.py`、`test_perms.py`、`test_embed_style.py`、`test_review_fixes.py` 都要通过）

- [ ] **Step 5: 提交**

```bash
git add rinbot/cogs/moderation.py rinbot/i18n/commands.zh.json tests
git commit -m "feat: merge timed bans into /ban and group warnings with autocomplete"
```

---

### Task 5: `/case`

**Files:**
- Modify: `rinbot/rincore/cases.py`、`rinbot/cogs/moderation.py`、`rinbot/i18n/commands.zh.json`
- Test: `tests/test_cases.py`（扩充）、`tests/test_case_commands.py`

**Interfaces:**
- Produces（`rincore/cases.py`）：
  - `async def get_case(db, guild_id: int, case_no: int) -> Optional[dict]`：字典键 `case_no, action, user_id, mod_id, reason, duration, created_at`。
  - `async def recent_cases(db, guild_id: int, limit: int = 25, actions: Optional[Sequence[str]] = None) -> list[dict]`：新的在前。
  - `async def set_reason(db, guild_id: int, case_no: int, reason: str) -> bool`。
  - `async def set_duration(db, guild_id: int, case_no: int, duration: str) -> bool`。
- `/case` 组：`case_group`（`@require(manage_messages=True)`、`guild_only`），子指令：
  - `list(member: discord.User = None, page: commands.Range[int, 1, None] = 1)`：原 `modlog` 的逻辑。
  - `view(case: int)`。
  - `reason(case: int, *, reason: str)`。
  - `duration(case: int, duration: str)`：`duration` 按案件动作解析，`mute` 用 `Duration("mute")`，`tempban` 用 `Duration("ban")`；在函数里调用转换器，好按动作选上限。
  - 四个子指令都 `@require(manage_messages=True)`；`duration` 还在函数里检查：禁言案件要 `ctx.author.guild_permissions.moderate_members`，临时封禁案件要 `ban_members`，不满足时抛 `commands.MissingPermissions([...])`，交给统一报错。
- "还在生效"的判定：
  - 禁言案件：它是该成员最新的 `mute` 案件，而且成员还在服务器里、`timed_out_until` 晚于现在。
  - 临时封禁案件：它是该用户最新的 `tempban` 案件，而且 `tempbans` 表里还有这个用户的行。
  - 判定写成 `Moderation._active_until(guild, case) -> Optional[datetime]`，失效时返回 `None`。
- 文案（逐字）：
  - `view`：用管理日志里那张卡片（子项目一 `_log_case` 里的，抽成 `_case_embed(case) -> discord.Embed`，两处共用）；还在生效时多一个字段 `("剩余", f"<t:{ts}:R>")`。
  - `reason` 成功：`("success", f"案件 #{n} 的原因已更新")`；日志频道补发 `embed("warning", f"案件 #{n}：原因已更新", fields=[("之前", 旧, False), ("之后", 新, False), ("管理员", ctx.author.mention)], timestamp=utcnow)`。
  - `duration` 成功：`("success", f"案件 #{n} 将在 <t:{ts}:R> 解除")`；日志补发 `"案件 #{n}：时长已更新"`，字段"之前""之后""管理员"。
  - 不能改：`("error", "这个案件没有可以修改的时长")`。
  - 找不到：`("error", f"找不到案件 #{n}")`。
- 修改时长的副作用：禁言调用 `member.timeout(now + 秒数, reason=...)`；临时封禁 `UPDATE tempbans SET unban_at = ?`。两种都把案件的 `duration` 改成 `durations.format_duration(秒数)`。
- 补全：`view` / `reason` 列最近 25 个案件，显示 `f"#{n} {ACTION_NAMES[action]} {成员名} {原因前 30 字}"`；`duration` 只列还在生效的禁言和临时封禁，显示里加 `f" 剩 {label}"`；`duration.duration` 用 `duration_autocomplete("mute")`。
- 删除 `modlog`，`DONE` 加 `"case"`。

- [ ] **Step 1: 写失败的测试**
  - `tests/test_cases.py`：在临时 DB 上测 `get_case`、`recent_cases`（含 `actions` 过滤和顺序）、`set_reason`、`set_duration`（不存在时返回 False）。
  - `tests/test_case_commands.py`：
    - `test_case_group_shape`：`case` 子指令为 `{"list","view","reason","duration"}`；Moderation 顶层名字里没有 `modlog`。
    - `test_duration_on_expired_mute_is_refused`（Review Focus 5）：成员的 `timed_out_until` 为 `None`，调 `case duration.callback` 得到"这个案件没有可以修改的时长"。成员已离开服务器（`guild.get_member` 返回 `None`）、临时封禁行已删时同样。
    - `test_duration_updates_mute`：生效中的禁言改成 `2h` 后，`member.timeout` 被以约 `now+7200` 调用，案件 `duration` 变成 `"2小时"`，回复是成功文案。
    - `test_duration_updates_tempban`：`tempbans.unban_at` 更新。
    - `test_duration_needs_matching_permission`：作者没有 `moderate_members` 时抛 `MissingPermissions`。
    - `test_reason_updates_and_logs`：原因写入数据库，日志频道收到"案件 #n：原因已更新"。
    - `test_unknown_case`：返回"找不到案件 #99"。
    - `test_case_autocomplete_active_only`：`duration` 的补全只含生效中的案件。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest -q tests/test_cases.py tests/test_case_commands.py`
Expected: FAIL

- [ ] **Step 3: 实现**

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add rinbot tests
git commit -m "feat: add /case to view cases and edit reasons and durations"
```

---

### Task 6: 音乐

**Files:**
- Modify: `rinbot/cogs/music.py`、`rinbot/i18n/commands.zh.json`
- Test: `tests/test_music_commands.py`

**Interfaces:**
- `/playlist` 组（不需要权限，`guild_only`），子指令 `save(*, name: str = "default")`、`load(*, name: str = "default")`、`list()`、`delete(*, name: str)`，逻辑分别搬自 `saveq`、`loadq`、`queues`、`delqueue`，然后删掉这四条旧指令。
- `loop`：参数改为 `mode: Optional[str] = None`，加 `@app_commands.choices(mode=[Choice(name="Off", value="off"), Choice(name="Single track", value="single"), Choice(name="Whole queue", value="queue")])`；前缀调用照旧接受这三个值，其他值私密提示 `("error", "参数格式不对", "用法：`r!loop [off|single|queue]`")`。
- 数字范围：`volume(level: commands.Range[int, 0, 150] = None)`（去掉手写检查）；`queue(page: commands.Range[int, 1, None] = 1)`。
- 补全：
  - `playlist load.name`、`playlist delete.name`：本服务器的存档，显示 `f"{name}（{n} 首）"`，值是名字。
  - `remove.position`、`move.from_pos`、`move.to_pos`：当前队列，显示 `f"{i}. {歌名前 80 字}"`，值是 int。
  - 没有队列或存档时返回 `[]`。
- 15 条平铺指令和 `/playlist` 的说明、参数改英文，翻译表补齐；`choices` 补 `off`、`single`、`queue`；`DONE` 加这 16 个名字。
- 机器人里提到 `/saveq`、`/queues` 的提示文字改成 `/playlist save`、`/playlist list`。

- [ ] **Step 1: 写失败的测试** `tests/test_music_commands.py`：
  - `test_music_command_names`：16 个顶层名字；`playlist` 子指令 `{"save","load","list","delete"}`；没有 `saveq`、`loadq`、`queues`、`delqueue`。
  - `test_loop_choices`：`loop` 的 `mode` 参数有三个选项，值为 `off`、`single`、`queue`。
  - `test_volume_range`：`min_value == 0`、`max_value == 150`。
  - `test_queue_position_autocomplete`：假状态里有 3 首歌，输入 `"2"` 时包含 `"2. 歌名"`；空队列时返回 `[]`（Review Focus 2）。
  - `test_playlist_autocomplete_empty`：没有存档时返回 `[]`（临时 DB）。
  - `DONE` 加名字。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest -q tests/test_music_commands.py tests/test_command_i18n.py`
Expected: FAIL

- [ ] **Step 3: 实现**

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add rinbot tests
git commit -m "feat: group saved queues under /playlist and let music commands pick from the queue"
```

---

### Task 7: 抽奖、通用、等级和 `/help 指令`

**Files:**
- Modify: `rinbot/cogs/giveaway.py`、`rinbot/cogs/general.py`、`rinbot/cogs/leveling.py`、`rinbot/cogs/help.py`、`rinbot/i18n/commands.zh.json`
- Test: `tests/test_giveaway_commands.py`、`tests/test_help_command.py`

**Interfaces:**
- 抽奖：
  - `gw_start(self, ctx, duration: Duration("giveaway"), winners: commands.Range[int, 1, 20] = 1, *, prize: str)`：删掉函数里的时长解析和 1–20 检查。
  - `gw_end(giveaway: int)`、`gw_reroll(giveaway: int, count: commands.Range[int, 1, 20] = 1)`：参数由 `giveaway_id` 改名为 `giveaway`。
  - 补全：`end` 列本服务器进行中的抽奖，显示 `f"{奖品前 60 字} 剩 {label}"`；`reroll` 列已结束的，显示 `f"{奖品前 60 字} 已结束"`；值都是 ID。
- 通用：`roll(sides: commands.Range[int, 2, 1000] = 6)`，去掉手写检查。
- 等级：`leaderboard(page: commands.Range[int, 1, None] = 1)`。
- `/help`：
  - `help(self, ctx, *, command: Optional[str] = None)`；不填时行为不变。
  - 填了时按路径找指令：先 `bot.get_command(path)`，找不到再试 `path.lstrip("/")`。找不到或 `visible(...)` 为假时，私密提示 `("error", "找不到这条指令")`。
  - 找到时私密回复 `embed("info", f"/{path}", zh_description(path) or 英文说明, fields=[...])`，字段依次为：
    - `("用法", f"`/{path} {参数}`", False)`：参数用中文名，必填写 `<名字>`，可选写 `[名字]`；
    - `("例子", "\n".join(examples), False)`；
    - `("需要的权限", permission_list(...))`：没有就不加。
  - 补全：这个人能看到的所有指令路径（含子指令，用 `bot.walk_commands()` 过滤 hidden、主人指令和 `visible`），显示 `f"/{path} {中文说明前 50 字}"`，值是路径。
  - 用法行的中文参数名写成 `help.usage_zh(command) -> str`。
- `DONE` 加 `giveaway`、`status`、`roll`、`avatar`、`help`、`rank`、`leaderboard`。

- [ ] **Step 1: 写失败的测试**
  - `tests/test_giveaway_commands.py`：
    - `start` 参数依次为 `duration, winners, prize`，`winners` 在 1–20；
    - `end` 的补全只列进行中的，`reroll` 的只列已结束的（临时 DB，`monkeypatch` 掉 `DB_PATH`）；
    - `list` 带 `manage_guild` 检查。
  - `tests/test_help_command.py`：
    - `test_help_detail_card`：用翻译表里的 `ban` 条目，`/help ban` 的卡片标题 `"/ban"`，用法字段 `"`/ban <成员> [时长] [删除消息天数] [原因]`"`（按参数实际顺序），有例子字段，权限字段为 `"「封禁成员」"`；
    - `test_help_unknown_or_hidden`：`"nope"` 和普通成员查 `kick` 都得"找不到这条指令"；
    - `test_help_autocomplete_respects_permissions`：普通成员的候选里没有 `kick`，有 `roll`。
  - `DONE` 加名字。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest -q tests/test_giveaway_commands.py tests/test_help_command.py tests/test_command_i18n.py`
Expected: FAIL

- [ ] **Step 3: 实现**

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add rinbot tests
git commit -m "feat: pick giveaways from lists and explain a single command with /help"
```

---

### Task 8: 迎新、自动审核、指令开关，删掉交给控制台的指令

**Files:**
- Modify: `rinbot/cogs/welcome.py`、`rinbot/cogs/reactionroles.py`、`rinbot/cogs/serverlog.py`、`rinbot/cogs/automod.py`、`rinbot/cogs/commandtoggle.py`、`rinbot/i18n/commands.zh.json`
- Test: `tests/test_feature_groups.py`

**Interfaces:**
- **迎新**：
  - `/welcome` 组（`@require(manage_guild=True)`、`guild_only`），子指令 `setup`（原 `welcome_setup` 的面板）、`test`（原 `welcome_test`），两个都 `@require(manage_guild=True)`。
  - 删掉其余 8 条 `welcome_*`。
  - 迎新的事件监听（加入、离开、`_build_welcome_embed` 等）不动。
- **身份组面板**：删掉 6 条 `rr_*` 指令。按钮回调、面板重建、`on_raw_*` 监听保留，控制台发的面板继续能用。
- **审计日志**：删掉 `serverlog` 组和 7 个子指令；事件监听、`_send`、`get_config` 保留。
- **自动审核**：
  - `/automod` 组保留，前缀不带子指令时仍显示配置面板。
  - 新增 `status` 子指令，显示同一个面板。
  - 删掉 `enable`、`disable`、`toggle`、`log`、`mute_duration`、`spam_config`。前缀用户打 `r!automod enable` 这类旧子指令时，组回调发现 `f"automod {ctx.subcommand_passed}"` 在 `legacy.REMOVED` 里，就调用 `send_moved(ctx, f"automod {ctx.subcommand_passed}")`，返回 True 时就不再显示面板。
  - 嵌套组 `words`、`whitelist`、`ignore`，各有 `add`、`remove`、`list`，逻辑搬自原来的 `automod_words`、`automod_whitelist`、`automod_ignore` 里对应 action 的分支，然后删掉这三条旧指令。
    - `words add(*, word: str)`、`words remove(*, word: str)`；
    - `whitelist add(domain: str)`、`whitelist remove(domain: str)`；
    - `ignore add(channel: discord.TextChannel = None, role: discord.Role = None)`、`ignore remove(...)` 同参数；
    - 所有子指令都 `@require(manage_guild=True)`、`guild_only`。
  - 补全：`words remove.word` 列已有的违禁词；`whitelist remove.domain` 列已有的白名单域名。
- **指令开关**：
  - `/commands` 组（`@require(manage_guild=True)`、`guild_only`），子指令：
    - `disable(command: str)`、`enable(command: str)`；
    - `list()`：原 `togglelist`；
    - 隐藏的纯前缀子指令 `toggle(command: str)`（`with_app_command=False`、`hidden=True`）：原 `/toggle` 的来回切换逻辑。
  - `disable` 和 `enable` 只接受顶层指令名。`PROTECTED_COMMANDS` 改为 `{"commands", "help"}` 加 9 条开发指令名；保护名单里的指令被停用时私密提示 `("error", "这条指令不能停用")`。
  - 补全：`disable` 列还开着的、不在保护名单里的顶层指令；`enable` 列已停用的；显示 `f"{名字} {中文说明前 50 字}"`。
  - 删掉 `toggle`、`togglelist` 两条旧指令。
- 机器人里提到 `/rr_add`、`/serverlog …`、`/automod enable`、`/welcome_setup`、`/welcome_test`、`/toggle` 的提示文字，改成新指令名或"在控制台里修改"。
- 翻译表补齐 `welcome`、`automod`、`commands` 三个组及全部子指令；`DONE` 加这三个名字。

- [ ] **Step 1: 写失败的测试** `tests/test_feature_groups.py`：
  - `test_welcome_group`：`welcome` 子指令 `{"setup","test"}`；Welcome 没有其他顶层指令。
  - `test_reaction_roles_and_serverlog_have_no_commands`：两个 cog 没有任何顶层指令，但 `ReactionRoles` 的按钮回调和 `ServerLog` 的事件监听方法还在（按方法名断言）。
  - `test_automod_shape`：顶层只有 `automod`；子指令和子组为 `{"status","words","whitelist","ignore"}`；三个子组各自是 `{"add","remove","list"}`。
  - `test_automod_removed_subcommand_points_to_dashboard`：前缀调用组回调、`ctx.subcommand_passed="enable"` 时，发出"已移到控制台"提示，链接 `#automod`。
  - `test_commands_group`：斜杠子指令 `{"disable","enable","list"}`；前缀子指令里还有 `toggle`；`toggle` 不出现在 app command 里。
  - `test_protected_commands_cannot_be_disabled`：`disable` 传 `"help"` 得到"这条指令不能停用"。
  - `test_word_autocomplete_lists_existing_words`：用假配置测。
  - `DONE` 加名字。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest -q tests/test_feature_groups.py tests/test_command_i18n.py`
Expected: FAIL

- [ ] **Step 3: 实现**

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest -q`
Expected: PASS（`test_embed_style.py`、`test_review_fixes.py`、`test_guild_only.py`、`test_perms.py` 都要通过；`test_review_fixes.py` 里用到的 `welcome_test` 换成 `/welcome test` 的回调）

- [ ] **Step 5: 提交**

```bash
git add rinbot tests
git commit -m "feat: group welcome, automod lists and command toggles and hand duplicated settings to the dashboard"
```

---

### Task 9: 收口：完整指令表、全量翻译、控制台文案

**Files:**
- Modify: `tests/test_command_i18n.py`（`DONE` 改为全部顶层指令）、`website/templates/index.html:744`、`website/static/js/modules/utility.js:66`、`website/routes.py:2267, 2793`
- Test: `tests/test_command_map.py`

**Interfaces:**
- Consumes: 前面所有任务。

- [ ] **Step 1: 写失败的测试** `tests/test_command_map.py`：
  - `test_top_level_commands_are_the_38`：`top_level_app_commands()` 的名字集合等于 spec 第 4.1 节的 38 个。
  - `test_removed_commands_are_gone`：`legacy.REMOVED` 和 `legacy.RENAMED` 的所有键都不是顶层斜杠指令名（`automod enable` 这类按空格前的第一个词判断时跳过已有的组名）。
  - `test_renamed_targets_exist`：`RENAMED` 的每个值，`bot.get_command(值)` 都能找到。用一个不联网的 `commands.Bot` 实例把所有 cog 类的指令加进去，不调用 `add_cog`，避免触发 `cog_load`。
  - `test_dashboard_texts_use_new_names`：`index.html` 不再出现 `/tempban`；`utility.js` 和 `routes.py` 不再出现 `/toggle`（改成 `/commands`）。
  - `tests/test_command_i18n.py`：`DONE` 改成"全部顶层指令"，以后新加的指令自动受约束。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest -q tests/test_command_map.py tests/test_command_i18n.py`
Expected: FAIL（网页文案还是旧名）

- [ ] **Step 3: 改网页文案**（主页的 `/tempban` 改成 `/ban`，指令页和 `routes.py` 的 `/toggle` 改成 `/commands`）；补上测试暴露出来的漏翻条目

- [ ] **Step 4: 运行三套测试和导入检查，确认全部通过**

Run: `python -m pytest -q; cd website && python -m pytest -q tests && node --test tests/*.test.cjs`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add rinbot website tests
git commit -m "feat: lock the 38-command map and full chinese translations"
```

---

## 收尾（执行完全部任务后）

- 最终整体审查，修掉严重和重要问题。
- 推送前按用户的固定要求列出全部待推送提交的完整标题和说明，等用户确认。
- 部署后提醒用户在开发服务器发 `r!sync global`，再按 spec 第 1 节的成功标准检查。
