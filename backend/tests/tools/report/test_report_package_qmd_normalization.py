from datetime import datetime

from app.tools.report.report_package.tool import _normalize_static_qmd


def test_normalize_static_qmd_removes_r_only_template_markup():
    qmd = """---
title: "Demo"
date: "`r Sys.Date()`"
output:
  html_document:
    toc: true
---

```{r setup, include=FALSE}
knitr::opts_chunk$set(echo = FALSE, warning = FALSE, message = FALSE)
```

## Summary

Body.
"""

    normalized = _normalize_static_qmd(qmd)

    assert "`r Sys.Date()`" not in normalized
    assert "```{r setup" not in normalized
    assert "knitr::opts_chunk" not in normalized
    assert f'date: "{datetime.now().strftime("%Y-%m-%d")}"' in normalized
    assert "## Summary" in normalized


def test_normalize_static_qmd_converts_quotes_around_mixed_chinese_numeric_text():
    qmd = 'FPI品牌"厂家备案参数0-4.096V"、SHARP5030"最高加热温度60℃"\n'

    normalized = _normalize_static_qmd(qmd)

    assert '"厂家备案参数0-4.096V"' not in normalized
    assert "FPI品牌“厂家备案参数0-4.096V”" in normalized
    assert "SHARP5030“最高加热温度60℃”" in normalized


def test_normalize_static_qmd_handles_weather_ranges_without_touching_code():
    qmd = (
        "湿度48%~58%，降水概率87%~90%，等级良~轻度污染。\n"
        "| 湿度 | 等级 |\n|---|---|\n| 78%~93% | 较好~优 |\n"
        "\x6048%~58%\x60 和 \\~ 保持原样。\n"
        "\x60\x60\x60text\n78%~93%\n\x60\x60\x60\n"
    )

    normalized = _normalize_static_qmd(qmd)

    assert "湿度48%～58%，降水概率87%～90%，等级良～轻度污染" in normalized
    assert "| 78%～93% | 较好～优 |" in normalized
    assert "\x6048%~58%\x60 和 \\~ 保持原样" in normalized
    assert "\x60\x60\x60text\n78%~93%\n\x60\x60\x60" in normalized
