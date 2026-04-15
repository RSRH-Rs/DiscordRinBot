import discord
from discord.ext import commands
from discord.ui import Select, View


# --- 1. 定义下拉菜单组件 ---
class HelpDropdown(Select):
    def __init__(self, bot):
        self.bot = bot
        options = []

        # A. 添加一个默认的“首页”选项
        options.append(
            discord.SelectOption(
                label="🏠 首页", description="回到功能概览", value="home"
            )
        )

        # B. 动态读取 bot 里的所有 Cog (插件)
        for cog_name, cog in bot.cogs.items():
            # 跳过 Help 自己，不显示在菜单里
            if cog_name == "Help":
                continue

            # 如果这个插件里没有指令，也就不用显示了
            if len(cog.get_commands()) == 0:
                continue

            # 给不同的模块设置不同的 emoji (可选，为了好看)
            emoji = "📂"
            if cog_name == "Music":
                emoji = "🎵"
            elif cog_name == "Leveling":
                emoji = "🏆"
            elif cog_name == "General":
                emoji = "🛠️"

            options.append(
                discord.SelectOption(
                    label=f"{cog_name} 模块",
                    description=f"查看 {cog_name} 的所有指令",
                    value=cog_name,  # 这里的 value 存的是 Cog 的名字
                    emoji=emoji,
                )
            )

        # 初始化下拉菜单
        super().__init__(
            placeholder="👇 请选择你想查看的功能模块...",
            min_values=1,
            max_values=1,
            options=options,
        )

    # C. 当用户选中某个选项时触发
    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]  # 获取用户选中的值

        if value == "home":
            # 如果选的是首页，显示默认欢迎界面
            embed = discord.Embed(
                title="✨ 小凛 Rinbot 指令手册",
                description="这里是全能小助手小凛！\n请查看下方的功能列表 (´• ω •`)ﾉ\n",
                color=discord.Color.pink(),
            )
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            embed.add_field(
                name="关于我",
                value="我是你的全能小助手，支持音乐、等级、娱乐等功能。",
                inline=False,
            )

        else:
            # 如果选的是具体模块 (如 Music)
            cog = self.bot.get_cog(value)
            if cog:
                embed = discord.Embed(
                    title=f"📂 {value} 模块指令", color=discord.Color.blue()
                )

                # 获取该模块下的指令
                commands_list = []
                for command in cog.get_commands():
                    if not command.hidden:
                        desc = command.description or "暂无介绍"
                        commands_list.append(f"**`/{command.name}`**\n╰ {desc}")

                if commands_list:
                    embed.description = "\n\n".join(commands_list)
                else:
                    embed.description = "该模块暂时没有可用指令。"
            else:
                embed = discord.Embed(
                    title="❌ 错误",
                    description="找不到该模块。",
                    color=discord.Color.red(),
                )

        # 更新消息 (edit_message)
        await interaction.response.edit_message(embed=embed)


# --- 2. 定义包含下拉菜单的视图 (View) ---
class HelpView(View):
    def __init__(self, bot):
        super().__init__(timeout=60)  # 60秒后按钮失效，节省资源
        self.add_item(HelpDropdown(bot))


# --- 3. 主 Cog ---
class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="打开交互式指令菜单")
    async def help(self, ctx):
        # 创建默认的首页 Embed
        embed = discord.Embed(
            title="✨ 小凛 Rinbot 指令中心",
            description="请在下方菜单选择一个分类，查看详细指令列表！",
            color=discord.Color.pink(),
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text="提示: 菜单 60 秒后失效")

        # 发送 Embed 并附带 View (下拉菜单)
        view = HelpView(self.bot)
        await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Help(bot))
