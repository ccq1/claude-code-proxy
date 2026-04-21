#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path


FRAMEWORKS_INDEX_RELATIVE_PATH = "references/frameworks/frameworks_index.json"
TAILWIND_RELATIVE_PATH = "references/frameworks/tailwindcss/tailwind.min.css"
ASSET_EXT_GROUPS = {
    "fonts": {".ttf", ".otf", ".woff", ".woff2"},
    "icons": {".svg", ".ico"},
    "images": {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"},
    "styles": {".css", ".scss", ".less"},
    "scripts": {".js", ".ts"},
}
IGNORE_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
}


@dataclass
class Layout:
    skill_root: Path
    plugin_root: Path


def resolve_layout() -> Layout:
    script_path = Path(__file__).resolve()
    skill_root = script_path.parents[1]
    for parent in script_path.parents:
        if (parent / ".claude-plugin" / "plugin.json").exists():
            return Layout(skill_root=skill_root, plugin_root=parent)
    return Layout(skill_root=skill_root, plugin_root=skill_root.parents[1])


def load_runtime(layout: Layout) -> dict:
    runtime_path = layout.plugin_root / "config" / "runtime.json"
    runtime: dict = {}
    if runtime_path.exists():
        try:
            runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        except Exception:
            runtime = {}

    path_env_to_runtime_key = {
        "FRONTEND_DESIGN_LIBRARY_ROOT": "designLibraryRoot",
        "FRONTEND_ASSETS_ROOT": "frontendAssetsRoot",
    }
    for env_key, runtime_key in path_env_to_runtime_key.items():
        value = configured_path(os.environ.get(env_key))
        if value is not None:
            runtime[runtime_key] = str(value)

    css_pack_value = os.environ.get("FRONTEND_CSS_PACK", "").strip()
    if css_pack_value and not css_pack_value.startswith("{{"):
        runtime["preferredCssPack"] = css_pack_value

    return runtime


def configured_path(value: str | None) -> Path | None:
    if not value:
        return None
    value = value.strip()
    if not value or value.startswith("{{"):
        return None
    return Path(value).expanduser().resolve()


def bundled_design_root(layout: Layout) -> Path:
    return (layout.skill_root / "references" / "design").resolve()


def resolve_design_root(layout: Layout, runtime: dict) -> Path:
    configured = configured_path(str(runtime.get("designLibraryRoot", "")))
    if configured and configured.exists():
        return configured
    return bundled_design_root(layout)


def resolve_assets_root(runtime: dict) -> Path | None:
    configured = configured_path(str(runtime.get("frontendAssetsRoot", "")))
    if configured and configured.exists():
        return configured
    return None


def slug_from_path(path: Path, root: Path) -> str:
    return path.relative_to(root).parts[0]


def resolve_frameworks_index_path(layout: Layout) -> Path:
    return layout.skill_root / FRAMEWORKS_INDEX_RELATIVE_PATH


def load_frameworks(layout: Layout) -> list[dict]:
    index_path = resolve_frameworks_index_path(layout)
    default_frameworks = [
        {
            "name": "tailwindcss",
            "kind": "css",
            "entry": TAILWIND_RELATIVE_PATH,
            "notes": "offline static build for intranet usage",
        }
    ]

    if not index_path.exists():
        return default_frameworks

    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return default_frameworks

    frameworks = []
    for rec in payload.get("frameworks", []):
        name = rec.get("name")
        entry = rec.get("entry")
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(entry, str) or not entry.strip():
            continue
        frameworks.append(
            {
                "name": name.strip().lower(),
                "kind": str(rec.get("kind", "")).strip() or "css",
                "entry": entry.strip(),
                "notes": str(rec.get("notes", "")).strip(),
                "version": str(rec.get("version", "")).strip(),
            }
        )

    return frameworks or default_frameworks


def resolve_preferred_css_pack(runtime: dict) -> str:
    raw_value = str(runtime.get("preferredCssPack", "")).strip().lower()
    if not raw_value or raw_value.startswith("{{"):
        return "tailwindcss"
    return raw_value


def resolve_framework_source(layout: Layout, framework: dict) -> Path:
    entry = Path(str(framework.get("entry", "")))
    if entry.is_absolute():
        return entry
    return (layout.skill_root / entry).resolve()


def select_framework(layout: Layout, runtime: dict, requested_name: str | None = None) -> tuple[dict, str | None]:
    frameworks = load_frameworks(layout)
    framework_map = {rec["name"]: rec for rec in frameworks}

    if requested_name:
        requested_key = requested_name.strip().lower()
        framework = framework_map.get(requested_key)
        if framework is None:
            available = ", ".join(sorted(framework_map))
            raise ValueError(f"unknown framework: {requested_name}. available: {available}")
        return framework, None

    preferred_name = resolve_preferred_css_pack(runtime)
    preferred = framework_map.get(preferred_name)
    if preferred is not None:
        return preferred, None

    fallback = framework_map.get("tailwindcss") or frameworks[0]
    note = f"preferredCssPack={preferred_name} is not bundled; fallback to {fallback['name']}"
    return fallback, note


def sanitize_output_filename(filename: str, fallback: str) -> str:
    candidate = filename.strip() or fallback
    parsed = Path(candidate)
    if parsed.is_absolute() or len(parsed.parts) != 1 or parsed.name in {"", ".", ".."}:
        raise ValueError(f"invalid filename: {filename}")
    return parsed.name


def summarize_design(design_md: Path) -> tuple[str, list[str]]:
    text = design_md.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title = lines[0].lstrip("# ").strip() if lines else design_md.parent.name
    content = text.lower()
    tags = []
    for token in (
        "dashboard",
        "landing",
        "dark",
        "minimal",
        "enterprise",
        "fintech",
        "saas",
        "editorial",
        "product",
    ):
        if token in content:
            tags.append(token)
    return title, tags[:8]


def build_index(layout: Layout, runtime: dict) -> dict:
    root = resolve_design_root(layout, runtime)
    records = []
    for design_md in sorted(root.glob("*/DESIGN.md")):
        slug = slug_from_path(design_md, root)
        title, tags = summarize_design(design_md)
        rec = {
            "slug": slug,
            "title": title,
            "tags": tags,
            "design_md": str(design_md),
        }
        records.append(rec)
    return {"total": len(records), "design_root": str(root), "records": records}


def save_index(layout: Layout, payload: dict) -> Path:
    index_path = layout.skill_root / "references" / "design_index.json"
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index_path


def normalize_index_payload(payload: dict) -> dict:
    records = []
    for rec in payload.get("records", []):
        records.append(
            {
                "slug": rec.get("slug", ""),
                "title": rec.get("title", ""),
                "tags": rec.get("tags", []),
                "design_md": rec.get("design_md", ""),
            }
        )
    return {
        "total": len(records),
        "design_root": payload.get("design_root", ""),
        "records": records,
    }


def load_or_build_index(layout: Layout, runtime: dict) -> dict:
    current_root = resolve_design_root(layout, runtime)
    if current_root != bundled_design_root(layout):
        return build_index(layout, runtime)

    index_path = layout.skill_root / "references" / "design_index.json"
    if index_path.exists():
        try:
            payload = normalize_index_payload(json.loads(index_path.read_text(encoding="utf-8")))
            if payload.get("design_root") == str(current_root):
                save_index(layout, payload)
                return payload
        except Exception:
            pass
    payload = build_index(layout, runtime)
    save_index(layout, payload)
    return payload


def cmd_rebuild_index(layout: Layout, runtime: dict) -> int:
    payload = build_index(layout, runtime)
    current_root = resolve_design_root(layout, runtime)
    if current_root == bundled_design_root(layout):
        path = save_index(layout, payload)
        print(f"index rebuilt: {payload['total']} presets -> {path}")
    else:
        print(f"index rebuilt: {payload['total']} presets -> {current_root}")
        print("note: custom design root index is not persisted into bundled cache")
    return 0


def cmd_list_presets(layout: Layout, runtime: dict) -> int:
    payload = load_or_build_index(layout, runtime)
    print(f"total presets: {payload.get('total', 0)}")
    for rec in payload.get("records", []):
        tags = ",".join(rec.get("tags", []))
        print(f"- {rec['slug']}: {rec['title']} [{tags}]")
    return 0


def score_record(rec: dict, query_tokens: list[str]) -> int:
    haystack = " ".join([rec.get("slug", ""), rec.get("title", ""), " ".join(rec.get("tags", []))]).lower()
    score = 0
    for tok in query_tokens:
        if tok in rec.get("slug", "").lower():
            score += 5
        if tok in rec.get("title", "").lower():
            score += 4
        if tok in haystack:
            score += 2
    return score


def cmd_search_design(layout: Layout, runtime: dict, query: str, limit: int) -> int:
    payload = load_or_build_index(layout, runtime)
    tokens = [t.strip().lower() for t in query.split() if t.strip()]
    matches = []
    for rec in payload.get("records", []):
        sc = score_record(rec, tokens)
        if sc > 0:
            matches.append((sc, rec))
    matches.sort(key=lambda x: (-x[0], x[1]["slug"]))
    if not matches:
        print("no matched design preset")
        return 0
    for sc, rec in matches[:limit]:
        print(f"{rec['slug']} | score={sc} | {rec['title']}")
        print(f"  design_md: {rec['design_md']}")
    return 0


def cmd_inspect_design(layout: Layout, runtime: dict, slug: str) -> int:
    payload = load_or_build_index(layout, runtime)
    rec = next((r for r in payload.get("records", []) if r.get("slug") == slug), None)
    if not rec:
        print(f"design slug not found: {slug}")
        return 1
    design_path = Path(rec["design_md"])
    text = design_path.read_text(encoding="utf-8", errors="replace")
    snippet_lines = []
    for line in text.splitlines():
        if line.strip().startswith("## "):
            snippet_lines.append(line.strip())
        if len(snippet_lines) >= 8:
            break
    print(f"slug: {rec['slug']}")
    print(f"title: {rec['title']}")
    print(f"design_md: {rec['design_md']}")
    print("sections:")
    for line in snippet_lines:
        print(f"- {line}")
    return 0


def walk_assets(root: Path):
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in IGNORE_DIRS)
        for filename in sorted(filenames):
            yield Path(current_root) / filename


def cmd_inventory_assets(root: Path, limit: int) -> int:
    if not root.exists():
        print(f"assets root not found: {root}")
        return 1
    if not root.is_dir():
        print(f"assets root is not a directory: {root}")
        return 1
    counters = {k: 0 for k in ASSET_EXT_GROUPS}
    sample = {k: [] for k in ASSET_EXT_GROUPS}
    other_count = 0
    for path in walk_assets(root):
        suffix = path.suffix.lower()
        group = None
        for key, exts in ASSET_EXT_GROUPS.items():
            if suffix in exts:
                group = key
                break
        if group is None:
            other_count += 1
            continue
        counters[group] += 1
        if len(sample[group]) < limit:
            sample[group].append(str(path))
    print(f"asset root: {root}")
    for key in ("fonts", "icons", "images", "styles", "scripts"):
        print(f"{key}: {counters[key]}")
        for item in sample[key]:
            print(f"  - {item}")
    print(f"other_files: {other_count}")
    return 0


def resolve_tailwind_path(layout: Layout) -> Path:
    return layout.skill_root / TAILWIND_RELATIVE_PATH


def cmd_list_frameworks(layout: Layout, runtime: dict) -> int:
    preferred_name = resolve_preferred_css_pack(runtime)
    fallback_note = None
    try:
        active_framework, fallback_note = select_framework(layout, runtime)
    except ValueError as exc:
        print(str(exc))
        return 1

    print("frameworks:")
    for framework in load_frameworks(layout):
        source = resolve_framework_source(layout, framework)
        status = "ready" if source.exists() else "missing"
        marker = " | preferred" if framework["name"] == active_framework["name"] else ""
        version = framework.get("version")
        version_suffix = f" | v{version}" if version else ""
        print(f"- {framework['name']} | {status}{version_suffix}{marker} | {source}")
    if fallback_note:
        print(f"note: {fallback_note}")
    elif preferred_name == active_framework["name"]:
        print(f"preferredCssPack: {preferred_name}")
    return 0


def cmd_install_framework(
    layout: Layout,
    runtime: dict,
    output_dir: Path,
    filename: str | None,
    framework_name: str | None = None,
) -> int:
    try:
        framework, fallback_note = select_framework(layout, runtime, requested_name=framework_name)
        source = resolve_framework_source(layout, framework)
        safe_filename = sanitize_output_filename(filename or source.name, source.name)
    except ValueError as exc:
        print(str(exc))
        return 1

    if not source.exists():
        print(f"framework package not found: {source}")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    target = (output_dir / safe_filename).resolve()
    shutil.copy2(source, target)
    print(f"framework installed: {framework['name']} -> {target}")
    if fallback_note:
        print(f"note: {fallback_note}")
    return 0


def cmd_install_tailwind(layout: Layout, runtime: dict, output_dir: Path, filename: str) -> int:
    return cmd_install_framework(
        layout=layout,
        runtime=runtime,
        output_dir=output_dir,
        filename=filename,
        framework_name="tailwindcss",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline frontend helper for plugin skill workflows.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("rebuild-index")
    sub.add_parser("list-presets")

    p_search = sub.add_parser("search-design")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=10)

    p_inspect = sub.add_parser("inspect-design")
    p_inspect.add_argument("slug")

    p_inv = sub.add_parser("inventory-assets")
    p_inv.add_argument("--root", default="")
    p_inv.add_argument("--limit", type=int, default=5)

    sub.add_parser("list-frameworks")

    p_install_framework = sub.add_parser("install-framework")
    p_install_framework.add_argument("output_dir")
    p_install_framework.add_argument("--framework", default="")
    p_install_framework.add_argument("--filename", default="")

    p_install_tw = sub.add_parser("install-tailwind")
    p_install_tw.add_argument("output_dir")
    p_install_tw.add_argument("--filename", default="tailwind.min.css")

    return parser


def main() -> int:
    layout = resolve_layout()
    runtime = load_runtime(layout)
    args = build_parser().parse_args()

    if args.cmd == "rebuild-index":
        return cmd_rebuild_index(layout, runtime)
    if args.cmd == "list-presets":
        return cmd_list_presets(layout, runtime)
    if args.cmd == "search-design":
        return cmd_search_design(layout, runtime, args.query, args.limit)
    if args.cmd == "inspect-design":
        return cmd_inspect_design(layout, runtime, args.slug)
    if args.cmd == "inventory-assets":
        runtime_root = resolve_assets_root(runtime)
        root = Path(args.root).expanduser().resolve() if args.root else runtime_root
        if root is None:
            print("assets root not provided. use --root or set frontendAssetsRoot in config/runtime.json")
            return 1
        return cmd_inventory_assets(root, args.limit)
    if args.cmd == "list-frameworks":
        return cmd_list_frameworks(layout, runtime)
    if args.cmd == "install-framework":
        return cmd_install_framework(
            layout=layout,
            runtime=runtime,
            output_dir=Path(args.output_dir).expanduser().resolve(),
            filename=args.filename or None,
            framework_name=args.framework or None,
        )
    if args.cmd == "install-tailwind":
        return cmd_install_tailwind(
            layout=layout,
            runtime=runtime,
            output_dir=Path(args.output_dir).expanduser().resolve(),
            filename=args.filename,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
