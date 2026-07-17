from __future__ import annotations

import xml.etree.ElementTree as ET
from copy import deepcopy
from typing import Any


class DrawioXmlError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "drawio_xml_error",
        operation_index: int | None = None,
        field: str | None = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.operation_index = operation_index
        self.field = field
        self.retryable = retryable


def normalize_drawio_xml(xml: str) -> str:
    raw = (xml or "").strip()
    if not raw:
        raise DrawioXmlError("xml is required")

    root = _parse_input(raw)
    cells = _extract_cells(root)
    _validate_cells(cells)
    return _serialize_mxfile(cells)


def apply_drawio_operations(
    xml: str,
    operations: list[dict[str, Any]],
    selected_cells: list[dict[str, Any]] | None = None,
) -> str:
    normalized = normalize_drawio_xml(xml)
    root = ET.fromstring(normalized)
    graph_root = _find_graph_root(root)
    if graph_root is None:
        raise DrawioXmlError("missing mxGraphModel root")

    by_id = {
        cell.attrib["id"]: cell
        for cell in graph_root.findall("mxCell")
        if cell.attrib.get("id") not in {"0", "1"}
    }
    order = [
        cell.attrib["id"]
        for cell in graph_root.findall("mxCell")
        if cell.attrib.get("id") not in {"0", "1"}
    ]

    for operation_index, op in enumerate(operations or []):
        try:
            operation = str(op.get("operation") or "").strip().lower()
            cell_id = _resolve_cell_id(op, selected_cells)
            new_cell = None
            if operation in {"add", "update"}:
                new_cell = _parse_single_cell(str(op.get("new_xml") or ""))
                cell_id = cell_id or str(new_cell.attrib.get("id") or "").strip()
            if not cell_id and operation != "connect":
                raise DrawioXmlError(
                    "operation cell_id is required",
                    error_code="operation_cell_id_required",
                    field="cell_id",
                )

            if operation in {"add", "update"}:
                assert new_cell is not None
                if new_cell.attrib.get("id") != cell_id:
                    raise DrawioXmlError(f"ID mismatch for {cell_id}")
                by_id[cell_id] = new_cell
                if cell_id not in order:
                    order.append(cell_id)
            elif operation == "delete":
                delete_ids = _cascade_delete_ids(by_id, cell_id)
                for delete_id in delete_ids:
                    by_id.pop(delete_id, None)
                order = [existing_id for existing_id in order if existing_id not in delete_ids]
            elif operation == "delete_with_edges":
                delete_ids = _cascade_delete_ids(by_id, cell_id)
                for delete_id in delete_ids:
                    by_id.pop(delete_id, None)
                order = [existing_id for existing_id in order if existing_id not in delete_ids]
            elif operation == "update_label":
                _require_existing_cell(by_id, cell_id)
                by_id[cell_id].set("value", str(op.get("label", op.get("value", ""))))
            elif operation == "update_style":
                _require_existing_cell(by_id, cell_id)
                by_id[cell_id].set(
                    "style",
                    _merge_style(by_id[cell_id].attrib.get("style", ""), op.get("style_patch"), op.get("style")),
                )
            elif operation == "move_resize":
                _require_existing_cell(by_id, cell_id)
                _update_geometry(by_id[cell_id], op.get("geometry") or op)
            elif operation == "connect":
                edge_id = str(op.get("cell_id") or op.get("edge_id") or "").strip()
                if not edge_id:
                    raise DrawioXmlError("connect cell_id is required")
                if edge_id in by_id:
                    raise DrawioXmlError(f"duplicate id {edge_id}")
                source_id = _resolve_endpoint_id(op.get("source_cell_id", op.get("source")), selected_cells)
                target_id = _resolve_endpoint_id(op.get("target_cell_id", op.get("target")), selected_cells)
                if not source_id or not target_id:
                    raise DrawioXmlError("connect source_cell_id and target_cell_id are required")
                _require_existing_cell(by_id, source_id)
                _require_existing_cell(by_id, target_id)
                by_id[edge_id] = _create_edge_cell(edge_id, source_id, target_id, op)
                order.append(edge_id)
            else:
                raise DrawioXmlError(f"unsupported operation {operation}")
        except DrawioXmlError as exc:
            if exc.operation_index is None:
                exc.operation_index = operation_index
            raise

    next_cells = [by_id[cell_id] for cell_id in order if cell_id in by_id]
    _validate_cells(next_cells)
    return _serialize_mxfile(next_cells)


def _parse_input(raw: str) -> ET.Element:
    try:
        if raw.startswith("<mxfile") or raw.startswith("<mxGraphModel"):
            return ET.fromstring(raw)
        return ET.fromstring(f"<wrapper>{raw}</wrapper>")
    except ET.ParseError as exc:
        raise DrawioXmlError(f"invalid XML: {exc}") from exc


def _parse_single_cell(raw: str) -> ET.Element:
    wrapper = _parse_input(raw.strip())
    cells = _extract_cells(wrapper)
    if len(cells) != 1:
        raise DrawioXmlError("new_xml must contain exactly one mxCell")
    return deepcopy(cells[0])


def _extract_cells(root: ET.Element) -> list[ET.Element]:
    if root.tag == "mxfile":
        graph_root = _find_graph_root(root)
        if graph_root is None:
            raise DrawioXmlError("missing root")
        cells = list(graph_root.findall("mxCell"))
    elif root.tag == "mxGraphModel":
        graph_root = root.find("root")
        if graph_root is None:
            raise DrawioXmlError("missing root")
        cells = list(graph_root.findall("mxCell"))
    else:
        cells = list(root.findall("mxCell"))

    return [deepcopy(cell) for cell in cells if cell.attrib.get("id") not in {"0", "1"}]


def _find_graph_root(root: ET.Element) -> ET.Element | None:
    if root.tag == "mxfile":
        diagram = root.find("diagram")
        graph = diagram.find("mxGraphModel") if diagram is not None else None
        return graph.find("root") if graph is not None else None
    if root.tag == "mxGraphModel":
        return root.find("root")
    return None


def _validate_cells(cells: list[ET.Element]) -> None:
    ids: set[str] = set()
    for cell in cells:
        cell_id = cell.attrib.get("id")
        if not cell_id:
            raise DrawioXmlError("mxCell id is required")
        if cell_id in ids:
            raise DrawioXmlError(f"duplicate id {cell_id}")
        ids.add(cell_id)

    endpoint_ids = ids | {"0", "1"}
    for cell in cells:
        if cell.attrib.get("edge") == "1":
            source = cell.attrib.get("source")
            target = cell.attrib.get("target")
            if source and source not in endpoint_ids:
                raise DrawioXmlError(f"unknown source {source}")
            if target and target not in endpoint_ids:
                raise DrawioXmlError(f"unknown target {target}")


def _serialize_mxfile(cells: list[ET.Element]) -> str:
    mxfile = ET.Element("mxfile", {"host": "suyuan"})
    diagram = ET.SubElement(mxfile, "diagram", {"id": "page-1", "name": "Page-1"})
    graph = ET.SubElement(diagram, "mxGraphModel")
    graph_root = ET.SubElement(graph, "root")
    ET.SubElement(graph_root, "mxCell", {"id": "0"})
    ET.SubElement(graph_root, "mxCell", {"id": "1", "parent": "0"})
    for cell in cells:
        graph_root.append(deepcopy(cell))
    return ET.tostring(mxfile, encoding="unicode")


def _cascade_delete_ids(by_id: dict[str, ET.Element], cell_id: str) -> set[str]:
    delete_ids = {cell_id}
    changed = True
    while changed:
        changed = False
        for existing_id, cell in list(by_id.items()):
            if existing_id in delete_ids:
                continue
            if (
                cell.attrib.get("parent") in delete_ids
                or cell.attrib.get("source") in delete_ids
                or cell.attrib.get("target") in delete_ids
            ):
                delete_ids.add(existing_id)
                changed = True
    return delete_ids


def _resolve_cell_id(op: dict[str, Any], selected_cells: list[dict[str, Any]] | None) -> str:
    explicit = str(op.get("cell_id") or "").strip()
    if explicit:
        return explicit

    target = str(op.get("target") or "").strip()
    if target == "selected":
        return _first_selected_cell_id(selected_cells)

    return target


def _resolve_endpoint_id(value: Any, selected_cells: list[dict[str, Any]] | None) -> str:
    endpoint = str(value or "").strip()
    if endpoint == "selected":
        return _first_selected_cell_id(selected_cells)
    return endpoint


def _first_selected_cell_id(selected_cells: list[dict[str, Any]] | None) -> str:
    for cell in selected_cells or []:
        if isinstance(cell, dict):
            cell_id = str(cell.get("id") or cell.get("cell_id") or cell.get("cellId") or "").strip()
            if cell_id:
                return cell_id
    raise DrawioXmlError("target selected requires selected_cells")


def _require_existing_cell(by_id: dict[str, ET.Element], cell_id: str) -> None:
    if cell_id not in by_id:
        raise DrawioXmlError(f"Cell with id={cell_id} not found")


def _merge_style(current_style: str, style_patch: Any, replacement_style: Any = None) -> str:
    if isinstance(replacement_style, str) and replacement_style.strip():
        return replacement_style.strip()

    style_parts: dict[str, str] = {}
    flags: list[str] = []
    for part in (current_style or "").split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            key, value = part.split("=", 1)
            style_parts[key] = value
        elif part not in flags:
            flags.append(part)

    if isinstance(style_patch, dict):
        for key, value in style_patch.items():
            clean_key = str(key).strip()
            if not clean_key:
                continue
            if value is None:
                style_parts.pop(clean_key, None)
            else:
                style_parts[clean_key] = str(value)
    elif isinstance(style_patch, str):
        return _merge_style(current_style, _parse_style_patch(style_patch))

    merged = flags + [f"{key}={value}" for key, value in style_parts.items()]
    return ";".join(merged) + (";" if merged else "")


def _parse_style_patch(style: str) -> dict[str, str]:
    patch: dict[str, str] = {}
    for part in (style or "").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        patch[key] = value
    return patch


def _update_geometry(cell: ET.Element, geometry_updates: Any) -> None:
    if not isinstance(geometry_updates, dict):
        raise DrawioXmlError("move_resize geometry is required")

    geometry = cell.find("mxGeometry")
    if geometry is None:
        geometry = ET.SubElement(cell, "mxGeometry", {"as": "geometry"})

    for key in ["x", "y", "width", "height"]:
        if key in geometry_updates and geometry_updates[key] is not None:
            geometry.set(key, _format_number(geometry_updates[key]))


def _format_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DrawioXmlError(f"invalid geometry number {value}") from exc
    if number.is_integer():
        return str(int(number))
    return str(number)


def _create_edge_cell(edge_id: str, source_id: str, target_id: str, op: dict[str, Any]) -> ET.Element:
    attrs = {
        "id": edge_id,
        "value": str(op.get("label", op.get("value", ""))),
        "style": str(op.get("style") or "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;"),
        "edge": "1",
        "parent": str(op.get("parent") or "1"),
        "source": source_id,
        "target": target_id,
    }
    edge = ET.Element("mxCell", attrs)
    ET.SubElement(edge, "mxGeometry", {"relative": "1", "as": "geometry"})
    return edge
