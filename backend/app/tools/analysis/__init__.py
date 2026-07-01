"""
Analysis Tools

分析工具集，用于执行各种分析任务。
"""

__all__ = [
    "AnalyzeUpwindEnterprisesTool",
    "TrajectorySourceAnalysisTool",
]


def __getattr__(name: str):
    if name == "AnalyzeUpwindEnterprisesTool":
        from app.tools.analysis.analyze_upwind_enterprises.tool import AnalyzeUpwindEnterprisesTool

        return AnalyzeUpwindEnterprisesTool
    if name == "TrajectorySourceAnalysisTool":
        from app.tools.analysis.trajectory_source_analysis.tool import TrajectorySourceAnalysisTool

        return TrajectorySourceAnalysisTool
    raise AttributeError(name)
