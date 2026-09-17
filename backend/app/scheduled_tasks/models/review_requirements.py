"""Declarative task result requirements shared by every review category."""
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResultFieldRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    field: str = Field(pattern=r"^(title|summary|decision|comment|sections\.[a-z][a-z0-9_]*)$")
    label: str = Field(min_length=1, max_length=120)
    required: bool = True
    required_when: dict[str, str] = Field(default_factory=dict, description="全部字段匹配时才必填")
    allowed_values: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_values(self):
        if any(not value.strip() for value in self.allowed_values):
            raise ValueError("允许值不能为空")
        if len(set(self.allowed_values)) != len(self.allowed_values):
            raise ValueError("允许值不能重复")
        if self.field == "decision" and not set(self.allowed_values).issubset(
            {"approve", "reject", "needs_evidence", "needs_action"}
        ):
            raise ValueError("结论状态允许值不合法")
        return self


def validate_result_requirements(requirements):
    fields = [item.field for item in requirements]
    if len(fields) != len(set(fields)):
        raise ValueError("结果字段要求不能重复")
    return requirements


def validate_review_result(submission, requirements):
    rules = validate_result_requirements([
        ResultFieldRequirement.model_validate(item) for item in requirements
    ])
    values = {key: submission[key] for key in ("title", "summary", "decision", "comment")}
    for section in submission["sections"]:
        for item in section["fields"]:
            if not item.get("key"):
                continue
            key = "sections." + item["key"]
            if key in values:
                raise ValueError(f"结果字段重复：{key}")
            values[key] = item["value"]
    errors = []
    for rule in rules:
        value = values.get(rule.field)
        if not value:
            if rule.required and all(values.get(key) == expected for key, expected in rule.required_when.items()):
                errors.append(f"缺少必填字段 {rule.label}（{rule.field}）")
        elif rule.allowed_values and value not in rule.allowed_values:
            errors.append(f"{rule.label}（{rule.field}）必须是：{'、'.join(rule.allowed_values)}")
    if errors:
        raise ValueError("结果校验失败，请修正后重新提交：" + "；".join(errors))
