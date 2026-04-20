# -*- coding: utf-8 -*-
# @runtime Jython

from common import function_sort_key, function_to_dict, iter_functions, load_request_and_output, normalize_text, write_json


AUTO_NAME_PREFIXES = ("FUN_", "LAB_", "DAT_", "SUB_", "UNK_", "PTR_")


def _looks_auto_named(name):
    if not name:
        return True
    upper_name = normalize_text(name).upper()
    for prefix in AUTO_NAME_PREFIXES:
        if upper_name.startswith(prefix):
            return True
    return False


def _import_item(symbol):
    kind = None
    try:
        kind = normalize_text(symbol.getSymbolType().toString())
    except Exception:
        kind = normalize_text(symbol.getSymbolType())

    namespace = None
    try:
        namespace = normalize_text(symbol.getParentNamespace().getName())
    except Exception:
        namespace = None

    try:
        reference_count = int(len(symbol.getReferences()))
    except Exception:
        reference_count = None

    return {
        "name": normalize_text(symbol.getName()),
        "address": normalize_text(symbol.getAddress().toString()),
        "kind": kind,
        "library": namespace,
        "reference_count": reference_count,
    }


def _export_item(function):
    item = function_to_dict(function, currentProgram)
    item["heuristic"] = True
    return item


def main():
    output_path, request = load_request_and_output(getScriptArgs())
    query = normalize_text(request.get("query", "")).strip().lower()
    limit = int(request.get("limit", 200))

    symbol_table = currentProgram.getSymbolTable()

    imports = []
    seen_imports = set()
    external_symbols = symbol_table.getExternalSymbols()
    while external_symbols.hasNext():
        symbol = external_symbols.next()
        item = _import_item(symbol)
        haystack = " ".join(filter(None, [item.get("name"), item.get("library"), item.get("kind")])).lower()
        if query and query not in haystack:
            continue
        key = (item.get("name"), item.get("library"), item.get("address"))
        if key in seen_imports:
            continue
        seen_imports.add(key)
        imports.append(item)

    imports.sort(key=lambda item: (item.get("library") or "", item.get("name") or "", item.get("address") or ""))

    exports = []
    seen_exports = set()
    for function in iter_functions(currentProgram):
        item = function_to_dict(function, currentProgram)
        if item.get("is_external"):
            continue
        if not item.get("is_entry_point") and _looks_auto_named(item.get("name")):
            continue
        haystack = " ".join(filter(None, [item.get("name"), item.get("full_name"), item.get("namespace")])).lower()
        if query and query not in haystack:
            continue
        key = (item.get("name"), item.get("entry_point"))
        if key in seen_exports:
            continue
        seen_exports.add(key)
        exports.append(_export_item(function))

    exports.sort(key=function_sort_key)

    write_json(
        output_path,
        {
            "success": True,
            "program_id": request.get("program_id"),
            "query": request.get("query"),
            "imports": imports[:limit],
            "exports": exports[:limit],
            "import_count": len(imports),
            "export_count": len(exports),
            "limit": limit,
            "imports_truncated": len(imports) > limit,
            "exports_truncated": len(exports) > limit,
            "exports_are_heuristic": True,
        },
    )


main()
