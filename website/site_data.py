"""官网各页面共用的数据：邀请链接、邀请时要的权限、指令分组和权限显示名。

模板和测试都从这里读，改一处就够了。
"""

CLIENT_ID = 1352551616427069492
INVITE_PERMISSIONS = 1374694796438


def invite_url(permissions: int = INVITE_PERMISSIONS) -> str:
    """邀请小凛的链接；permissions 是 Discord 权限位的整数。"""
    return (
        f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}"
        f"&permissions={permissions}&integration_type=0&scope=bot+applications.commands"
    )


# 邀请权限页的五组，顺序就是页面上的顺序
PERMISSION_GROUPS = [
    {"key": "msg", "zh": "发消息（每个功能都要）", "en": "Messages (every feature needs these)"},
    {"key": "voice", "zh": "放歌", "en": "Music"},
    {"key": "roles", "zh": "身份组", "en": "Roles"},
    {"key": "mod", "zh": "管理和自动审核", "en": "Moderation and AutoMod"},
    {"key": "log", "zh": "服务器日志", "en": "Server log"},
]


def _perm(bit, group, zh, en, why_zh, why_en, lose_zh, lose_en):
    return {"bit": bit, "group": group, "zh": zh, "en": en,
            "why_zh": why_zh, "why_en": why_en, "lose_zh": lose_zh, "lose_en": lose_en}


# 邀请链接里的 16 项权限；名称用 Discord 自己的中文叫法，用途和后果都对过代码
PERMISSIONS = [
    _perm(10, "msg", "查看频道", "View Channels",
          "找到你在控制台里选的欢迎、日志频道", "Find the welcome and log channels you pick in the dashboard",
          "小凛看不到频道，几乎所有功能都会失效", "Rin can’t see channels, so almost nothing works"),
    _perm(11, "msg", "发送消息", "Send Messages",
          "发欢迎消息、日志、抽奖和身份组面板", "Post welcomes, logs, giveaways and role panels",
          "小凛没法在频道里说话，几乎所有功能都会失效", "Rin can’t talk in channels, so almost nothing works"),
    _perm(38, "msg", "在子区中发送消息", "Send Messages in Threads",
          "在子区里用指令时也能回复", "Reply when a command is used in a thread",
          "在子区里小凛不会回复", "Rin won’t reply inside threads"),
    _perm(14, "msg", "嵌入链接", "Embed Links",
          "小凛的消息都是带颜色边条的卡片", "Every message Rin sends is a card with a coloured edge",
          "消息会变成一堆没排版的文字", "Messages turn into unformatted text"),
    _perm(15, "msg", "附加文件", "Attach Files",
          "发欢迎图卡和等级卡图片", "Send welcome cards and rank card images",
          "欢迎图卡和 /rank 等级卡发不出来", "Welcome cards and /rank images can’t be sent"),
    _perm(16, "msg", "阅读消息历史", "Read Message History",
          "开奖时找到原来的抽奖消息，/purge 只删某个人时往前翻",
          "Find the giveaway message when drawing, and look back when /purge targets one member",
          "抽奖到点开不了奖，/purge 不能只删某个人的消息",
          "Giveaways can’t be drawn, and /purge can’t target one member"),
    _perm(20, "voice", "连接", "Connect",
          "进入你所在的语音频道", "Join your voice channel",
          "不能放歌", "Music won’t work"),
    _perm(21, "voice", "说话", "Speak",
          "在语音频道里放出声音", "Play sound in the voice channel",
          "进了语音频道也没声音", "Rin joins but no one hears anything"),
    _perm(25, "voice", "使用语音活动", "Use Voice Activity",
          "在要求按键说话的语音频道里也能出声", "Be heard in voice channels that require push-to-talk",
          "在要求按键说话的频道里没声音", "No sound in push-to-talk channels"),
    _perm(28, "roles", "管理身份组", "Manage Roles",
          "给新成员发身份组、身份组面板发放身份组、/lock 锁频道",
          "Give roles to new members and from role panels, and lock channels with /lock",
          "迎新自动身份组和身份组面板不能用，/lock 也会失败",
          "Join roles and role panels stop working, and /lock fails"),
    _perm(13, "mod", "管理消息", "Manage Messages",
          "自动审核删掉违规消息，/purge 批量删除",
          "Delete messages that break AutoMod rules, and bulk delete with /purge",
          "自动审核删不掉违规消息，/purge 不能用", "AutoMod can’t delete messages, and /purge fails"),
    _perm(4, "mod", "管理频道", "Manage Channels",
          "/lock、/unlock 锁频道，/slowmode 设慢速模式", "Lock channels with /lock and /unlock, set /slowmode",
          "/lock、/unlock 和 /slowmode 不能用", "/lock, /unlock and /slowmode fail"),
    _perm(1, "mod", "踢出成员", "Kick Members",
          "/kick，警告次数够了自动踢出", "/kick, and kicking automatically after enough warnings",
          "/kick 和警告后自动踢出不能用", "/kick and kicks after warnings fail"),
    _perm(2, "mod", "封禁成员", "Ban Members",
          "/ban、临时封禁到期自动解封、/unban", "/ban, lifting temporary bans on time, and /unban",
          "封禁、解封都不能用", "Bans and unbans fail"),
    _perm(40, "mod", "禁言成员", "Timeout Members",
          "/mute，警告够了自动禁言，自动审核禁言刷屏的人",
          "/mute, timeouts after warnings, and AutoMod timeouts for spam",
          "禁言相关的功能都不能用", "Timeouts fail everywhere"),
    _perm(7, "log", "查看审核日志", "View Audit Log",
          "日志里写明是谁删了消息、封了人、改了身份组",
          "Show who deleted a message, banned someone or changed a role",
          "日志只记发生了什么，不写是谁做的", "The log shows what happened, but not who did it"),
]

# 小凛不会要的权限
NEVER = [
    {"bit": 3, "zh": "管理员", "en": "Administrator",
     "why_zh": "等于什么都能做，所以不要。", "why_en": "It allows everything, so Rin doesn’t take it."},
    {"bit": 5, "zh": "管理服务器", "en": "Manage Server",
     "why_zh": "改服务器名称、图标和设置，小凛不碰这些。",
     "why_en": "Changes the server’s name, icon and settings. Rin leaves those alone."},
    {"bit": 17, "zh": "提及 @everyone", "en": "Mention @everyone",
     "why_zh": "小凛的消息不会 @全体或 @身份组。", "why_en": "Rin’s messages never ping everyone or a role."},
    {"bit": 29, "zh": "管理 Webhook", "en": "Manage Webhooks",
     "why_zh": "日志直接用小凛自己发，不借用 Webhook。", "why_en": "Logs are posted by Rin herself, not through webhooks."},
]


def _group(key, zh, en, desc_zh, desc_en, dashboard=None, dashboard_zh="", dashboard_en=""):
    return {"key": key, "zh": zh, "en": en, "desc_zh": desc_zh, "desc_en": desc_en,
            "dashboard": dashboard, "dashboard_zh": dashboard_zh, "dashboard_en": dashboard_en}


# 指令大全的十组，key 是 cog 名（CommandToggle 和 Help 归到 System）
COMMAND_GROUPS = [
    _group("Music", "音乐", "Music", "在语音频道里放歌，队列可以存档下次再放。",
           "Play music in voice channels and save queues for later.", "music", "音乐系统", "Music"),
    _group("Leveling", "等级", "Levels", "聊天涨经验，查看等级卡和排行榜。",
           "Chat to earn XP, then check cards and the leaderboard.", "leveling", "等级系统", "Leveling"),
    _group("Welcome", "迎新", "Welcomes", "选欢迎频道，用自己预览欢迎消息。",
           "Pick the welcome channel and preview the message on yourself.", "welcome", "欢迎新成员", "Welcome"),
    _group("Giveaway", "抽奖", "Giveaways", "发起、提前结束和重抽。",
           "Start, end early and reroll.", "giveaway", "抽奖", "Giveaways"),
    _group("ReactionRoles", "身份组面板", "Role panels", "成员点按钮自己领身份组。",
           "Members pick their own roles with buttons.", "roles", "领取身份组", "Role panels"),
    _group("Moderation", "管理", "Moderation", "踢出、封禁、禁言、警告和管理记录。",
           "Kick, ban, time out, warn and look up cases.", "moderation", "管理模块", "Moderation"),
    _group("AutoMod", "自动审核", "AutoMod", "违禁词、允许的链接和跳过的频道。",
           "Banned words, allowed links and skipped channels.", "automod", "自动审核", "AutoMod"),
    _group("ServerLog", "服务器日志", "Server log", "选择不记录哪些频道。",
           "Choose channels to leave out of the log.", "serverlog", "服务器事件日志", "Server log"),
    _group("General", "通用", "General", "状态、头像和掷骰子。", "Status, avatars and dice."),
    _group("System", "系统", "System", "帮助和指令开关。",
           "Help and command switches.", "utility", "指令管理", "Commands"),
]

# 指令默认需要的成员权限，用 Discord 的中文叫法
PERM_LABELS = {
    "manage_guild": ("管理服务器", "Manage Server"),
    "kick_members": ("踢出成员", "Kick Members"),
    "ban_members": ("封禁成员", "Ban Members"),
    "moderate_members": ("禁言成员", "Timeout Members"),
    "manage_messages": ("管理消息", "Manage Messages"),
    "manage_channels": ("管理频道", "Manage Channels"),
    "manage_roles": ("管理身份组", "Manage Roles"),
}
