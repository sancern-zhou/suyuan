# AI Draw.io Candidate Edge Routing Design

## Goal

Prevent connectors in AI-generated draw.io candidate boards from crossing unrelated nodes. The system will detect edge-to-node intersections, repair affected orthogonal routes by moving their horizontal or vertical channel, write the repaired route into the XML, and reject a candidate if it cannot produce a node-safe route.

Node avoidance is the hard requirement. Reducing edge-to-edge crossings is a secondary optimization and must never cause a route to cross a node.

## Scope

This feature applies only to a new AI candidate produced by `create_drawio_board` when the tool has an Agent run and session context.

Included:

- deterministic routing of AI-generated orthogonal edges that do not contain explicit waypoints;
- validation and repair of AI-generated orthogonal or segmented edges that already contain waypoints;
- absolute geometry resolution for nested nodes, groups, containers, and swimlanes;
- edge-to-node collision detection with a visual safety margin;
- structured routing metrics and blocking diagnostics;
- focused geometry, routing, XML, quality-gate, and tool integration tests.

Excluded:

- rerouting XML saved or manually edited by a user;
- rerouting restored history versions or autosaved drafts;
- moving or resizing nodes;
- globally rearranging the diagram;
- guaranteeing that no two connectors cross;
- automatically rerouting arbitrary curved or straight edges;
- introducing a full automatic layout engine such as ELK in the first version.

This design extends the existing draw.io quality gate. It intentionally adds routing only for AI candidates and does not change the general rule that unusual user-created layouts remain editable and persistable.

## Chosen Approach

Use a deterministic local channel router that reproduces the common manual repair: move the middle segment of a connector above, below, left, or right until it has a clear corridor.

The alternatives were:

1. A full global Manhattan or ELK layout pass. This is more powerful but may move or substantially reroute otherwise acceptable content and is unnecessary for the initial problem.
2. Ask the Agent to regenerate XML after a quality warning. This is inexpensive to integrate but cannot guarantee that repeated generations will remove the collision.
3. A local channel router. This preserves the Agent's node layout, produces predictable XML, and directly automates the user's successful manual adjustment. This is the selected option.

## Why Explicit Routes Are Required

AI-generated edges usually declare only `source`, `target`, `edgeStyle`, and an empty relative `mxGeometry`. diagrams.net then calculates a local display route when the XML is loaded. That route is not a global obstacle-avoidance result and its bend positions may not be stored in the source XML.

The backend must not validate one estimated route and then allow diagrams.net to display a different route. For every AI-generated automatic orthogonal edge, it will therefore calculate a deterministic route and persist its ports and bend points. Repaired edges will use `segmentEdgeStyle` so diagrams.net preserves the intended horizontal and vertical segments.

## Processing Pipeline

The AI candidate path becomes:

```text
normalize_drawio_xml
  -> build absolute geometry index
  -> route or validate candidate edges in stable order
  -> write explicit ports and mxPoint waypoints
  -> validate every emitted segment against node obstacles
  -> evaluate_drawio_quality
  -> persist candidate
```

The routing pass runs after XML normalization and before the current static quality evaluation and candidate persistence. Calls without AI session/run context retain their current behavior.

Edge handling rules are:

- an automatic orthogonal edge receives a deterministic route;
- an explicit orthogonal or segmented route is preserved when collision-free;
- an explicit orthogonal or segmented route is replaced when it crosses an unrelated node;
- a straight or curved edge is not silently restyled; if it crosses a node, candidate validation fails and the Agent must generate a routable edge;
- user-originated XML never enters the routing pass.

## Components

### DrawioGeometryIndex

`DrawioGeometryIndex` parses the normalized cells and exposes absolute geometry independently of XML traversal details.

Responsibilities:

- resolve child-relative coordinates through all ancestors;
- identify vertices, groups, containers, swimlanes, decorations, and edge terminals;
- create obstacle rectangles expanded by the configured safety margin;
- expose connection sides and candidate port coordinates;
- expose swimlane header geometry separately from the swimlane body.

Obstacle policy:

- normal nodes, decisions, annotations, and text boxes are obstacles;
- each obstacle is expanded by 12 px by default;
- a swimlane or large container body is not an obstacle because cross-lane edges must traverse it;
- a visible swimlane header is an obstacle;
- invisible groups, backgrounds, and non-interactive decorations are not obstacles;
- an edge's source and target are excluded from its unrelated-obstacle set, but the edge may enter them only through its selected terminal side.

The first version uses conservative rectangular bounds for all shapes. This deliberately leaves extra clearance around diamonds and other non-rectangular shapes and better protects their labels.

### OrthogonalEdgeRouter

`OrthogonalEdgeRouter` accepts a source terminal, a target terminal, obstacle rectangles, and already accepted edge routes. It returns fixed ports and an ordered polyline.

Routing behavior:

1. Select the natural terminal sides from the dominant flow direction. Left-to-right connections prefer source-right and target-left; top-to-bottom connections prefer source-bottom and target-top.
2. Try a direct route or the minimum-turn orthogonal route.
3. If blocked, create channel candidates from obstacle boundaries, terminal center lines, and the configured safety margin.
4. Search above and below for a horizontal main flow, or left and right for a vertical main flow.
5. If boundary-derived channels remain blocked, expand outward in 20 px steps.
6. Choose the lowest-cost node-safe route.

The default search limit is 300 px. If the current canvas bounds permit it, one final search expands to 600 px. Search is finite and deterministic.

Candidate cost is ordered lexicographically so a lower-priority preference can never outweigh node safety:

```text
1. edge-to-node intersection count (must equal zero)
2. total offset distance
3. bend count, weighted by 20
4. edge-to-edge crossing count, weighted by 5
5. total route length, weighted by 0.01
```

Shared or crossing edge segments are allowed when necessary. They affect route selection only after all node-safe requirements are satisfied.

Edges are routed in stable XML order. This makes repeated runs idempotent and lets later edges use earlier routes as a secondary crossing signal.

### DrawioRouteValidator

`DrawioRouteValidator` is independent from the router so it can verify both generated and preserved routes.

Responsibilities:

- ensure every route segment is horizontal or vertical;
- detect intersection between each segment and every unrelated expanded obstacle;
- allow only the terminal segment to touch its corresponding source or target;
- detect duplicate or zero-length consecutive waypoints;
- count edge-to-edge intersections for advisory metrics;
- return stable issue codes and affected cell IDs.

The validator runs after all routes are written. A candidate cannot be persisted when `edge_vertex_intersection_count` is nonzero.

## XML Contract

A routed edge contains fixed entry/exit constraints and explicit points. For example:

```xml
<mxCell
  id="edge_a_b"
  source="a"
  target="b"
  edge="1"
  parent="1"
  style="edgeStyle=segmentEdgeStyle;exitX=1;exitY=0.5;entryX=0;entryY=0.5;html=1;">
  <mxGeometry relative="1" as="geometry">
    <Array as="points">
      <mxPoint x="240" y="80"/>
      <mxPoint x="240" y="20"/>
      <mxPoint x="520" y="20"/>
      <mxPoint x="520" y="80"/>
    </Array>
  </mxGeometry>
</mxCell>
```

The router must preserve unrelated style properties such as color, arrowheads, stroke width, labels, dashed state, and HTML rendering. It replaces only routing properties and route geometry.

The operation schema does not need a public routing input in the first version because automatic processing occurs after the complete candidate XML is assembled. A later change may expose structured ports and points to `connect` if other callers need direct control.

## Quality Report

Successful candidate reports add:

```json
{
  "metrics": {
    "routed_edge_count": 18,
    "rerouted_edge_count": 3,
    "edge_vertex_intersection_count": 0,
    "edge_edge_crossing_count": 2,
    "max_route_offset": 80
  }
}
```

`edge_edge_crossing_count` is advisory. `edge_vertex_intersection_count` is blocking.

When no safe route is found, the tool returns a structured retryable error without persisting the candidate:

```json
{
  "code": "unroutable_edge",
  "edge_id": "edge_review_retry",
  "source_id": "review",
  "target_id": "upload",
  "blocking_node_ids": ["approval", "archive"],
  "attempted_directions": ["above", "below"]
}
```

Other stable routing issues include:

- `edge_vertex_intersection`;
- `non_orthogonal_segment`;
- `duplicate_waypoint`;
- `unsupported_colliding_edge_style`;
- `invalid_nested_geometry`.

## Error Handling

- Routing and validation failures use the existing unsuccessful `create_drawio_board` result path and are retryable when the Agent can adjust layout or edge style.
- The original normalized XML is not persisted when routing fails.
- Failure reports include the edge, terminals, and known blocking nodes so the Agent can make a focused retry.
- The router never moves nodes as a fallback.
- The router never converts a colliding straight or curved edge without an explicit policy decision.
- Unexpected router exceptions are reported as `edge_routing_failed` with no partial candidate persistence.

## Performance

The initial implementation may compare each route candidate with every obstacle because board-mode diagrams are expected to contain a moderate number of nodes and edges. The practical target is to route a 100-node, 150-edge candidate in under 500 ms in the configured Python environment.

If profiling shows that geometry checks dominate, a grid or interval spatial index can be added behind `DrawioGeometryIndex` without changing the router or validator interfaces.

## Testing

### Geometry unit tests

- nested child coordinates resolve to correct absolute bounds;
- multiple ancestor levels resolve correctly;
- swimlane body and header obstacle policies differ;
- invisible groups and background cells are ignored;
- safety margins are applied consistently.

### Router unit tests

- an A-to-C edge with B in the middle routes above or below B;
- a blocked upper channel selects the lower channel;
- blocked initial channels expand outward by the configured step;
- a collision-free existing route remains unchanged;
- a colliding explicit route is replaced;
- an impossible route returns `unroutable_edge`;
- repeated routing of the same XML produces byte-equivalent route geometry;
- node avoidance wins even when the result has more edge crossings.

### Validator unit tests

- segment-to-rectangle intersections report edge and node IDs;
- endpoint contact is allowed only at the selected port;
- zero-length and duplicate points are detected;
- edge-to-edge crossings are counted but do not fail validation;
- the final intersection count must be zero.

### Integration tests

- `create_drawio_board` repairs a colliding AI candidate before persistence;
- a safe candidate persists with routing metrics;
- an unroutable candidate returns a retryable failure and is not persisted;
- straight or curved collisions fail without silent restyling;
- calls without Agent candidate context retain current behavior;
- user saves, draft autosaves, and history restoration never invoke the router;
- exported XML retains routing points and ports after a diagrams.net load/export cycle.

Tests run in the project environment:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/app/tools/visualization/create_drawio_board \
  backend/app/boards -q
```

## Success Criteria

- every persisted AI candidate has zero detected edge-to-unrelated-node intersections;
- an automatically routed edge renders from the explicit route that was validated;
- existing safe explicit routes are preserved;
- user-created and restored XML is never automatically rerouted;
- the router makes no node-position changes;
- edge-to-edge crossings may remain but are reported and considered during route selection;
- routing failure returns actionable structured diagnostics and does not persist a partial candidate;
- existing create, edit, render, accept, and frontend board contracts remain compatible.

