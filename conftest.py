"""pytest 配置：确保插件根目录在 sys.path 中，使测试可直接导入 blockly 包。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
