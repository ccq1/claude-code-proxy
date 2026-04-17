#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import deque
from pathlib import Path


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _guess_file(workdir: Path, prefixes: tuple[str, ...], suffixes: tuple[str, ...]) -> Path | None:
    for prefix in prefixes:
        for suffix in suffixes:
            for path in sorted(workdir.glob(f"{prefix}*{suffix}")):
                if path.is_file():
                    return path
    return None


def load_nodes(path: Path) -> dict[str, dict[str, str]]:
    nodes: dict[str, dict[str, str]] = {}
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                node_id = str(row.get("id") or row.get("name") or "").strip()
                if not node_id:
                    continue
                nodes[node_id] = {
                    "id": node_id,
                    "label": str(row.get("label") or row.get("type") or "asset"),
                }
        return nodes

    payload = _load_json(path)
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict) and isinstance(payload.get("nodes"), list):
        candidates = payload["nodes"]
    else:
        candidates = []

    for item in candidates:
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("id") or item.get("name") or "").strip()
        if not node_id:
            continue
        nodes[node_id] = {
            "id": node_id,
            "label": str(item.get("label") or item.get("type") or "asset"),
        }
    return nodes


def load_edges(path: Path) -> list[dict[str, object]]:
    edges: list[dict[str, object]] = []
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                source = str(row.get("source") or row.get("src") or "").strip()
                target = str(row.get("target") or row.get("dst") or "").strip()
                if not source or not target:
                    continue
                edges.append(
                    {
                        "source": source,
                        "target": target,
                        "kind": str(row.get("kind") or row.get("edge_type") or "relation"),
                        "confidence": float(row.get("confidence") or 0.6),
                        "evidence": str(row.get("evidence") or ""),
                    }
                )
        return edges

    payload = _load_json(path)
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict) and isinstance(payload.get("edges"), list):
        candidates = payload["edges"]
    else:
        candidates = []

    for item in candidates:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or item.get("src") or "").strip()
        target = str(item.get("target") or item.get("dst") or "").strip()
        if not source or not target:
            continue
        confidence = item.get("confidence", 0.6)
        try:
            confidence = float(confidence)
        except Exception:
            confidence = 0.6
        edges.append(
            {
                "source": source,
                "target": target,
                "kind": str(item.get("kind") or item.get("edge_type") or "relation"),
                "confidence": confidence,
                "evidence": str(item.get("evidence") or ""),
            }
        )
    return edges


def build_adjacency(edges: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    graph: dict[str, list[dict[str, object]]] = {}
    for edge in edges:
        source = str(edge["source"])
        graph.setdefault(source, []).append(edge)
    return graph


def shortest_path(graph: dict[str, list[dict[str, object]]], start: str, target: str) -> list[dict[str, object]]:
    queue = deque([(start, [])])
    visited = {start}

    while queue:
        current, path = queue.popleft()
        if current == target:
            return path

        for edge in graph.get(current, []):
            nxt = str(edge["target"])
            if nxt in visited:
                continue
            visited.add(nxt)
            queue.append((nxt, path + [edge]))

    return []


def confidence_label(value: float) -> str:
    if value >= 0.8:
        return "confirmed"
    if value >= 0.5:
        return "likely"
    return "speculative"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build recommended attack paths from local node/edge exports.")
    parser.add_argument("--workdir", default=".", help="Directory containing node/edge exports.")
    parser.add_argument("--nodes", default="", help="Explicit node csv/json path.")
    parser.add_argument("--edges", default="", help="Explicit edge csv/json path.")
    parser.add_argument("--start", required=True, help="Start node id.")
    parser.add_argument("--target", required=True, help="Target node id.")
    parser.add_argument("--output", default="attack_path_report.json", help="Output report file name.")
    args = parser.parse_args()

    workdir = Path(args.workdir).expanduser().resolve()

    node_file = Path(args.nodes).expanduser().resolve() if args.nodes else _guess_file(workdir, ("nodes", "hosts", "assets"), (".csv", ".json"))
    edge_file = Path(args.edges).expanduser().resolve() if args.edges else _guess_file(workdir, ("edges", "acl", "sessions", "relations"), (".csv", ".json"))

    if not node_file or not node_file.exists():
        raise SystemExit("No node file found. Provide --nodes or add nodes*.csv/json")
    if not edge_file or not edge_file.exists():
        raise SystemExit("No edge file found. Provide --edges or add edges*.csv/json")

    nodes = load_nodes(node_file)
    edges = load_edges(edge_file)
    graph = build_adjacency(edges)

    path_edges = shortest_path(graph, args.start, args.target)

    steps: list[dict[str, object]] = []
    for edge in path_edges:
        confidence = float(edge.get("confidence", 0.6))
        steps.append(
            {
                "source": edge["source"],
                "target": edge["target"],
                "kind": edge.get("kind", "relation"),
                "evidence": edge.get("evidence", ""),
                "confidence": confidence,
                "label": confidence_label(confidence),
            }
        )

    avg_confidence = sum(step["confidence"] for step in steps) / len(steps) if steps else 0.0

    report = {
        "start": args.start,
        "target": args.target,
        "nodeFile": str(node_file),
        "edgeFile": str(edge_file),
        "nodeCount": len(nodes),
        "edgeCount": len(edges),
        "pathFound": bool(steps),
        "pathLength": len(steps),
        "averageConfidence": round(avg_confidence, 3),
        "steps": steps,
    }

    out_path = workdir / args.output
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Report: {out_path}")
    if not steps:
        print("No path found between start and target.")
        return 2

    print(f"Path found: {args.start} -> {args.target} with {len(steps)} steps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
