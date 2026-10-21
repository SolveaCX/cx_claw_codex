#!/usr/bin/env python3
"""沙箱状态检查入口。支持全量检查或单项场景。

用法：
  python3 /skills/runtime-inspector/scripts/sandbox_inspect.py                    # 全量
  python3 /skills/runtime-inspector/scripts/sandbox_inspect.py --scenario env     # 仅环境变量
  python3 /skills/runtime-inspector/scripts/sandbox_inspect.py --scenario fs      # 仅目录结构
  python3 /skills/runtime-inspector/scripts/sandbox_inspect.py --scenario execute # 仅 bash execute 路径行为
  python3 /skills/runtime-inspector/scripts/sandbox_inspect.py --scenario paths   # 虚拟路径行为验证
  python3 /skills/runtime-inspector/scripts/sandbox_inspect.py --scenario deps    # 仅依赖库
"""
import json, os, sys, argparse, importlib, subprocess, shutil
sys.path.insert(0, os.path.join(os.environ["SOLVEA_LIB_DIR"], "skill-runtime"))
from bootstrap import *
import json

_SEC = "=" * 64
_failures: list[str] = []


def _ok(label: str, detail: str = "") -> None:
    suffix = f"  ({detail})" if detail else ""
    print(f"  ✅  {label}{suffix}")


def _fail(label: str, detail: str = "") -> None:
    suffix = f"  — {detail}" if detail else ""
    print(f"  ❌  {label}{suffix}")
    _failures.append(label + (f": {detail}" if detail else ""))


def _info(label: str, detail: str = "") -> None:
    suffix = f"  ({detail})" if detail else ""
    print(f"  ⬜  {label}{suffix}")


def check(label: str, ok: bool, detail: str = "") -> None:
    (_ok if ok else _fail)(label, detail)


_SENSITIVE_SUFFIXES = ("KEY", "SECRET", "PASSWORD", "TOKEN", "PASS")


def _is_sensitive(name: str) -> bool:
    upper = name.upper()
    return any(upper.endswith(s) or f"_{s}_" in upper for s in _SENSITIVE_SUFFIXES)


def _mask(val: str, show: int = 4) -> str:
    """Keep first/last `show` chars, replace middle with ***."""
    if len(val) <= show * 2:
        return "*" * len(val)
    return f"{val[:show]}***{val[-show:]}"


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO: env
# ─────────────────────────────────────────────────────────────────────────────

def check_env() -> None:
    print(_SEC)
    print("ENV — 预期注入变量")

    # WORKSPACE_DIR：必须存在且可写，本地=root_dir/workspace，Docker=/sandbox/workspace
    workspace_dir = os.environ.get("WORKSPACE_DIR", "")
    if workspace_dir:
        p = Path(workspace_dir)
        if not p.exists():
            _fail("WORKSPACE_DIR", f"路径不存在: {workspace_dir}")
        elif not os.access(p, os.W_OK):
            _fail("WORKSPACE_DIR", f"路径不可写: {workspace_dir}")
        else:
            _ok("WORKSPACE_DIR", workspace_dir)
    else:
        _fail("WORKSPACE_DIR", "未注入")

    # SOLVEA_LIB_DIR：必须存在且有内容
    lib_dir = os.environ.get("SOLVEA_LIB_DIR", "")
    if lib_dir:
        p = Path(lib_dir)
        if not p.exists():
            _fail("SOLVEA_LIB_DIR", f"路径不存在: {lib_dir}")
        else:
            subdirs = [d.name for d in p.iterdir() if d.is_dir()]
            _ok("SOLVEA_LIB_DIR", f"{lib_dir}  ({len(subdirs)} 个子包: {', '.join(sorted(subdirs)[:4])})")
    else:
        _fail("SOLVEA_LIB_DIR", "未注入")

    # SOLVEA_ENV
    env_val = os.environ.get("SOLVEA_ENV", "")
    check("SOLVEA_ENV", bool(env_val), env_val or "未注入")

    # ANTHROPIC_BASE_URL：不能指向真实 api.anthropic.com
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "")
    if not base_url:
        _fail("ANTHROPIC_BASE_URL", "未注入")
    elif "api.anthropic.com" in base_url:
        _fail("ANTHROPIC_BASE_URL", f"直接暴露真实端点: {base_url}")
    else:
        _ok("ANTHROPIC_BASE_URL", base_url)

    openai_base_url = os.environ.get("OPENAI_BASE_URL", "")
    if not openai_base_url:
        _fail("OPENAI_BASE_URL", "未注入")
    elif "api.openai.com" in openai_base_url:
        _fail("OPENAI_BASE_URL", f"直接暴露真实端点: {openai_base_url}")
    else:
        _ok("OPENAI_BASE_URL", openai_base_url)

    print()
    print("ENV — 可选变量")
    for key, desc in [
        ("SOLVEA_TOKEN",      "staging JWT token"),
        ("SOLVEA_PROD_TOKEN", "prod JWT token"),
        ("SOLVEA_PROJECT_ID", "项目 ID"),
    ]:
        val = os.environ.get(key, "")
        print(f"  {'✅' if val else '⬜'}  {key}={'(set)' if val else '(not set)'}  {desc}")

    print()
    print("CXClaw — 本地 CLI")
    cli_path = shutil.which("${PLUGIN_ROOT}/bin/cxclaw-launcher")
    if cli_path:
        _ok("${PLUGIN_ROOT}/bin/cxclaw-launcher", cli_path)
    else:
        _fail("${PLUGIN_ROOT}/bin/cxclaw-launcher", "未找到；业务命令和 SLS 直查不可用")

    print()
    print("ENV — 安全校验（敏感变量不应泄露）")
    for key, desc in [
        ("ANTHROPIC_API_KEY",              "应为哑键 sk-sandbox-proxy，或不存在"),
        ("OPENAI_API_KEY",                 "应为哑键 sk-sandbox-proxy，或不存在"),
        ("GPT_BASE_URL",                   "Java 内部地址不应暴露到沙箱"),
        ("GPT_X_TOKEN",                    "Java 内部鉴权 token 不应暴露到沙箱"),
        ("SOLVEA_SLS_ACCESS_KEY_ID",       "SLS AK 不应暴露到沙箱"),
        ("SOLVEA_SLS_ACCESS_KEY_SECRET",   "SLS SK 不应暴露到沙箱"),
        ("DATABASE_URL",                   "数据库 URL 不应暴露"),
        ("POSTGRES_PASSWORD",              "PG 密码不应暴露"),
        ("AWS_SECRET_ACCESS_KEY",          "AWS 密钥不应暴露"),
    ]:
        val = os.environ.get(key, "")
        if not val:
            _ok(f"{key}  未注入", desc)
        elif key in {"ANTHROPIC_API_KEY", "OPENAI_API_KEY"} and val == "sk-sandbox-proxy":
            _ok(f"{key}=sk-sandbox-proxy", "哑键，正常")
        else:
            print(f"  ⚠️   {key}  已注入（值已隐藏）  ← {desc}")

    print()
    print("ENV — 所有注入变量（敏感值已脱敏）")
    all_env = sorted(os.environ.items())
    for k, v in all_env:
        display = _mask(v) if _is_sensitive(k) else v
        # 超长值截断显示
        if len(display) > 120:
            display = display[:117] + "..."
        print(f"  {k}={display}")


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO: fs
# ─────────────────────────────────────────────────────────────────────────────

def _check_path(rel: str, label: str, expect_writable: bool) -> None:
    p = Path(rel)
    exists = p.exists()
    writable = os.access(p, os.W_OK) if exists else False
    status = "✅" if exists else "⬜"
    rw = "[rw]" if writable else "[ro]"
    warn = "  ⚠️  权限异常" if exists and (writable != expect_writable) else ""
    extra = ""
    if exists and p.is_dir():
        count = sum(1 for _ in p.rglob("*") if _.is_file())
        extra = f"  {count} files"
    elif exists and p.is_file():
        extra = f"  {p.stat().st_size} bytes"
    print(f"  {status} {label}")
    print(f"     {rel}{extra}  {rw}{warn}")


def check_fs() -> None:
    print(_SEC)
    print("FS — 目录结构")
    _state_file = STATE_DIR / "inspect.json"
    state = {}
    if _state_file.exists():
        try:
            state = json.loads(_state_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    results_path = state.get("results_path")

    # workspace 子目录：SandboxManager 创建，expect_writable=True
    for rel, label in [
        ("workspace",         "workspace 根目录（可写）"),
        ("workspace/outputs", "outputs（每轮新文件）"),
        ("workspace/state",   "state（固定文件名跨轮覆盖）"),
        ("workspace/tmp",     "tmp（当轮临时）"),
    ]:
        _check_path(rel, label, expect_writable=True)

    # mounted 目录：只读性由 ManifestBackend 保证，OS 层面目录本身可写属正常，不检查权限
    # eager 模型下 chat-files/agent 与 chat-files/state 已不再使用
    for rel, label in [
        ("mounted",                             "mounted 根目录"),
        ("mounted/chat-files/user",             "用户上传文件"),
        ("mounted/tenant-files",                "租户级共享文件"),
    ]:
        p = Path(rel)
        status = "✅" if p.exists() else "⬜"
        count = sum(1 for _ in p.rglob("*") if _.is_file()) if p.exists() else 0
        print(f"  {status} {label}")
        print(f"     {rel}  {count} files  [逻辑只读，OS 可写属正常]")

    # 上一轮 agent outputs：eager 还原到 workspace/outputs/{skill}/，首次运行时空属正常
    skill_outputs = Path("workspace/outputs") / SKILL_NAME
    if skill_outputs.exists():
        files = sorted(f for f in skill_outputs.rglob("*") if f.is_file())
        _info("上一轮 agent outputs", f"{skill_outputs}  ({len(files)} files)")
    else:
        _info("上一轮 agent outputs", f"{skill_outputs}  (首次运行，尚无历史输出)")

    # skills / skill-lib：文件级只读（OS chmod 0o444），目录本身可写（允许 rmtree），检查文件权限
    for rel, label in [
        ("skills/" + SKILL_NAME, "skill 目录"),
    ]:
        p = Path(rel)
        if p.exists():
            files = list(p.rglob("*"))
            file_list = [f for f in files if f.is_file()]
            readonly_files = [f for f in file_list if not os.access(f, os.W_OK)]
            all_ro = len(readonly_files) == len(file_list) and len(file_list) > 0
            status = "✅" if all_ro else ("⬜" if not file_list else "⚠️ ")
            detail = f"{len(readonly_files)}/{len(file_list)} 个文件只读"
            print(f"  {status} {label}  ({detail})")
            print(f"     {rel}")
        else:
            print(f"  ⬜ {label}")
            print(f"     {rel}  (不存在)")

    lib_dir = os.environ.get("SOLVEA_LIB_DIR", "")
    if lib_dir:
        p = Path(lib_dir)
        if p.exists():
            file_list = [f for f in p.rglob("*") if f.is_file()]
            readonly_files = [f for f in file_list if not os.access(f, os.W_OK)]
            all_ro = len(readonly_files) == len(file_list) and len(file_list) > 0
            status = "✅" if all_ro else ("⬜" if not file_list else "⚠️ ")
            detail = f"{len(readonly_files)}/{len(file_list)} 个文件只读"
            print(f"  {status} skill-lib 目录  ({detail})")
            print(f"     {lib_dir}")
        else:
            _fail("skill-lib 目录", f"路径不存在: {lib_dir}")

    if results_path:
        _check_path(results_path, "本轮处理结果", True)


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO: execute
# ─────────────────────────────────────────────────────────────────────────────

def _bash(cmd: str) -> tuple[int, str]:
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
    return r.returncode, (r.stdout.strip() or r.stderr.strip())


def check_execute() -> None:
    print(_SEC)
    print("EXECUTE — bash 执行环境验证")

    # 1. CWD
    cwd = os.getcwd()
    print(f"\n  CWD: {cwd}")
    check("CWD 可访问", os.path.isdir(cwd))
    check("workspace/ 相对路径可达",
          os.path.isdir("workspace"),
          "Path('workspace') 应等价于 CWD/workspace")

    # 2. $WORKSPACE_DIR 从 bash 里读
    print()
    rc, out = _bash("echo $WORKSPACE_DIR")
    check("$WORKSPACE_DIR 在 bash 中已设置", bool(out) and out != "", out or "(empty)")
    if out:
        p = Path(out)
        check("$WORKSPACE_DIR 路径存在", p.exists(), out)
        check("$WORKSPACE_DIR 可写", p.exists() and os.access(p, os.W_OK), out)

    # 3. $SOLVEA_LIB_DIR 从 bash 里读
    rc2, out2 = _bash("echo $SOLVEA_LIB_DIR")
    check("$SOLVEA_LIB_DIR 在 bash 中已设置", bool(out2) and out2 != "", out2 or "(empty)")
    if out2:
        check("$SOLVEA_LIB_DIR 路径存在", Path(out2).exists(), out2)

    # 4. 相对路径写文件再读回（验证 CWD 对齐）
    print()
    test_file = "workspace/tmp/execute_path_test.txt"
    rc3, _ = _bash(f"mkdir -p workspace/tmp && echo 'execute-ok' > {test_file}")
    if rc3 == 0:
        content = Path(test_file).read_text().strip() if Path(test_file).exists() else ""
        check("bash 相对路径写文件可被 Python 读到", content == "execute-ok",
              f"actual={content!r}" if content != "execute-ok" else "")
        Path(test_file).unlink(missing_ok=True)
    else:
        _fail("bash 相对路径写文件", "命令失败")

    # 5. python3 解释器路径
    rc4, python_path = _bash("which python3")
    check("python3 可找到", rc4 == 0, python_path)
    if python_path:
        is_venv = ".venv" in python_path or "envs" in python_path
        print(f"  {'✅' if is_venv else '⚠️ '}  python3 路径: {python_path}"
              + ("  (venv)" if is_venv else "  ← 可能是系统 python，非 venv"))

    # 6. PATH 包含 venv bin
    rc5, path_val = _bash("echo $PATH")
    has_venv_in_path = ".venv" in path_val or "envs" in path_val
    check("PATH 包含 venv bin 目录", has_venv_in_path,
          "(确保 python3 解释器和依赖库来自 venv)")


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO: paths
# ─────────────────────────────────────────────────────────────────────────────

def check_paths() -> None:
    print(_SEC)
    print("PATHS — 虚拟路径行为（deepagent 工具 / bash execute / 脚本内部）")

    # 1. Python bootstrap 路径常量（脚本内部访问）
    print("\n  [1] Python 路径常量（bootstrap 注入）")

    # 必须存在的父目录（SandboxManager 创建）
    for name, path in [
        ("WORKSPACE",      WORKSPACE),
        ("MOUNTED_USER",   MOUNTED_USER),
        ("MOUNTED_TENANT", MOUNTED_TENANT),
    ]:
        p = Path(str(path))
        check(f"{name}", p.exists(), str(p))

    # skill 子目录：脚本首次写文件时自行 mkdir，此处只验证路径常量值合理（父目录存在）
    for name, path in [
        ("OUTPUTS_DIR", OUTPUTS_DIR),
        ("STATE_DIR",   STATE_DIR),
        ("TMP_DIR",     TMP_DIR),
    ]:
        p = Path(str(path))
        parent_ok = p.parent.exists()
        status = "✅" if parent_ok else "❌"
        exist_hint = "已存在" if p.exists() else "未创建（首次写时 mkdir）"
        print(f"  {status}  {name}  ({p}  {exist_hint})")
        if not parent_ok:
            _failures.append(f"{name}: 父目录不存在 {p.parent}")

    # 2. bash execute 路径可达性（bash execute 工具）
    print("\n  [2] bash 虚拟路径可达（ls）")
    for vpath in ["/workspace", "/mounted", "/skills", "/skill-lib"]:
        rc, out = _bash(f"ls {vpath} 2>&1 | head -3")
        check(f"bash: ls {vpath}", rc == 0, out[:80] if out else "(no output)")

    # 3. bash write → Python read（CWD / 路径映射对齐）
    print("\n  [3] bash 写 workspace/tmp → Python 读回")
    probe = "workspace/tmp/path_probe.txt"
    rc, _ = _bash(f"mkdir -p workspace/tmp && echo 'pathok' > {probe}")
    if rc == 0:
        py_path = Path(probe)
        content = py_path.read_text().strip() if py_path.exists() else ""
        check("bash 写 → Python 读对齐", content == "pathok",
              f"actual={content!r}" if content != "pathok" else "")
        py_path.unlink(missing_ok=True)
    else:
        _fail("bash 写 workspace/tmp", "mkdir 或 echo 失败")

    # 4. Python write → bash read（反向验证）
    print("\n  [4] Python 写 workspace/tmp → bash 读回")
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    probe2 = TMP_DIR / "path_probe2.txt"
    probe2.write_text("pyok", encoding="utf-8")
    rc2, out2 = _bash(f"cat {probe2}")
    check("Python 写 → bash 读对齐", out2.strip() == "pyok",
          f"actual={out2.strip()!r}" if out2.strip() != "pyok" else "")
    probe2.unlink(missing_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO: deps
# ─────────────────────────────────────────────────────────────────────────────

def check_deps() -> None:
    print(_SEC)
    print("DEPS — 依赖库可用性")

    libs = [
        ("anthropic",   "Claude API"),
        ("httpx",       "HTTP 客户端"),
        ("yaml",        "YAML (pyyaml)"),
        ("openpyxl",    "Excel 读写"),
        ("pandas",      "数据处理"),
        ("bs4",         "HTML 解析 (beautifulsoup4)"),
        ("pypdf",       "PDF 解析"),
        ("pymupdf4llm", "PDF → Markdown"),
        ("markdown",    "Markdown → HTML（poc/scripts/gen_poc_manual.py 渲染报告）"),
        ("docx",        "Word 文档 (python-docx)"),
        ("markitdown",  "多格式转 Markdown"),
        ("aiohttp",     "异步 HTTP"),
        ("aliyun.log",  "阿里云 SLS (aliyun-log-python-sdk)"),
    ]
    for module, desc in libs:
        try:
            importlib.import_module(module)
            _ok(f"{module:<16} {desc}")
        except ImportError:
            _info(f"{module:<16} {desc}  ← 不可用（sandbox 组依赖未安装属正常）")


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────

SCENARIOS: dict[str, tuple[str, object]] = {
    "env":     ("ENV — 环境变量注入与安全",              check_env),
    "fs":      ("FS — 目录结构与读写权限",               check_fs),
    "execute": ("EXECUTE — bash 执行路径行为",           check_execute),
    "paths":   ("PATHS — 虚拟路径行为（bash/Python对齐）", check_paths),
    "deps":    ("DEPS — 依赖库可用性",                   check_deps),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="沙箱状态检查")
    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS) + ["all"],
        default="all",
        help="单项场景或全量（默认 all）",
    )
    args = parser.parse_args()

    print(_SEC)
    print("SANDBOX INSPECTOR")
    print(_SEC)

    if args.scenario == "all":
        for name, (title, fn) in SCENARIOS.items():
            fn()
    else:
        _, fn = SCENARIOS[args.scenario]
        fn()

    print()
    print(_SEC)
    if _failures:
        print(f"RESULT: ❌ FAIL  ({len(_failures)} 项)")
        for f in _failures:
            print(f"  - {f}")
    else:
        print("RESULT: ✅ PASS")
    print(_SEC)


if __name__ == "__main__":
    main()
