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
