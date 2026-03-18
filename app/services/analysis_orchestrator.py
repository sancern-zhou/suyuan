from typing import Any, Dict, Optional
import os
from app.agent.context.data_context_manager import DataContextManager

from backend.app.tools.analysis.calculate_reconstruction.calculate_reconstruction import calculate_reconstruction
from backend.app.tools.analysis.calculate_carbon.calculate_carbon import calculate_carbon
from backend.app.tools.analysis.calculate_soluble.calculate_soluble import calculate_soluble
from backend.app.tools.analysis.calculate_crustal.calculate_crustal import calculate_crustal
from backend.app.tools.analysis.calculate_trace.calculate_trace import calculate_trace

from backend.app.tools.visualization.scientific_charts.chonggou import render_chonggou_from_payload
from backend.app.tools.visualization.scientific_charts.carbon import render_carbon_from_payload
from backend.app.tools.visualization.scientific_charts.soluble import render_soluble_from_payload
from backend.app.tools.visualization.scientific_charts.crustal import render_crustal_from_payload
from backend.app.tools.visualization.scientific_charts.trace import render_trace_from_payload


TOOL_MAP = {
    "calculate_reconstruction": calculate_reconstruction,
    "calculate_carbon": calculate_carbon,
    "calculate_soluble": calculate_soluble,
    "calculate_crustal": calculate_crustal,
    "calculate_trace": calculate_trace,
}


def analyze_and_render(
    tool_name: str,
    data_id: str,
    data_manager: DataContextManager,
    out_dir: Optional[str] = None,
    render_inline: bool = True,
) -> Dict[str, Any]:
    """
    Orchestrator for calling analysis tools by name using data_id, then optionally rendering visuals.
    Returns the tool result and attaches rendered_files info into visuals.meta if available.
    """
    tool = TOOL_MAP.get(tool_name)
    if tool is None:
        raise ValueError(f"Unknown tool: {tool_name}")

    # Load raw data for the tool
    raw = data_manager.get_raw_data(data_id)
    import pandas as pd

    df = pd.DataFrame(raw) if isinstance(raw, list) else pd.DataFrame([raw])

    # Call tool with data and data_context_manager if supported
    result = tool(data=df, data_id=data_id, data_context_manager=data_manager)

    visuals = result.get("visuals", [])
    rendered_files = {}
    if render_inline and visuals:
        out_dir = out_dir or os.path.join("mapout", tool_name)
        os.makedirs(out_dir, exist_ok=True)
        for vis in visuals:
            v_id = vis.get("id", "visual")
            v_type = vis.get("type", "")
            payload = vis.get("payload", {})
            out_path = os.path.join(out_dir, f"{v_id}.svg")
            # routing to inline renderers
            if v_type == "stacked_time":
                # prefer reconstruction specialized renderer
                if tool_name == "calculate_reconstruction":
                    saved = render_chonggou_from_payload(payload, out_path, fmt="svg")
                else:
                    saved = render_carbon_from_payload(payload, out_path, fmt="svg")
            elif v_type == "scatter_ec_oc" or v_type == "scatter_nor_sor":
                saved = render_carbon_from_payload(payload, out_path, fmt="svg")
            elif v_type == "ternary":
                saved = render_soluble_from_payload(payload, out_path, fmt="svg")
            elif v_type == "boxplot":
                saved = render_crustal_from_payload(payload, out_path, fmt="svg")
            elif v_type == "bar_trace":
                saved = render_trace_from_payload(payload, out_path, fmt="svg")
            else:
                # default fallback
                saved = render_chonggou_from_payload(payload, out_path, fmt="svg")
            rendered_files[v_id] = saved
            vis_meta = vis.setdefault("meta", {})
            vis_meta["rendered_files"] = saved

    return result


