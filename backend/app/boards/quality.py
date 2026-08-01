from __future__ import annotations

import base64
import json
import math
import os
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.utils.path_config import get_data_registry


class BoardQualityFailed(RuntimeError):
    code = "board_quality_failed"

    def __init__(self, report: dict[str, Any]):
        super().__init__(self.code)
        self.report = report


class BoardRenderFailed(RuntimeError):
    code = "board_render_failed"

    def __init__(self, message: str, *, report: dict[str, Any] | None = None):
        super().__init__(message)
        self.report = report or {}


def _style_map(style: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in str(style or "").split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            result[key] = value
    return result


def _geometry(cell: ET.Element) -> dict[str, float] | None:
    geometry = cell.find("mxGeometry")
    if geometry is None:
        return None
    values: dict[str, float] = {}
    for key in ("x", "y", "width", "height"):
        try:
            values[key] = float(geometry.attrib.get(key, "0"))
        except (TypeError, ValueError):
            return None
    return values


def _overlap_ratio(left: dict[str, float], right: dict[str, float]) -> float:
    width = max(0.0, min(left["x"] + left["width"], right["x"] + right["width"]) - max(left["x"], right["x"]))
    height = max(0.0, min(left["y"] + left["height"], right["y"] + right["height"]) - max(left["y"], right["y"]))
    intersection = width * height
    minimum_area = min(left["width"] * left["height"], right["width"] * right["height"])
    return intersection / minimum_area if minimum_area > 0 else 0.0


def evaluate_drawio_quality(xml: str) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        return {
            "status": "failed",
            "errors": [{"code": "invalid_xml", "message": str(exc)}],
            "warnings": [],
            "metrics": {"vertex_count": 0, "edge_count": 0, "overlap_count": 0, "orphan_count": 0, "canvas_utilization": 0.0},
        }

    cells = [cell for cell in root.iter("mxCell") if cell.attrib.get("id") not in {None, "0", "1"}]
    cell_ids = {cell.attrib["id"] for cell in cells}
    vertices: list[tuple[ET.Element, dict[str, float]]] = []
    edges: list[ET.Element] = []
    connected_ids: set[str] = set()

    for cell in cells:
        cell_id = cell.attrib["id"]
        parent = cell.attrib.get("parent")
        if parent and parent not in cell_ids | {"0", "1"}:
            errors.append({"code": "unknown_parent", "cell_id": cell_id, "message": f"父节点 {parent} 不存在"})
        if cell.attrib.get("vertex") == "1":
            geometry = _geometry(cell)
            if geometry is None or not all(math.isfinite(value) for value in geometry.values()):
                errors.append({"code": "invalid_geometry", "cell_id": cell_id, "message": "节点几何信息无效"})
                continue
            if geometry["width"] <= 0 or geometry["height"] <= 0:
                errors.append({"code": "invalid_geometry_size", "cell_id": cell_id, "message": "节点宽高必须大于零"})
            vertices.append((cell, geometry))
            label = str(cell.attrib.get("value") or "").strip()
            if not label:
                warnings.append({"code": "empty_label", "cell_id": cell_id, "message": "节点没有文本"})
            if len(label) > 80:
                warnings.append({"code": "label_too_long", "cell_id": cell_id, "message": "节点文本可能溢出"})
            style = _style_map(cell.attrib.get("style", ""))
            try:
                if float(style.get("fontSize", "12")) < 10:
                    warnings.append({"code": "font_too_small", "cell_id": cell_id, "message": "字号小于 10px"})
            except ValueError:
                pass
        if cell.attrib.get("edge") == "1":
            edges.append(cell)
            for endpoint_name in ("source", "target"):
                endpoint = cell.attrib.get(endpoint_name)
                if endpoint:
                    if endpoint not in cell_ids:
                        errors.append({"code": "unknown_edge_endpoint", "cell_id": cell_id, "message": f"连线端点 {endpoint} 不存在"})
                    else:
                        connected_ids.add(endpoint)

    overlap_count = 0
    top_level = [(cell, geo) for cell, geo in vertices if cell.attrib.get("parent") in {None, "1"}]
    for index, (left_cell, left_geo) in enumerate(top_level):
        for right_cell, right_geo in top_level[index + 1:]:
            if _overlap_ratio(left_geo, right_geo) >= 0.15:
                overlap_count += 1
                warnings.append({
                    "code": "node_overlap",
                    "cell_ids": [left_cell.attrib["id"], right_cell.attrib["id"]],
                    "message": "节点存在明显重叠",
                })

    orphan_ids = [cell.attrib["id"] for cell, _ in vertices if cell.attrib["id"] not in connected_ids]
    for cell_id in orphan_ids:
        warnings.append({"code": "orphan_node", "cell_id": cell_id, "message": "节点没有任何连线"})

    if vertices:
        min_x = min(geo["x"] for _, geo in vertices)
        min_y = min(geo["y"] for _, geo in vertices)
        max_x = max(geo["x"] + geo["width"] for _, geo in vertices)
        max_y = max(geo["y"] + geo["height"] for _, geo in vertices)
        bounds_area = max(1.0, (max_x - min_x) * (max_y - min_y))
        node_area = sum(geo["width"] * geo["height"] for _, geo in vertices)
        utilization = min(1.0, node_area / bounds_area)
    else:
        utilization = 0.0

    status = "failed" if errors else "warning" if warnings else "passed"
    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "vertex_count": len(vertices),
            "edge_count": len(edges),
            "overlap_count": overlap_count,
            "orphan_count": len(orphan_ids),
            "canvas_utilization": round(utilization, 4),
        },
    }


class PlaywrightDrawioRenderer:
    def __init__(self, render_url: str | None = None, *, timeout_ms: int = 20_000) -> None:
        self.render_url = render_url or os.getenv(
            "DRAWIO_RENDER_URL",
            "https://embed.diagrams.net/?embed=1&proto=json&spin=1&ui=min&modified=0&saveAndExit=0&noSaveBtn=1&noExitBtn=1",
        )
        self.timeout_ms = timeout_ms

    async def render(self, xml: str, output_path: Path) -> dict[str, Any]:
        from playwright.async_api import async_playwright

        origin_parts = urlparse(self.render_url)
        origin = f"{origin_parts.scheme}://{origin_parts.netloc}"
        render_url_json = json.dumps(self.render_url)
        origin_json = json.dumps(origin)
        xml_json = json.dumps(xml).replace("</", "<\\/")
        html = f"""
        <!doctype html><html><body style="margin:0">
        <iframe id="drawio" src={render_url_json} style="width:1200px;height:900px;border:0"></iframe>
        <script>
        window.__drawioExport = null;
        window.__drawioError = null;
        const frame = document.getElementById('drawio');
        const xml = {xml_json};
        window.addEventListener('message', (event) => {{
          if (event.source !== frame.contentWindow || event.origin !== {origin_json}) return;
          let message = event.data;
          if (typeof message === 'string') {{ try {{ message = JSON.parse(message); }} catch (_) {{ return; }} }}
          if (message.event === 'init') {{
            frame.contentWindow.postMessage(JSON.stringify({{ action: 'load', xml, autosave: 0 }}), {origin_json});
          }} else if (message.event === 'load') {{
            frame.contentWindow.postMessage(JSON.stringify({{ action: 'export', format: 'png', xml, border: 12, scale: 1 }}), {origin_json});
          }} else if (message.event === 'export') {{
            window.__drawioExport = message.data || message.image || message.url || null;
          }}
        }});
        </script></body></html>
        """
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                page = await browser.new_page(viewport={"width": 1200, "height": 900})
                await page.set_content(html)
                await page.wait_for_function("window.__drawioExport !== null", timeout=self.timeout_ms)
                data_url = await page.evaluate("window.__drawioExport")
            finally:
                await browser.close()
        if not isinstance(data_url, str) or "," not in data_url:
            raise RuntimeError("drawio_export_missing_data_url")
        output_path.write_bytes(base64.b64decode(data_url.split(",", 1)[1]))
        return {"renderer": "diagrams.net-playwright", "render_url": self.render_url, "width": 1200, "height": 900}


class DrawioQualityService:
    def __init__(self, *, renderer=None, storage_root: Path | str | None = None) -> None:
        self.renderer = renderer or PlaywrightDrawioRenderer()
        self.storage_root = Path(storage_root or (get_data_registry() / "drawio_board_screenshots"))

    async def inspect(self, xml: str, *, board_id: str, candidate_id: str) -> dict[str, Any]:
        report = evaluate_drawio_quality(xml)
        if report["status"] == "failed":
            raise BoardQualityFailed(report)
        directory = self.storage_root / board_id
        directory.mkdir(parents=True, exist_ok=True)
        output_path = directory / f"{candidate_id}_{uuid.uuid4().hex[:10]}.png"
        renderer_metadata = None
        last_error: Exception | None = None
        for _ in range(2):
            try:
                renderer_metadata = await self.renderer.render(xml, output_path)
                break
            except Exception as exc:
                last_error = exc
        if renderer_metadata is None or not output_path.exists():
            raise BoardRenderFailed(str(last_error or "renderer failed"), report=report) from last_error
        report["renderer"] = renderer_metadata
        local_path = str(output_path.resolve())
        screenshot_ref = {
            "kind": "drawio_board_screenshot",
            "artifact_kind": "drawio_board",
            "board_id": board_id,
            "candidate_version_id": candidate_id,
            "local_path": local_path,
            "path": local_path,
            "mime_type": "image/png",
            "format": "png",
            "size_bytes": output_path.stat().st_size,
        }
        return {"quality_report": report, "screenshot_ref": screenshot_ref}
