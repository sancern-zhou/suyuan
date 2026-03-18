"""
Browser Automation Tool

A browser automation tool for the ReAct Agent that enables web-based operations:
- Navigation (open, navigate, tabs)
- Content extraction (snapshot, screenshot, extract)
- Interaction (click, type, scroll)
- Lifecycle management (start, stop, status)

Design Pattern: Office Assistant Tool (simplified format, no UDF v2.0)
Text-First: All operations return LLM-readable content
"""
from .tool import BrowserTool

__all__ = ["BrowserTool"]
