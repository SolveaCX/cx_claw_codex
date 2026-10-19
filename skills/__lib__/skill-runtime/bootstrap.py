"""
Skill runtime bootstrap — two lines at the top of every skill script:

    import os, sys
    sys.path.insert(0, os.path.join(os.environ["SOLVEA_LIB_DIR"], "skill-runtime"))
    from bootstrap import *

After import, the following are available:
    SKILL_NAME        — inferred from the skill directory above scripts/
    WORKSPACE         — absolute Path to workspace/  (from $WORKSPACE_DIR, or relative fallback)
    OUTPUTS_DIR       — WORKSPACE / outputs / {skill_name}     # 跨轮路径稳定，下轮直接可读
    STATE_DIR         — WORKSPACE / state   / {skill_name}     # 跨轮路径稳定，下轮直接可读
    TMP_DIR           — WORKSPACE / tmp     / {skill_name}     # 仅本轮有效
    MOUNTED_USER      — .../mounted/chat-files/user            # 用户上传，lazy
    MOUNTED_TENANT    — .../mounted/tenant-files               # 租户级共享，lazy
    SOLVEA_TENANT_ID  — tenant ID (from $SOLVEA_TENANT_ID)
    SOLVEA_PROJECT_ID — Solvea project ID (from $SOLVEA_PROJECT_ID)
    SOLVEA_ENV        — "prod" or "staging"  (from $SOLVEA_ENV)
    timestamp()       — str  e.g. "20260422_143022"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SKILL 脚本开发规范
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【写入】脚本只能写 workspace/ 下的路径：
  - 输出文件  → OUTPUTS_DIR / f"name_{timestamp()}.ext"   # 每轮新建，带时间戳
  - 临时文件  → TMP_DIR / "tmp_name.ext"
  - 状态文件  → STATE_DIR / "progress.json"               # 固定名（有语义），每轮覆盖
  所有目录在使用前自行 mkdir：path.parent.mkdir(parents=True, exist_ok=True)
  禁止写 mounted/ 或沙箱外的任何路径。

【读取 mounted/】mounted/ 下的文件（用户上传 / 租户共享）是懒加载的：
  agent 调用 read_file 工具后文件才会物化到本地，脚本不能假设文件已存在。

  正确用法：
    if MOUNTED_USER.exists() and (MOUNTED_USER / "data.xlsx").exists():
        ...

【跨轮 outputs / state 惯用写法】
  上一轮写入 OUTPUTS_DIR / STATE_DIR 的文件，本轮启动时已由运行时 eager 还原到原路径，
  脚本直接读写即可（路径稳定，无需 read_file 物化）：

  读：
    import json
    _state_file = STATE_DIR / "progress.json"     # 用有语义的名字
    state = {}
    if _state_file.exists():
        try:
            state = json.loads(_state_file.read_text(encoding="utf-8"))
        except Exception:
            pass

  写：
    _state_file.parent.mkdir(parents=True, exist_ok=True)
    _state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

【路径格式】WORKSPACE_DIR 由运行时注入（docker: /sandbox/workspace，本地: {run_dir}/workspace），
  所有路径常量均为绝对 Path，不依赖 CWD。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os as _os
import sys as _sys
from datetime import datetime as _dt
from pathlib import Path

# ── sys.path bootstrap ────────────────────────────────────────────────────────
# Use __main__.__file__ when available (direct execution) so that module
# caching or re-import does not return a stale frame from a different caller.
_main_mod = _sys.modules.get("__main__")
_caller_file = _os.path.abspath(
    getattr(_main_mod, "__file__", None) or _sys._getframe(1).f_code.co_filename
)
_caller_dir  = _os.path.dirname(_caller_file)

# SOLVEA_LIB_DIR 由 SLG runtime（docker / local 都注入，见 env.py）；
# 通过 SLG runtime 之外裸跑脚本时，按仓库内 skills/{skill}/scripts 结构自动回退到 skills/__lib__。
def _infer_lib_root_from_caller() -> str:
    cur = Path(_caller_dir).resolve()
    for parent in [cur, *cur.parents]:
        candidate = parent / "__lib__"
        if candidate.is_dir():
            return str(candidate)
    raise KeyError("SOLVEA_LIB_DIR")


_lib_root = _os.environ.get("SOLVEA_LIB_DIR") or _infer_lib_root_from_caller()

# caller's own scripts/ dir first (for sibling module imports like render.py)
if _caller_dir not in _sys.path:
    _sys.path.insert(0, _caller_dir)

# add all subdirs of __lib__ to sys.path (each lib is its own flat package)
for _d in _os.listdir(_lib_root):
    _p = _os.path.join(_lib_root, _d)
    if _os.path.isdir(_p) and _p not in _sys.path:
        _sys.path.insert(0, _p)

# ── skill name & standard paths ───────────────────────────────────────────────
# Support both scripts/foo.py and focused subdirectories such as
# scripts/report/foo.py. The nearest scripts/ ancestor defines the skill root.
_caller_path = Path(_caller_dir).resolve()
_scripts_dir = next(
    (path for path in [_caller_path, *_caller_path.parents] if path.name == "scripts"),
    None,
)
SKILL_NAME = _scripts_dir.parent.name if _scripts_dir else _caller_path.parent.name

# WORKSPACE_DIR is injected by both backends (docker: /sandbox/workspace, local: {run_dir}/workspace).
# Falls back to relative "workspace" when running a script outside the runtime.
_workspace_dir = _os.environ.get("WORKSPACE_DIR")
if _workspace_dir:
    WORKSPACE     = Path(_workspace_dir)
    _root_dir     = WORKSPACE.parent
    _mounted_base = _root_dir / "mounted"
else:
    WORKSPACE     = Path("workspace")
    _mounted_base = Path("mounted")

OUTPUTS_DIR   = WORKSPACE / "outputs" / SKILL_NAME
STATE_DIR     = WORKSPACE / "state"   / SKILL_NAME
TMP_DIR       = WORKSPACE / "tmp"     / SKILL_NAME

MOUNTED_USER   = _mounted_base / "chat-files" / "user"
MOUNTED_TENANT = _mounted_base / "tenant-files"

# ── Solvea context injected by the runtime ────────────────────────────────────
SOLVEA_TENANT_ID  = _os.environ.get("SOLVEA_TENANT_ID", "")
SOLVEA_PROJECT_ID = _os.environ.get("SOLVEA_PROJECT_ID", "")
SOLVEA_ENV        = _os.environ.get("SOLVEA_ENV", "prod")


def timestamp() -> str:
    return _dt.now().strftime("%Y%m%d_%H%M%S")
