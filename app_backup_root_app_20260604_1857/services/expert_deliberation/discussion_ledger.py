"""Shared discussion ledger for expert deliberation turns."""

from __future__ import annotations

from .schemas import DiscussionTurn, ExpertAnalysis


class DiscussionLedger:
    def __init__(self) -> None:
        self._turns: list[DiscussionTurn] = []

    def add_analysis(self, analysis: ExpertAnalysis, round_index: int, turn_type: str) -> DiscussionTurn:
        turn = DiscussionTurn(
            turn_id=f"turn_{len(self._turns) + 1:03d}",
            round_index=round_index,
            expert_id=analysis.expert_id,
            display_name=analysis.display_name,
            turn_type=turn_type,
            position=analysis.position,
            used_fact_ids=analysis.used_fact_ids,
            new_fact_ids=analysis.new_fact_ids,
            claims=analysis.key_findings,
            questions_to_others=analysis.questions_to_others,
            tool_call_plan=analysis.tool_call_plan,
            uncertainties=analysis.uncertainties,
        )
        self._turns.append(turn)
        return turn

    def all(self) -> list[DiscussionTurn]:
        return list(self._turns)

    def latest_analyses(self) -> list[ExpertAnalysis]:
        latest: dict[str, DiscussionTurn] = {}
        for turn in self._turns:
            latest[turn.expert_id] = turn
        return [
            ExpertAnalysis(
                expert_id=turn.expert_id,
                display_name=turn.display_name,
                used_fact_ids=turn.used_fact_ids,
                new_fact_ids=turn.new_fact_ids,
                tool_call_plan=turn.tool_call_plan,
                position=turn.position,
                key_findings=turn.claims,
                questions_to_others=turn.questions_to_others,
                uncertainties=turn.uncertainties,
            )
            for turn in latest.values()
        ]

    def latest_for(self, expert_id: str) -> ExpertAnalysis | None:
        for turn in reversed(self._turns):
            if turn.expert_id == expert_id:
                return ExpertAnalysis(
                    expert_id=turn.expert_id,
                    display_name=turn.display_name,
                    used_fact_ids=turn.used_fact_ids,
                    new_fact_ids=turn.new_fact_ids,
                    tool_call_plan=turn.tool_call_plan,
                    position=turn.position,
                    key_findings=turn.claims,
                    questions_to_others=turn.questions_to_others,
                    uncertainties=turn.uncertainties,
                )
        return None

    def question_targets(self, valid_expert_ids: set[str]) -> set[str]:
        targets: set[str] = set()
        for turn in self._turns:
            for question in turn.questions_to_others:
                target = str(question.get("target_expert") or "").strip()
                if target in valid_expert_ids:
                    targets.add(target)
        return targets

    def summary_for_expert(self, expert_id: str, stage: str) -> str:
        if not self._turns:
            return "暂无共享讨论记录。"

        lines = [f"当前阶段：{stage}", "共享讨论记录："]
        for turn in self._turns[-8:]:
            lines.append(
                f"- {turn.turn_id} 第{turn.round_index}轮/{turn.turn_type}/{turn.display_name}: {turn.position}"
            )
            if turn.used_fact_ids:
                lines.append(f"  引用事实：{', '.join(turn.used_fact_ids[:8])}")
            if turn.new_fact_ids:
                lines.append(f"  新增补证事实：{', '.join(turn.new_fact_ids[:8])}")
            for question in turn.questions_to_others:
                target = str(question.get("target_expert") or "")
                question_text = str(question.get("question") or "")
                reason = str(question.get("reason") or "")
                if stage == "cross_review" and target != expert_id:
                    continue
                prefix = "指向你的问题" if target == expert_id else f"指向{target}的问题"
                lines.append(f"  {prefix}：{question_text}；原因：{reason}")
            if stage in {"review_moderation", "final_review"} and turn.uncertainties:
                lines.append(f"  不确定性：{'；'.join(turn.uncertainties[:4])}")
        return "\n".join(lines)
