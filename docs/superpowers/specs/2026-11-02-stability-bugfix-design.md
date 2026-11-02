# 子项目 1：Bug 修复与稳定性 — 设计

日期：2026-11-02
状态：待用户审阅

## 背景与目标

RinBot 将作为**公开、多服务器、中英双语**的 Discord bot 运营。本子项目是路线图的第一步（之后依次为：多语言基础 → 官网改版 → 新功能逐个立项），只修复现有问题、提升多服务器下的稳定性，**不改用户可见文案、不加新功能**。

**生产约束（最高优先级）：** bot 当前正在生产服务器（192.168.2.18，`discordbot.service` / `mysite.service`）上服务真实用户。任何改动必须：先有失败测试再修复；部署前自动做语法/导入检查，失败则不重启服务；可一步回滚；数据库迁移只增不删、可重复执行。

**成功标准：**
1. 下文列出的每个问题都有对应修复，纯逻辑部分有自动化测试覆盖且全部通过。
2. 网页仪表盘修改设置后 ≤ 5 秒在 bot 生效，bot 不再整表轮询配置。
3. 部署为 `git push prod master` 一条命令，部署失败时线上服务保持旧版本运行。
4. 上线后两服务日志无新增异常，开发服务器手动验收清单全部通过。

## 第 1 部分：基础设施

### 1.1 共享包 `rinbot/rincore/`

bot 与网页共用。网页已用 `BOT_DIR` 指向 `rinbot/`，在 `website/routes.py` 顶部将 `BOT_DIR` 加入 `sys.path` 后 `import rincore`。

| 模块 | 职责 |
|---|---|
| `rincore/storage.py` | 集中登记全部 `.db` 路径（替代散落在各 cog 与 `routes.py` 的常量来源，旧常量保留并改为引用这里）；`enable_wal(paths)` 对每个库执行 `PRAGMA journal_mode=WAL`（持久化，幂等）。bot `setup_hook` 开头与网页启动时各调用一次。 |
| `rincore/sync.py` | 变更日志。见 1.2。 |
| `rincore/textmatch.py` | 违禁词归一化与匹配、链接/邀请识别（纯函数）。 |
| `rincore/durations.py` | 时长解析与格式化（合并 moderation 与 giveaway 中重复的 `_parse_duration` / `_format_*`，行为以 giveaway 版的严格解析为准：`1d12h` 合法、单位不可重复、上限 365 天）。 |
| `rincore/roles.py` | 单选身份组的增删计算（纯函数）。 |

不改动现有 130 处 `aiosqlite.connect(...)` 调用：sqlite3 默认 5 秒 busy 超时已足够，WAL 解决读写互相阻塞即可。

### 1.2 配置变更同步（变更日志）

- 新库 `rinbot/sync.db`，表 `changes(id INTEGER PRIMARY KEY AUTOINCREMENT, module TEXT NOT NULL, guild_id INTEGER NOT NULL, created_at REAL NOT NULL)`。
- **网页侧** `await notify(module, guild_id)`：插入一行。全局设置用 `guild_id = 0`。
- **bot 侧** `ChangeWatcher`：
  - 启动时记下当前最大 `id` 作为游标（启动时各 cog 已全量加载配置，无需回放）。
  - 每 3 秒 `SELECT id, module, guild_id FROM changes WHERE id > ? ORDER BY id`，按 `(module, guild_id)` 去重后调用已注册回调 `async def reload(guild_id)`；回调异常只记日志，不影响其他回调与游标推进。
  - 每小时删除 `created_at` 早于 24 小时的行。
  - cog 通过 `bot.change_watcher.register(module, callback)` 在 `cog_load` 注册，`cog_unload` 时注销。
- **模块名（固定字符串）：** `welcome`、`automod`、`moderation`、`music`、`botlog`、`serverlog`、`reactionroles`、`commands`、`global`。
- 删除以下整表轮询循环，改为注册回调：
  - `automod._refresh`（15s）→ `automod`：重载该服务器一行配置
  - `serverlog._refresh`（20s）→ `serverlog`：重载该服务器一行配置
  - `commandtoggle.refresh_loop`（15s）→ `commands`：重载该服务器禁用指令集合
  - `botlog._refresh`（30s）→ `botlog`：重载该服务器一行配置
  - `botconfig.check_presence`（30s）→ `global`：读取 `bot_personalizer` 并应用在线状态（保留现有 hash 比对，避免重复调用 API）
  - `globalsettings._tick`（10s）**保留循环**，因为它还负责发送待处理公告；只移除其中的 `_reload()`，改为 `global` 回调重载维护模式与黑名单
- `health.py` 的 30 秒循环是写健康状态，不属于配置轮询，保留。

### 1.3 测试

- 新增 `requirements-dev.txt`（`pytest`、`pytest-asyncio`）与 `tests/`，`pytest.ini` 设 `asyncio_mode = auto`、`testpaths = tests`。
- 只测纯逻辑与数据库读写（用 `tmp_path` 临时库），不连接 Discord。
- 每个修复遵循：先写失败测试 → 修复 → 测试通过。

### 1.4 部署流水线

服务器上：
- 裸仓库 `/root/rinbot.git`，本地添加 remote `prod = root@192.168.2.18:/root/rinbot.git`（SSH 使用 `~/.ssh/rinbot_ed25519`，在本地 `~/.ssh/config` 为该主机配置 `IdentityFile` 与 `IdentitiesOnly yes`）。
- `hooks/post-receive`，仅处理 `master`，按序执行，**任一步失败则退出且不重启服务**：
  1. `git --work-tree=/root/rinbot-src checkout -f master`
  2. **预检**（在 `/root/rinbot-src` 内）：`python3 -m compileall -q rinbot website`；`python3 -m pytest -q`；导入冒烟测试：`cd rinbot && python3 -c "import importlib,os; [importlib.import_module('cogs.'+f[:-3]) for f in os.listdir('cogs') if f.endswith('.py') and not f.startswith('_')]"`（需能找到真实 `config.py`，因此冒烟测试前把 `/root/rinbot/config.py` 临时复制进检出目录，结束后删除）。
  3. `rsync -a --delete` 将 `rinbot/` → `/root/rinbot/`、`website/` → `/root/website/`，排除：`*.db`、`*.db-wal`、`*.db-shm`、`*.db-journal`、`config.py`、`uploads/`、`health.json`、`*.log`、`__pycache__/`、`*.bak*`、`.env`。
  4. 若本次推送改动了 `rinbot/requirements.txt`：`pip3 install --break-system-packages -r /root/rinbot/requirements.txt`（与服务器现有依赖安装方式一致）。
  5. `systemctl restart discordbot mysite`，等待 5 秒，输出两服务 `is-active` 与最近 20 行日志。
- 服务器安装 `pytest`、`pytest-asyncio`（同样 `--break-system-packages`），使预检可在生产同平台（aarch64 / Linux）运行。
- **首次部署前**：`tar czf /root/deploy-backups/pre-rincore-<时间戳>.tar.gz /root/rinbot /root/website`（含数据库）。首次推送内容为基线提交 `bf2eb45`，用于验证流水线本身：rsync 后代码文件应与现有文件一致，仅新增 `config.example.py`；服务器上的 `*.bak*` 文件在排除列表中，不会被删除。基线不含 `tests/`，因此首次推送的预检中 pytest 步骤在 `tests/` 不存在时跳过。

### 1.5 配置文件小修（服务器上手工改，`config.py` 不入库）

- `website/config.py`：删除无条件的 `os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"`，由 `main.py` 中已有的 `RINBOT_ALLOW_HTTP` 逻辑控制（生产不设该变量 → 走 HTTPS 校验；cloudflared 对外为 HTTPS）。同步修改 `config.example.py`。
- 修改前备份为 `config.py.bak-<时间戳>`。上线后验证网页登录流程正常；若 OAuth 回调因内部 HTTP 报错，回滚此行并在 `mysite.service` 设置 `Environment=RINBOT_ALLOW_HTTP=1` 后再调查。

## 第 2 部分：bot 模块修复

| 模块 | 问题 | 修复 |
|---|---|---|
| leveling | 升级提示发送失败（无频道发言权限）时，异常发生在 `commit` 之前，经验与等级更新全部丢失 | 先 `commit`，再在 `try/except (Forbidden, HTTPException)` 中发送升级提示 |
| leveling | PIL 画等级卡在事件循环中同步执行，阻塞 bot | `await asyncio.to_thread(self.generate_cute_rank_card_bytes, ...)` |
| leveling | `self.cooldowns` 只增不减 | 每次写入时若字典超过 5000 项，清除早于 `cooldown_sec` 的条目 |
| welcome | PIL 画欢迎卡同步阻塞 | `_render_card_file` 中 `asyncio.to_thread(self._generate_welcome_card, ...)` |
| welcome | 自动身份组逐个 `add_roles` | 一次 `add_roles(*roles)`；`Forbidden` 时记日志 |
| welcome | 开启成员审核（Membership Screening）的服务器，新人未通过规则就被发身份组 | `on_member_join` 时若 `member.pending` 为真则跳过发身份组；新增 `on_member_update` 监听 `before.pending and not after.pending` 时发放。欢迎消息仍在加入时发送 |
| welcome | 欢迎/道别 `channel.send` 无异常处理 | 捕获 `Forbidden/HTTPException` 并记日志 |
| automod | 违禁词子串匹配误杀（`ass`→`class`），且可用全角/零宽/空格绕过 | 见 2.1 |
| automod | 链接过滤只识别 `http(s)://` | 见 2.1 |
| automod | 刷屏只禁言不删消息 | 刷屏缓存同时记录消息 ID；触发时 `channel.delete_messages` 批量删除该窗口内消息（仅 14 天内消息，失败则逐条尽力删除） |
| automod | 大写轰炸不写审核日志 | 补 `_log_action` |
| automod | `_msg_cache` / `_repeat_cache` 只增不减 | 每 10 分钟清除最近一次记录早于 60 秒的用户条目与空服务器条目 |
| moderation | 案件编号全局自增 | 见 2.2 |
| moderation | `ban` 只能封禁当前成员 | 参数改为 `discord.User`；目标是成员时才做层级检查与私信；新增可选参数 `delete_days: int = 0`（0–7），用 `guild.ban(user, delete_message_seconds=delete_days*86400)` |
| moderation | `tempban` 使用已弃用的 `delete_message_days` | 改 `delete_message_seconds=0` |
| moderation | 私信通知只捕获 `Forbidden` | 捕获 `(Forbidden, HTTPException)` |
| giveaway | 每次点击参与都编辑原消息，大型抽奖触发限流 | 点击只回复 ephemeral；人数标签改为节流更新：每个抽奖最多每 5 秒编辑一次，用 `asyncio` 延迟任务合并多次点击 |
| reactionroles | 任意消息的任意反应都查一次数据库 | 启动时加载所有面板 `message_id` 到内存集合，不在集合中的直接返回 |
| reactionroles | 网页修改/删除面板后 bot 缓存不失效 | 注册 `reactionroles` 同步回调，按服务器重载该服务器的面板 |
| reactionroles | 反应模式不支持单选（exclusive） | 加反应时若面板 exclusive：用 `rincore.roles` 计算需移除的同面板身份组并移除；尽力移除该用户在此消息上的其他映射反应（需要“管理消息”权限，失败忽略） |
| musicconfig | 同步 `sqlite3` 读库，锁等待最长阻塞事件循环 2 秒 | 启动时全量加载到内存字典；`get_config` 读内存；注册 `music` 同步回调按服务器重载；`set_config` 写库后更新内存 |
| globalsettings | 黑名单/维护模式不拦截组件交互（音乐控制、抽奖、身份组按钮） | `GlobalSettings` 暴露 `blocked_reason(user_id) -> str | None`；`NowPlayingView`、`SearchView`、`GiveawayEntryButton`、`netease` 的 `_OwnerView` 的 `interaction_check`，以及 `reactionroles.on_interaction`，调用它并以 ephemeral 回复拒绝 |
| globalsettings | 网页“全局禁用指令”写入 `global_disabled_cmds` 表，但 bot 从不读取，开关无效 | `_reload` 一并加载该表为集合；`_global_check` 对非主人拒绝被全局禁用的指令（按 `ctx.command.qualified_name.split()[0]` 判断），ephemeral 提示“该指令已被全局停用” |
| errors | 完整 traceback 发到各服务器日志频道（泄露服务器路径） | 生成 8 位错误编号；完整 traceback 只发到开发服务器（`DEV_GUILD_ID`）的 bot 日志，并打印到 journal；用户与所在服务器日志只看到“出错了（错误编号 XXXX）” |
| 全局 | 依赖服务器的指令在私信中调用报错 | 为所有使用 `ctx.guild` 的指令加 `@commands.guild_only()`（`errors._friendly` 已对 `NoPrivateMessage` 给出友好提示，无需改动） |
| 清理 | 根目录 `rinbot/serverlog.py`、`rinbot/help.py` 与 `cogs/` 下重复 | 确认无 import 引用后删除 |
| 清理 | `diag_automod.py` 调试脚本混在主目录 | 移到 `rinbot/tools/` |

### 2.1 违禁词与链接匹配（`rincore/textmatch.py`）

`normalize(text)`：`unicodedata.normalize("NFKC")` → 小写 → 移除零宽字符（U+200B–U+200D、U+2060、U+FEFF）。

`find_badword(text, words) -> str | None`：
- 文本与每个词都先 `normalize`；空词跳过。
- 词全部由 ASCII 字母/数字组成：在归一化文本上用 `(?<![a-z0-9])词(?![a-z0-9])` 匹配（整词）。
- 其他词（含中文等）：在归一化文本上子串匹配；再在“去除所有空白与常见分隔符（`.-_*·`）后的文本”上子串匹配。
- 返回命中的原始词（用于日志）。

`find_links(text) -> list[str]`：识别
- `https?://\S+`
- 无协议域名：`(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}(?:/\S*)?`，要求顶级域为字母且整体不在邮箱 `@` 之后、不是纯数字版本号（如 `1.2.3`）。
- Discord 邀请：`discord.gg/…`、`discord.com/invite/…`、`discordapp.com/invite/…`（被上一条覆盖，单独列出用于测试）。

`host_of(link)` 补全协议后用 `urlparse` 取主机名；白名单匹配沿用现有规则（主机等于或为其子域）。

测试必须覆盖：`class` 不命中 `ass`；`ＡＳＳ`（全角）命中；`a​ss` 命中；`违 禁 词`、`违.禁.词` 命中中文词 `违禁词`；`example.com/x`、`www.example.com`、`discord.gg/abc` 被识别；`me@example.com`、`v1.2.3`、`3.14` 不被识别；白名单 `example.com` 放行 `cdn.example.com`、不放行 `badexample.com`。

### 2.2 每服务器案件编号（moderation）

- 迁移（`cog_load` 内，幂等）：若 `mod_cases` 无 `case_no` 列，则 `ALTER TABLE mod_cases ADD COLUMN case_no INTEGER`；对 `case_no IS NULL` 的行，按 `guild_id` 分组、按 `id` 升序编号（续接该服务器已有最大 `case_no`）；创建唯一索引 `(guild_id, case_no)`。
- 新建案件：在同一事务中 `SELECT COALESCE(MAX(case_no),0)+1 FROM mod_cases WHERE guild_id=?` 后插入；`BEGIN IMMEDIATE` 防并发重复。
- 所有面向用户的“案件 #N”与 `modlog`、网页 `/moderation/cases` 返回与展示改用 `case_no`。`id` 保留为内部主键。
- 测试：两个服务器交错插入旧数据 → 迁移后各自从 1 连续；重复执行迁移不改变结果；迁移后新建案件续号。

## 第 3 部分：网页后台修复（`website/routes.py`）

| 问题 | 修复 |
|---|---|
| `fetch_bot_guild_ids` 不分页，bot 超过 200 个服务器后仪表盘显示不全 | 循环 `?limit=200&after=<最后一个 id>` 直到返回不足 200；结果进程内缓存 60 秒；失败时返回上次缓存（若有） |
| 保存后 bot 最长 30 秒才生效 | 每个写入型接口成功写库后 `await sync.notify(module, gid)`：welcome（含图片上传/删除）、automod、moderation、music、botlog、serverlog、reactionroles（创建/删除面板）、commands（单个与批量开关）、全局（maintenance、blacklist、personalizer、username、avatar → `global`, 0） |
| 案件列表显示全局 id | 返回并展示 `case_no` |
| WAL | 启动时（`ensure_tables` 之前）调用 `rincore.storage.enable_wal()` |

测试：分页函数抽成接收“取页函数”参数的纯协程，用假数据（450 个服务器）验证返回完整集合；`notify` 写入后 `ChangeWatcher` 能读到并去重。

## 第 4 部分：上线与验收

1. 本地 `pytest` 全绿后才推送。
2. 服务器全量备份（见 1.4）。
3. 搭建 `prod` 裸仓库与 hook，推送基线 `bf2eb45` 验证流水线（服务应正常重启、行为不变）。
4. 修复按模块分提交（每提交自带测试），全部完成后一次推送上线；hook 预检任一失败即中止。
5. 服务器手改 `website/config.py`（1.5）。
6. 观察两服务日志 10 分钟，然后在开发服务器手动验收：
   - 在禁止 bot 发言的频道聊天至升级 → 经验正常增加（`/rank` 可见），无报错
   - `/rank`、欢迎测试卡在画图时 bot 仍能即时响应其他指令
   - 违禁词（英文整词、全角、中文加空格）与 `class` 误杀用例；`www.` / `discord.gg` 链接被拦，白名单子域放行
   - 刷屏触发后窗口内消息被删除
   - `/ban` 用不在服务器的用户 ID；`modlog` 显示本服务器从 1 开始的案件号（旧案件已重编号）
   - 抽奖多人连续点击无报错，人数标签最终正确
   - 按钮面板与反应面板的单选模式；网页删除面板后反应不再发身份组
   - 网页修改自动审核/音乐 DJ 设置，5 秒内生效
   - 黑名单用户点击音乐控制按钮被拒
   - 私信中调用 `/rank` 得到友好提示
   - 网页登录、保存设置流程正常
7. **回滚：** `git revert` 或 `git push -f prod <上一个好提交>:master` 重新部署；数据库迁移只新增列与索引，旧代码可直接读取。极端情况用 1.4 的 tar 备份还原。

## 不在范围内

- 所有新功能、文案改写与多语言（子项目 2）。
- 官网与仪表盘视觉改版（子项目 3）。
- 合并 bot 与网页进程、更换数据库。
- 推送到 GitHub（按用户节奏单独确认）。
