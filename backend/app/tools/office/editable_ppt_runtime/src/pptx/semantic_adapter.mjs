import { normalizeColor, powerpointFont, pxBoxToInches } from "./basic_adapter.mjs";

function chartData(element) {
  return element.data.series.map((series) => ({
    name: series.name,
    labels: element.data.categories,
    values: series.values,
  }));
}

function addChart(slide, element, box, theme, pptxApi) {
  const chartType = element.chartType === "column"
    ? (pptxApi.ChartType.column || pptxApi.ChartType.bar)
    : pptxApi.ChartType[element.chartType];
  if (!chartType) throw new Error(`UNSUPPORTED_CHART_TYPE: ${element.chartType}`);
  slide.addChart(chartType, chartData(element), {
    ...pxBoxToInches(box),
    objectName: element.id,
    showTitle: false,
    showLegend: element.data.series.length > 0,
    showValue: true,
    showCatName: false,
    showSerName: false,
    catAxisLabelFontFace: powerpointFont(theme),
    valAxisLabelFontFace: powerpointFont(theme),
    chartColors: [normalizeColor(theme.primary) || "174A7C", normalizeColor(theme.secondary) || "0F766E"],
    showBorder: false,
    ...(element.chartType === "column" ? { barDir: "col" } : {}),
  });
  return { kind: "chart", id: element.id };
}

function addTable(slide, element, box, theme) {
  slide.addTable(element.data.rows, {
    ...pxBoxToInches(box),
    objectName: element.id,
    border: { color: normalizeColor(theme.line) || "CBD5E1", width: 1 },
    color: normalizeColor(theme.text) || "1F2937",
    fill: normalizeColor(theme.surface) || "FFFFFF",
    fontFace: powerpointFont(theme),
    fontSize: 12,
    margin: 0.06,
    valign: "mid",
    autoFit: false,
  });
  return { kind: "table", id: element.id };
}

function addDiagram(slide, element, box, theme, pptxApi) {
  const frame = pxBoxToInches(box);
  const nodes = element.data.nodes || [];
  const edges = element.data.edges || [];
  if (nodes.length === 0) throw new Error(`DIAGRAM_HAS_NO_NODES: ${element.id}`);
  const gap = Math.min(0.35, frame.w / (nodes.length * 5));
  const nodeWidth = (frame.w - gap * (nodes.length - 1)) / nodes.length;
  const nodeHeight = Math.min(frame.h * 0.55, 1.1);
  const y = frame.y + (frame.h - nodeHeight) / 2;
  const positions = new Map();
  nodes.forEach((node, index) => {
    const x = frame.x + index * (nodeWidth + gap);
    positions.set(node.id, { x, y, w: nodeWidth, h: nodeHeight });
    slide.addShape(pptxApi.ShapeType.roundRect, {
      x,
      y,
      w: nodeWidth,
      h: nodeHeight,
      objectName: node.id,
      fill: { color: normalizeColor(node.fill || theme.surface) || "FFFFFF" },
      line: { color: normalizeColor(theme.primary) || "174A7C", width: 1.5 },
      radius: 0.08,
    });
    slide.addText(String(node.label || node.id), {
      x,
      y,
      w: nodeWidth,
      h: nodeHeight,
      objectName: `${node.id}-label`,
      margin: 0.05,
      align: "center",
      valign: "mid",
      color: normalizeColor(theme.text) || "1F2937",
      fontFace: powerpointFont(theme),
      fontSize: 14,
      fit: "shrink",
    });
  });
  for (const edge of edges) {
    const source = positions.get(edge.source);
    const target = positions.get(edge.target);
    if (!source || !target) throw new Error(`DIAGRAM_EDGE_NODE_MISSING: ${edge.id}`);
    const x = source.x + source.w;
    const targetX = target.x;
    const edgeY = source.y + source.h / 2;
    slide.addShape(pptxApi.ShapeType.line, {
      x,
      y: edgeY,
      w: targetX - x,
      h: target.y + target.h / 2 - edgeY,
      objectName: edge.id,
      line: { color: normalizeColor(theme.primary) || "174A7C", width: 1.5, beginArrowType: "none", endArrowType: "triangle" },
    });
  }
  return { kind: "diagram", id: element.id, nodes: nodes.length, edges: edges.length };
}

export function addNativeElement(slide, element, box, theme, pptxApi) {
  if (element.kind === "chart") return addChart(slide, element, box, theme, pptxApi);
  if (element.kind === "table") return addTable(slide, element, box, theme);
  if (element.kind === "diagram") return addDiagram(slide, element, box, theme, pptxApi);
  throw new Error(`UNSUPPORTED_NATIVE_ELEMENT: ${element.kind}`);
}
