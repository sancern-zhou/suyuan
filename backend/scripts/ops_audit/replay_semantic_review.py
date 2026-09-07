"""Replay semantic review from a saved audit without fetching or overwriting history.

Run with PYTHONPATH=backend in the backend_py311 environment.
"""

import argparse
import json
from collections import Counter

from app.services.ops_audit.final_issue_list import build_final_issue_list
from app.services.ops_audit.review_artifacts import persist_review_input
from app.services.ops_audit.semantic.reviewer import build_semantic_review_results
from app.utils.path_config import format_agent_path, resolve_agent_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--working-order-code", action="append", default=[])
    args = parser.parse_args()
    source = resolve_agent_path(args.source_dir)
    output = resolve_agent_path(args.output_dir)
    output.mkdir(parents=True, exist_ok=False)
    audit = json.loads((source / "latest_finished_work_orders_deterministic_audit.json").read_text())
    dataset = json.loads((source / "latest_finished_work_orders_dataset.json").read_text())
    if args.working_order_code:
        codes = set(args.working_order_code)
        audit["records"] = [record for record in audit["records"] if record.get("working_order_code") in codes]
    results = build_semantic_review_results(audit, dataset)
    final = build_final_issue_list(audit, results)
    for name, value in (("semantic_review_results", results), ("final_issue_list", final)):
        (output / f"latest_finished_work_orders_{name}.json").write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    persist_review_input(final, output / "latest_finished_work_orders_review_input.json")
    summary = {
        "scope": "semantic_replay_only_deterministic_audit_unchanged",
        "output_dir": format_agent_path(output),
        "order_count": len(audit["records"]),
        "semantic_result_count": results["result_count"],
        "semantic_judgments": dict(Counter(r["judgment"] for r in results["results"])),
        "candidate_issue_count": final["issue_count"],
        "candidate_rule_counts": final["rule_counts"],
        "facts_requiring_verification": sum(bool(i.get("needs_manual_review")) for i in final["items"]),
        "pending_semantic_review_count": len(final["pending_semantic_reviews"]),
        "final_review_required": True,
    }
    (output / "replay_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
