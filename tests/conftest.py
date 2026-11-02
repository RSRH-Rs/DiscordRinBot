import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _name in ("website", "rinbot"):
    _path = os.path.join(ROOT, _name)
    if _path in sys.path:
        sys.path.remove(_path)
    sys.path.insert(0, _path)

# 线上 cogs 目录在 sys.path 上（cog 里 `from _botlog_helper import ...`）；测试里同样挂上，
# 并预先导入真实的辅助模块，避免各测试文件各自塞一个缺函数的桩模块
_cogs = os.path.join(ROOT, "rinbot", "cogs")
if _cogs not in sys.path:
    sys.path.append(_cogs)
import _botlog_helper  # noqa: E402,F401
