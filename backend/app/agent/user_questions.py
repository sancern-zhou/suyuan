"""Structured questions shared by the agent tool and interaction endpoint."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

# 参考 ZCode AskUserQuestion 的 preview 校验：预览只能是安全的 HTML 片段。
# 含 HTML 标记时禁止 html/body/doctype 文档级标签与 script/style 标签，且必须含至少一个标签；
# 纯文本（不含任何 HTML 标记）原样放行。
_HTML_PREVIEW_MARKER = re.compile(
    r"<!doctype\b|<!--|</?\s*[a-z][a-z0-9:-]*(?:\s[^<>]*)?>", re.IGNORECASE
)
_HTML_PREVIEW_DOCUMENT_TAG = re.compile(r"<!doctype\b|</?\s*(?:html|body)\b", re.IGNORECASE)
_HTML_PREVIEW_SCRIPT_STYLE_TAG = re.compile(r"</?\s*(?:script|style)\b", re.IGNORECASE)
_HTML_PREVIEW_TAG = re.compile(r"</?\s*[a-z][a-z0-9:-]*(?:\s[^<>]*)?>", re.IGNORECASE)


class QuestionOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=500)
    preview: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_preview(self):
        if self.preview is None or not _HTML_PREVIEW_MARKER.search(self.preview):
            return self
        if _HTML_PREVIEW_DOCUMENT_TAG.search(self.preview):
            raise ValueError("preview 必须是 HTML 片段，不能包含 html/body/doctype 标签")
        if _HTML_PREVIEW_SCRIPT_STYLE_TAG.search(self.preview):
            raise ValueError("preview 不能包含 script 或 style 标签")
        if not _HTML_PREVIEW_TAG.search(self.preview):
            raise ValueError("preview 含 HTML 标记时必须包含至少一个 HTML 标签")
        return self


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=500)
    header: str = Field(min_length=1, max_length=12)
    options: list[QuestionOption] = Field(min_length=2, max_length=4)
    multiSelect: bool = False

    @model_validator(mode="after")
    def unique_options(self):
        labels = [option.label.strip().casefold() for option in self.options]
        if len(labels) != len(set(labels)) or "other" in labels or "其他" in labels:
            raise ValueError("option labels must be unique; Other is provided by the client")
        return self


class QuestionSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    questions: list[Question] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def unique_questions(self):
        texts = [item.question.strip() for item in self.questions]
        if len(texts) != len(set(texts)):
            raise ValueError("question texts must be unique")
        return self


class QuestionAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected: list[StrictInt] = Field(default_factory=list, max_length=4)
    custom: str | None = Field(default=None, max_length=4000)


def validate_answers(questions: list[dict[str, Any]], answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    question_set = QuestionSet.model_validate({"questions": questions})
    if len(answers) != len(question_set.questions):
        raise ValueError("one answer is required for each question")
    validated = []
    for question, raw in zip(question_set.questions, answers):
        answer = QuestionAnswer.model_validate(raw)
        selected = answer.selected
        custom = (answer.custom or "").strip()
        if len(selected) != len(set(selected)) or any(
            index < 0 or index >= len(question.options) for index in selected
        ):
            raise ValueError("invalid option selection")
        if not selected and not custom:
            raise ValueError("blank answer")
        if not question.multiSelect and len(selected) + bool(custom) != 1:
            raise ValueError("single-select question requires exactly one choice")
        validated.append({"selected": selected, "custom": custom or None})
    return validated


def format_answers(questions: list[dict[str, Any]], answers: list[dict[str, Any]]) -> str:
    lines = ["【结构化提问回复】用户已回答先前的问题，请依据以下选择继续原任务："]
    for question, answer in zip(questions, answers):
        labels = [question["options"][index]["label"] for index in answer["selected"]]
        if answer.get("custom"):
            labels.append(answer["custom"])
        lines.append(f"- {question['question']}：{json.dumps(labels, ensure_ascii=False)}")
    return "\n".join(lines)
