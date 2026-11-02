import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _name in ("website", "rinbot"):
    _path = os.path.join(ROOT, _name)
    if _path in sys.path:
        sys.path.remove(_path)
    sys.path.insert(0, _path)
