"""Run from project root with PYTHONPATH=backend python -m scripts.evaluate_agent_dag."""
import argparse
import asyncio
import json
import os
import statistics
import subprocess
from pathlib import Path
import tempfile


def write_summary(report: dict, output: Path) -> None:
    lines = ["# Agent DAG 受控评测", "", f"运行后端：`{report['backend']}`。", "",
             "固定数据 + 有界评测循环 + 生产 DAG 调度。未覆盖生产 ReAct、记忆、SSE、子会话持久化和真实业务接口。",
             "replay 只验证链路，不能用于宣称模型正确率、Token 或生产性能提升。",
             "单次 live 样本只作试运行；阈值需重复样本和真实业务验证。", "",
             "| 场景 | 执行方式 | 通过/次数 | 耗时中位数(s) | 模型调用总数 | 输入Token总数 | 输出Token总数 | 重复取数总数 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    groups = {}
    for row in report["runs"]:
        groups.setdefault((row["case"], row["variant"]), []).append(row)
    for (case, variant), rows in groups.items():
        tokens = lambda field: sum(row["usage"][field] for row in rows) if all(row["usage"]["complete"] for row in rows) else "缺失"
        lines.append(f"| {case} | {variant} | {sum(row['quality']['passed'] and not row['error'] for row in rows)}/{len(rows)} | "
                     f"{statistics.median(row['duration_seconds'] for row in rows):.2f} | {sum(row['llm_calls'] for row in rows)} | "
                     f"{tokens('input_tokens')} | {tokens('output_tokens')} | {sum(row['duplicate_acquisitions'] for row in rows)} |")
    lines += ["", "耗时包含失败和超时样本。Token 为供应商返回值，缓存Token单列于 results.json，不估算缺失值或货币费用。",
              "质量校验覆盖数值、已访问来源文件和结构化因果边界；解释文字与每条结论的证据支持仍需人工复核。"]
    (output / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Controlled direct vs DAG evaluation (fixture data, real scheduling)")
    parser.add_argument("--backend", choices=("live", "replay"), default="replay")
    parser.add_argument("--env-file", type=Path, help="Explicit absolute deployment configuration; never copied into report")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--case", action="append")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    if args.repeats < 1 or args.timeout <= 0:
        parser.error("repeats and timeout must be positive")
    if args.env_file:
        if not args.env_file.is_absolute() or not args.env_file.is_file():
            parser.error("env-file must be an existing absolute path")
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=True)
    # Isolate all incidental journal/cache/log writes before importing application code.
    isolated_root = Path(tempfile.mkdtemp(prefix="suyuan-dag-eval-"))
    os.environ["DATA_REGISTRY_DIR"] = str(isolated_root / "registry")
    from app.agent.workflow.evaluation import EvaluationRunner, ReplayChildModel, default_cases
    from app.utils.path_config import PROJECT_ROOT, resolve_agent_path, format_agent_path
    output = resolve_agent_path(args.output_dir) if args.output_dir else isolated_root / "results"
    output.mkdir(parents=True, exist_ok=False)
    cases = default_cases()
    if args.case:
        unknown = set(args.case) - {case.name for case in cases}
        if unknown:
            parser.error(f"unknown cases: {sorted(unknown)}")
        cases = [case for case in cases if case.name in args.case]
    model = ReplayChildModel()
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                              text=True, capture_output=True, check=True).stdout.strip()
    if args.backend == "live":
        from app.services.llm_service import LLMService
        model = LLMService(request_timeout_seconds=min(args.timeout, 90))
    runs = []
    try:
        for case in cases:
            for repeat in range(args.repeats):
                # Alternate order to reduce systematic warm-cache/order bias.
                for variant in (("direct", "dag") if repeat % 2 == 0 else ("dag", "direct")):
                    runner = EvaluationRunner(case, variant, output / f"{case.name}-{repeat}-{variant}", model)
                    row = await runner.run(backend=args.backend, timeout=args.timeout)
                    row["repeat"] = repeat
                    runs.append(row)
                    report = {"schema_version": "agent-dag-eval.v1", "backend": args.backend,
                              "code_revision": revision,
                              "initial_model": getattr(model, "model", None),
                              "initial_provider": getattr(model, "provider", None),
                              "scope": "bounded evaluation loop + production DAG tool; fixture business tools; no ReAct memory/SSE/session persistence",
                              "runs": runs}
                    (output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                    write_summary(report, output)
                    print(json.dumps({key: row[key] for key in ("case", "variant", "duration_seconds", "quality", "usage", "error")}, ensure_ascii=False), flush=True)
        print("report: " + format_agent_path(output / "results.json"))
        return 0 if all(row["quality"]["passed"] and not row["error"] for row in runs) else 1
    finally:
        client = getattr(model, "anthropic_client", None)
        if client is not None:
            await client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
