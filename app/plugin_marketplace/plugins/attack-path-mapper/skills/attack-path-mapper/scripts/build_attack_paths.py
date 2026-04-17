#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import deque
from pathlib import Path
from typing import Any


TEXT_SUFFIXES = {".txt", ".md", ".log", ".conf", ".cfg", ".ini", ".xml", ".yml", ".yaml"}
DATA_SUFFIXES = {".csv", ".json"}
MAX_AUTO_FILE_BYTES = 5 * 1024 * 1024
MAX_DEPTH_CONF_PATH = 8

EDGE_SOURCE_KEYS = ("source", "src", "from", "from_node")
EDGE_TARGET_KEYS = ("target", "dst", "to", "to_node")
EDGE_KIND_KEYS = ("kind", "edge_type", "relation", "protocol", "service", "access")
EDGE_CONF_KEYS = ("confidence", "score", "weight", "probability")
EDGE_EVIDENCE_KEYS = ("evidence", "note", "reason", "description", "details")

NODE_ID_KEYS = ("id", "name", "node", "host", "asset")
NODE_LABEL_KEYS = ("label", "type", "category", "role")


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _guess_file(workdir: Path, prefixes: tuple[str, ...], suffixes: tuple[str, ...]) -> Path | None:
    for prefix in prefixes:
        for suffix in suffixes:
            for path in sorted(workdir.glob(f"{prefix}*{suffix}")):
                if path.is_file():
                    return path
    return None


def _safe_float(value: object, default: float = 0.6) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    return max(0.05, min(parsed, 0.99))


def _pick(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        raw = row.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    return ""


def load_nodes(path: Path) -> dict[str, dict[str, str]]:
    nodes: dict[str, dict[str, str]] = {}
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                node_id = _pick(row, NODE_ID_KEYS)
                if not node_id:
                    continue
                nodes[node_id] = {
                    "id": node_id,
                    "label": _pick(row, NODE_LABEL_KEYS) or infer_label(node_id),
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
        node_id = _pick(item, NODE_ID_KEYS)
        if not node_id:
            continue
        nodes[node_id] = {
            "id": node_id,
            "label": _pick(item, NODE_LABEL_KEYS) or infer_label(node_id),
        }
    return nodes


def load_edges(path: Path) -> list[dict[str, object]]:
    edges: list[dict[str, object]] = []
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                source = _pick(row, EDGE_SOURCE_KEYS)
                target = _pick(row, EDGE_TARGET_KEYS)
                if not source or not target:
                    continue
                edges.append(
                    {
                        "source": source,
                        "target": target,
                        "kind": _pick(row, EDGE_KIND_KEYS) or "relation",
                        "confidence": _safe_float(_pick(row, EDGE_CONF_KEYS) or 0.6),
                        "evidence": _pick(row, EDGE_EVIDENCE_KEYS),
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
        source = _pick(item, EDGE_SOURCE_KEYS)
        target = _pick(item, EDGE_TARGET_KEYS)
        if not source or not target:
            continue
        edges.append(
            {
                "source": source,
                "target": target,
                "kind": _pick(item, EDGE_KIND_KEYS) or "relation",
                "confidence": _safe_float(_pick(item, EDGE_CONF_KEYS) or 0.6),
                "evidence": _pick(item, EDGE_EVIDENCE_KEYS),
            }
        )
    return edges


def infer_label(node_id: str) -> str:
    lowered = node_id.lower()
    if lowered.startswith(("user", "adm", "svc_", "svc-")):
        return "user"
    if lowered.startswith(("ws", "wkst", "desktop", "laptop")):
        return "workstation"
    if lowered.startswith(("dc", "kdc")):
        return "domain-controller"
    if lowered.startswith(("fw", "firewall")):
        return "firewall"
    if lowered.startswith(("rt", "rtr", "router")):
        return "router"
    if lowered.startswith(("sw", "switch")):
        return "switch"
    if lowered.startswith(("sql", "db", "crown")):
        return "database-server"
    if lowered.startswith(("srv", "server", "app")):
        return "server"
    return "asset"


EDGE_TEXT_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"\b([A-Za-z0-9_.:-]+)\s*->\s*([A-Za-z0-9_.:-]+)\b"), "relation", 0.62),
    (re.compile(r"\b([A-Za-z0-9_.:-]+)\s+can\s+reach\s+([A-Za-z0-9_.:-]+)\b", re.I), "network_reach", 0.72),
    (re.compile(r"\b([A-Za-z0-9_.:-]+)\s+rdp\s+to\s+([A-Za-z0-9_.:-]+)\b", re.I), "rdp_lateral", 0.74),
    (re.compile(r"\b([A-Za-z0-9_.:-]+)\s+winrm\s+to\s+([A-Za-z0-9_.:-]+)\b", re.I), "winrm_lateral", 0.71),
    (re.compile(r"\b([A-Za-z0-9_.:-]+)\s+smb\s+to\s+([A-Za-z0-9_.:-]+)\b", re.I), "smb_lateral", 0.7),
    (re.compile(r"\b([A-Za-z0-9_.:-]+)\s+admin\s+on\s+([A-Za-z0-9_.:-]+)\b", re.I), "admin_path", 0.78),
    (re.compile(r"\b([A-Za-z0-9_.:-]+)\s+member\s+of\s+([A-Za-z0-9_.:-]+)\b", re.I), "group_membership", 0.76),
    (re.compile(r"\b([A-Za-z0-9_.:-]+)\s+trusts\s+([A-Za-z0-9_.:-]+)\b", re.I), "service_trust", 0.67),
]

BLOCK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bdeny\b.*?\bfrom\s+([A-Za-z0-9_.:-]+)\s+to\s+([A-Za-z0-9_.:-]+)", re.I),
    re.compile(r"\b([A-Za-z0-9_.:-]+)\s+blocked\s+to\s+([A-Za-z0-9_.:-]+)", re.I),
    re.compile(r"\bfirewall\b.*?\b([A-Za-z0-9_.:-]+)\s*->\s*([A-Za-z0-9_.:-]+).*?\bdeny\b", re.I),
]

TOKEN_NODE_RE = re.compile(r"\b(?:user\d+|ws\d+|srv\d+|dc[-_a-z0-9]+|kdc\d+|fw\d+|router\d+|switch\d+|[a-zA-Z][a-zA-Z0-9_-]{3,30})\b")


def _extract_structured_from_csv(path: Path) -> tuple[dict[str, dict[str, str]], list[dict[str, object]], set[tuple[str, str]], int]:
    nodes: dict[str, dict[str, str]] = {}
    edges: list[dict[str, object]] = []
    blocked: set[tuple[str, str]] = set()
    lines_used = 0

    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        reader = csv.DictReader(handle)
        headers = [h.strip().lower() for h in (reader.fieldnames or [])]
        has_edge_cols = any(h in EDGE_SOURCE_KEYS for h in headers) and any(h in EDGE_TARGET_KEYS for h in headers)
        has_node_cols = any(h in NODE_ID_KEYS for h in headers)

        for row_idx, row in enumerate(reader, start=2):
            if has_node_cols:
                node_id = _pick(row, NODE_ID_KEYS)
                if node_id:
                    nodes[node_id] = {"id": node_id, "label": _pick(row, NODE_LABEL_KEYS) or infer_label(node_id)}
                    lines_used += 1

            if has_edge_cols:
                source = _pick(row, EDGE_SOURCE_KEYS)
                target = _pick(row, EDGE_TARGET_KEYS)
                if source and target:
                    action = _pick(row, ("action", "policy", "rule_action")).lower()
                    if action in {"deny", "drop", "blocked", "block"}:
                        blocked.add((source, target))
                    else:
                        edges.append(
                            {
                                "source": source,
                                "target": target,
                                "kind": _pick(row, EDGE_KIND_KEYS) or "relation",
                                "confidence": _safe_float(_pick(row, EDGE_CONF_KEYS) or 0.68),
                                "evidence": f"{path.name}:{row_idx}",
                            }
                        )
                    lines_used += 1
    return nodes, edges, blocked, lines_used


def _extract_structured_from_json(path: Path) -> tuple[dict[str, dict[str, str]], list[dict[str, object]], set[tuple[str, str]], int]:
    nodes: dict[str, dict[str, str]] = {}
    edges: list[dict[str, object]] = []
    blocked: set[tuple[str, str]] = set()
    hits = 0

    def walk(obj: object) -> None:
        nonlocal hits
        if isinstance(obj, dict):
            source = _pick(obj, EDGE_SOURCE_KEYS)
            target = _pick(obj, EDGE_TARGET_KEYS)
            if source and target:
                action = _pick(obj, ("action", "policy", "rule_action")).lower()
                if action in {"deny", "drop", "blocked", "block"}:
                    blocked.add((source, target))
                else:
                    edges.append(
                        {
                            "source": source,
                            "target": target,
                            "kind": _pick(obj, EDGE_KIND_KEYS) or "relation",
                            "confidence": _safe_float(_pick(obj, EDGE_CONF_KEYS) or 0.7),
                            "evidence": path.name,
                        }
                    )
                hits += 1

            node_id = _pick(obj, NODE_ID_KEYS)
            if node_id:
                nodes[node_id] = {"id": node_id, "label": _pick(obj, NODE_LABEL_KEYS) or infer_label(node_id)}
                hits += 1

            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    try:
        payload = _load_json(path)
    except Exception:
        return nodes, edges, blocked, hits

    walk(payload)
    return nodes, edges, blocked, hits


def _extract_from_text(path: Path) -> tuple[dict[str, dict[str, str]], list[dict[str, object]], set[tuple[str, str]], int]:
    nodes: dict[str, dict[str, str]] = {}
    edges: list[dict[str, object]] = []
    blocked: set[tuple[str, str]] = set()
    hits = 0

    text = path.read_text(encoding="utf-8", errors="ignore")
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue

        for token in TOKEN_NODE_RE.findall(line):
            nodes.setdefault(token, {"id": token, "label": infer_label(token)})

        for pattern in BLOCK_PATTERNS:
            m = pattern.search(line)
            if m:
                blocked.add((m.group(1), m.group(2)))
                hits += 1

        for pattern, kind, conf in EDGE_TEXT_PATTERNS:
            m = pattern.search(line)
            if not m:
                continue
            source = m.group(1)
            target = m.group(2)
            edges.append(
                {
                    "source": source,
                    "target": target,
                    "kind": kind,
                    "confidence": conf,
                    "evidence": f"{path.name}:{line_no}",
                }
            )
            hits += 1

    return nodes, edges, blocked, hits


def discover_graph(workdir: Path, start: str, target: str) -> tuple[dict[str, dict[str, str]], list[dict[str, object]], dict[str, object]]:
    nodes: dict[str, dict[str, str]] = {}
    edges: list[dict[str, object]] = []
    blocked_pairs: set[tuple[str, str]] = set()
    scanned_files = 0
    discovered_hits = 0
    used_files: set[str] = set()

    for path in sorted(workdir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES | DATA_SUFFIXES:
            continue
        if path.name == "attack_path_report.json":
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > MAX_AUTO_FILE_BYTES:
            continue

        scanned_files += 1
        suffix = path.suffix.lower()

        file_nodes: dict[str, dict[str, str]] = {}
        file_edges: list[dict[str, object]] = []
        file_blocked: set[tuple[str, str]] = set()
        hits = 0

        if suffix == ".csv":
            file_nodes, file_edges, file_blocked, hits = _extract_structured_from_csv(path)
        elif suffix == ".json":
            file_nodes, file_edges, file_blocked, hits = _extract_structured_from_json(path)
        else:
            file_nodes, file_edges, file_blocked, hits = _extract_from_text(path)

        if hits:
            used_files.add(str(path))
            discovered_hits += hits

        for node_id, node in file_nodes.items():
            nodes[node_id] = node
        edges.extend(file_edges)
        blocked_pairs.update(file_blocked)

    nodes.setdefault(start, {"id": start, "label": infer_label(start)})
    nodes.setdefault(target, {"id": target, "label": infer_label(target)})

    dedup: dict[tuple[str, str, str], dict[str, object]] = {}
    for edge in edges:
        source = str(edge["source"]).strip()
        target_node = str(edge["target"]).strip()
        if not source or not target_node:
            continue
        if (source, target_node) in blocked_pairs:
            continue

        kind = str(edge.get("kind", "relation"))
        key = (source, target_node, kind)
        current = dedup.get(key)
        if not current or float(edge.get("confidence", 0.6)) > float(current.get("confidence", 0.6)):
            dedup[key] = {
                "source": source,
                "target": target_node,
                "kind": kind,
                "confidence": _safe_float(edge.get("confidence", 0.6)),
                "evidence": str(edge.get("evidence", "")),
            }

    final_edges = sorted(dedup.values(), key=lambda e: (e["source"], e["target"], e["kind"]))

    telemetry = {
        "mode": "auto_discovery",
        "scannedFiles": scanned_files,
        "usedFiles": sorted(used_files),
        "discoveredSignals": discovered_hits,
        "blockedEdgeCount": len(blocked_pairs),
    }
    return nodes, final_edges, telemetry


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


def highest_confidence_path(graph: dict[str, list[dict[str, object]]], start: str, target: str) -> list[dict[str, object]]:
    best_path: list[dict[str, object]] = []
    best_score = -1.0

    stack: list[tuple[str, list[dict[str, object]], set[str], int]] = [(start, [], {start}, 0)]
    while stack:
        node, path, visited, depth = stack.pop()
        if depth > MAX_DEPTH_CONF_PATH:
            continue
        if node == target and path:
            score = 1.0
            for edge in path:
                score *= float(edge.get("confidence", 0.6))
            if score > best_score:
                best_score = score
                best_path = path
            continue

        for edge in graph.get(node, []):
            nxt = str(edge["target"])
            if nxt in visited:
                continue
            stack.append((nxt, path + [edge], visited | {nxt}, depth + 1))

    return best_path


def path_score(path: list[dict[str, object]]) -> float:
    if not path:
        return -1.0
    avg_conf = sum(float(e.get("confidence", 0.6)) for e in path) / len(path)
    # Reward confidence, penalize operational length.
    return avg_conf * 1.2 - len(path) * 0.08


def confidence_label(value: float) -> str:
    if value >= 0.8:
        return "confirmed"
    if value >= 0.5:
        return "likely"
    return "speculative"


def _decorate_steps(path_edges: list[dict[str, object]]) -> list[dict[str, object]]:
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
    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description="Build recommended attack paths from local evidence with auto-discovery fallback.")
    parser.add_argument("--workdir", default=".", help="Directory containing topology, host, policy, and relationship evidence.")
    parser.add_argument("--nodes", default="", help="Explicit node csv/json path.")
    parser.add_argument("--edges", default="", help="Explicit edge csv/json path.")
    parser.add_argument("--start", required=True, help="Start node id.")
    parser.add_argument("--target", required=True, help="Target node id.")
    parser.add_argument("--output", default="attack_path_report.json", help="Output report file name.")
    parser.add_argument(
        "--disable-auto-discovery",
        action="store_true",
        help="When set, fail if explicit/guessed nodes and edges are unavailable.",
    )
    args = parser.parse_args()

    workdir = Path(args.workdir).expanduser().resolve()

    node_file = Path(args.nodes).expanduser().resolve() if args.nodes else _guess_file(workdir, ("nodes", "hosts", "assets"), (".csv", ".json"))
    edge_file = Path(args.edges).expanduser().resolve() if args.edges else _guess_file(workdir, ("edges", "acl", "sessions", "relations"), (".csv", ".json"))

    telemetry: dict[str, object] = {}
    if node_file and node_file.exists() and edge_file and edge_file.exists():
        nodes = load_nodes(node_file)
        edges = load_edges(edge_file)
        telemetry = {
            "mode": "structured",
            "nodeFile": str(node_file),
            "edgeFile": str(edge_file),
        }
    else:
        if args.disable_auto_discovery:
            raise SystemExit("No node/edge files found and auto-discovery is disabled.")
        nodes, edges, telemetry = discover_graph(workdir, args.start, args.target)

    graph = build_adjacency(edges)

    shortest = shortest_path(graph, args.start, args.target)
    highest_conf = highest_confidence_path(graph, args.start, args.target)

    selected = shortest
    strategy = "shortest_path"
    if path_score(highest_conf) > path_score(shortest):
        selected = highest_conf
        strategy = "balanced_confidence"

    steps = _decorate_steps(selected)
    avg_confidence = sum(step["confidence"] for step in steps) / len(steps) if steps else 0.0

    report = {
        "start": args.start,
        "target": args.target,
        "nodeCount": len(nodes),
        "edgeCount": len(edges),
        "pathFound": bool(steps),
        "pathLength": len(steps),
        "averageConfidence": round(avg_confidence, 3),
        "selectionStrategy": strategy,
        "candidates": {
            "shortest": _decorate_steps(shortest),
            "highestConfidence": _decorate_steps(highest_conf),
        },
        "steps": steps,
        "telemetry": telemetry,
    }

    out_path = workdir / args.output
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Report: {out_path}")
    if not steps:
        print("No path found between start and target.")
        return 2

    print(
        "Path found: {0} -> {1} with {2} steps (strategy={3})".format(
            args.start,
            args.target,
            len(steps),
            strategy,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
