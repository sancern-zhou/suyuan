"""守门：事件循环内的 async 代码禁止直接调用同步阻塞 IO。

AsyncIOScheduler 把所有 fetcher、scheduled-task 执行器把所有 agent 工具、
web/worker 进程把所有路由 handler，都跑在同一个事件循环上；worker 进程还
承载 web 代理过来的全部 /api/scheduled-tasks 管理接口。一次带超时的同步
网络/子进程调用会冻结整个循环，让同进程内所有前端请求排队（生产事故实例：
NMC 小时抓取任务用同步 requests 把 worker 卡住每小时约 70 秒，定时任务
面板点击响应 2~4 秒；gd_suncere 查询工具 timeout=60 直接挂在循环上）。

规则：同步阻塞调用只能通过 asyncio.to_thread / loop.run_in_executor 明确
调度到线程。扫描为项目级两遍传递闭包：
  1) 找出所有"自身或（经同文件同步调用链）间接包含阻塞调用"的同步函数；
  2) 标记 async 作用域内对阻塞模块 API、登记的同步客户端方法、以及上述
     同步函数的直接调用。
跨文件同步客户端（如 gd_suncere）无法按名字可靠解析，显式登记在
BLOCKING_METHOD_NAMES。通用方法名（get/list/execute 等）不做跨文件匹配，
避免把无关调用链误连。同步嵌套 def 不扫（它们可能整体被送进线程）。
重 CPU（pandas、大文件解析等）无法静态识别，属代码评审责任，规范见
AGENTS.md。
"""

import ast
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[2] / "app"

# module.<attr> 形式的同步阻塞调用（网络 / 子进程 / 睡眠）。
BLOCKING_MODULE_CALLS = {
    "requests": {
        "get", "post", "put", "patch", "delete", "head", "options",
        "request", "Session",
    },
    "urllib.request": {"urlopen"},
    "time": {"sleep"},
    # subprocess.run/call/check_* 总是等待子进程结束；Popen 仅构造进程不阻塞
    # （等待类必须走 to_thread，见 execute_python_tool 的 process.wait）。
    "subprocess": {"run", "call", "check_call", "check_output"},
    # httpx 的同步入口；AsyncClient 不受限。
    "httpx": {"get", "post", "put", "patch", "delete", "head", "request",
              "stream", "Client"},
}

# 跨文件同步客户端的网络方法（按方法名登记；新增同步客户端时在此登记，
# 并优先考虑改造为 async 客户端而不是持续追加）。
BLOCKING_METHOD_NAMES = {
    # app/services/gd_suncere_api_client.py（GDSuncereAPIClient，requests 同步）
    "_make_request",
    "get_token",
    "query_city_day_data",
    "query_city_hour_data",
    "query_station_hour_data",
    "query_station_day_data",
    "query_report_data",
    "query_city_day_old_standard",
    "_query_city_day_data_segments",
    "_query_station_day_data_segments",
}

# 把调用明确调度到线程的入口；其参数表达式不扫描。
OFFLOAD_HELPER_NAMES = {"to_thread", "run_in_executor"}

# 一次性脚本 / 独立进程运行、不与前端共享事件循环的文件（相对 app/ 路径 → 原因）。
ALLOWED_FILES = {
    # python -m 单独运行的数据回填脚本，不在 web/worker 进程内。
    "db/backfill_scheduled_task_results.py": "独立进程一次性回填脚本",
}


class ModuleInfo:
    def __init__(self, relative, tree):
        self.relative = relative
        self.tree = tree
        self.alias_to_module = {}   # 本地别名 -> 模块名（import requests as rq）
        self.alias_to_import = {}   # 本地别名 -> (模块名, 原名)（from requests import get）
        self.functions = {}         # 函数名 -> 节点（含类方法，按名字索引，仅本文件）
        self.async_funcs = []
        self.session_attrs = set()  # 被赋值为 requests.Session() 的属性名
        self._collect_imports()
        self._collect_functions()
        self._collect_session_attrs()

    def _collect_imports(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".")[0]
                    self.alias_to_module[local] = alias.name
            elif isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    local = alias.asname or alias.name
                    self.alias_to_import[local] = (node.module, alias.name)

    def _collect_functions(self):
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.functions[node.name] = node
                if isinstance(node, ast.AsyncFunctionDef):
                    self.async_funcs.append(node)

    def _collect_session_attrs(self):
        """记录 self.<attr> = requests.Session() 形式的属性，用于识别
        self.session.get(...) 之类的同步会话调用。"""
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Assign):
                continue
            if not (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "Session"
                and isinstance(node.value.func.value, ast.Name)
                and node.value.func.value.id in BLOCKING_MODULE_CALLS
            ):
                continue
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    self.session_attrs.add(target.attr)

    def resolve_call(self, node: ast.Call):
        """返回 ('api', 描述) / ('local', 函数名) / None。

        'api' 是直接命中的阻塞 API/登记方法；'local' 是本文件内可按名字
        确定目标函数的调用（普通函数名、self/<self.链>.<method>）。
        跨文件一律不按通用方法名解析，避免同名误连。
        """
        func = node.func
        if isinstance(func, ast.Attribute):
            if func.attr in BLOCKING_METHOD_NAMES:
                return ("api", func.attr)
            value = func.value
            if isinstance(value, ast.Name):
                module = self.alias_to_module.get(value.id, value.id)
                names = BLOCKING_MODULE_CALLS.get(module)
                if names and func.attr in names:
                    return ("api", f"{module}.{func.attr}")
                if value.id in {"self", "cls"} and func.attr in self.functions:
                    return ("local", func.attr)
            elif isinstance(value, ast.Attribute):
                if (
                    isinstance(value.value, ast.Name)
                    and value.value.id == "self"
                ):
                    # self.<session_attr>.get(...)：requests.Session 存到属性上。
                    if (
                        value.attr in self.session_attrs
                        and func.attr in BLOCKING_MODULE_CALLS.get("requests", ())
                    ):
                        return ("api", f"requests.Session({value.attr}).{func.attr}")
                    # self.<client>.<method>(...)：方法定义在本文件。
                    if func.attr in self.functions:
                        return ("local", func.attr)
                elif (
                    value.attr in BLOCKING_MODULE_CALLS
                    and func.attr in BLOCKING_MODULE_CALLS[value.attr]
                ):
                    # urllib.request.urlopen 之类二级模块引用。
                    return ("api", f"{value.attr}.{func.attr}")
            return None
        if isinstance(func, ast.Name):
            imported = self.alias_to_import.get(func.id)
            if imported:
                module, original = imported
                names = BLOCKING_MODULE_CALLS.get(module)
                if names and original in names:
                    return ("api", f"{module}.{original}")
            if func.id in BLOCKING_MODULE_CALLS.get("urllib.request", ()):
                return ("api", func.id)
            if func.id in self.functions and func.id not in self.alias_to_import:
                return ("local", func.id)
        return None


def _offload_call(func_node) -> bool:
    if isinstance(func_node, ast.Attribute):
        return func_node.attr in OFFLOAD_HELPER_NAMES
    if isinstance(func_node, ast.Name):
        return func_node.id in OFFLOAD_HELPER_NAMES
    return False


def _scope_calls(module: ModuleInfo, func_def):
    """函数自身作用域内的 (line, kind, value) 调用记录。

    kind='api' 直接阻塞调用；kind='local' 本文件具名函数调用。
    跳过嵌套函数体（可能整体进线程）、to_thread/run_in_executor 的参数、
    以及被 await 直接包裹的调用（同步方法被 await 会立刻 TypeError 崩溃，
    属运行期错误而非静默阻塞，不归本守门管）。
    """
    records = []

    def visit(node, offloaded, awaited):
        for child in ast.iter_child_nodes(node):
            child_awaited = awaited or isinstance(node, ast.Await)
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if isinstance(child, ast.Call):
                if _offload_call(child.func):
                    visit(child, True, False)
                    continue
                if not offloaded:
                    resolved = module.resolve_call(child)
                    if resolved and not (child_awaited and resolved[0] == "api"):
                        records.append((child.lineno, *resolved))
            visit(child, offloaded, child_awaited)

    visit(func_def, False, False)
    return records


def _load_modules():
    modules = {}
    for path in sorted(APP_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if path.name.startswith("test_") or path.name.endswith("_test.py"):
            continue
        relative = path.relative_to(APP_ROOT).as_posix()
        if relative in ALLOWED_FILES:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        modules[relative] = ModuleInfo(relative, tree)
    return modules


def _compute_blocking_sync_functions(modules):
    """返回 {(file, func_name)}：自身或经同文件同步调用链间接阻塞的同步函数。"""
    direct_hits = set()
    edges = {}
    for module in modules.values():
        for name, node in module.functions.items():
            if isinstance(node, ast.AsyncFunctionDef):
                continue
            key = (module.relative, name)
            for lineno, kind, value in _scope_calls(module, node):
                if kind == "api":
                    direct_hits.add(key)
                else:
                    # local 调用只解析到同文件定义，避免跨文件同名误连。
                    edges.setdefault(key, set()).add((module.relative, value))

    blocking = set(direct_hits)
    changed = True
    while changed:
        changed = False
        for key, targets in edges.items():
            if key in blocking:
                continue
            if targets & blocking:
                blocking.add(key)
                changed = True
    return blocking


def _collect_async_violations(modules, blocking):
    findings = []
    for module in modules.values():
        for node in module.async_funcs:
            for lineno, kind, value in _scope_calls(module, node):
                if kind == "api":
                    findings.append((module.relative, lineno, value))
                elif (module.relative, value) in blocking:
                    findings.append((module.relative, lineno, f"{value}()（本文件同步函数）"))
    return findings


def _findings():
    modules = _load_modules()
    blocking = _compute_blocking_sync_functions(modules)
    return _collect_async_violations(modules, blocking)


def test_async_functions_do_not_call_blocking_io_directly():
    violations = _findings()
    formatted = "\n".join(
        f"  app/{relative}:{lineno} async 内直接调用 {api}"
        for relative, lineno, api, _ in violations
    )
    assert not violations, (
        "async 代码中存在直接同步阻塞调用（会冻结事件循环，拖慢同进程全部"
        f"前端请求），必须用 asyncio.to_thread 调度到线程：\n{formatted}\n"
        "规范见 AGENTS.md「后台任务与事件循环隔离规范」。"
    )


if __name__ == "__main__":
    findings = _findings()
    for relative, lineno, api, _ in findings:
        print(f"app/{relative}:{lineno} {api}")
    raise SystemExit(1 if findings else 0)
