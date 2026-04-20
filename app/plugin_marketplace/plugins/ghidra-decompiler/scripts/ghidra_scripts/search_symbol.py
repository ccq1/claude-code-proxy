# -*- coding: utf-8 -*-
# @runtime Jython

from common import (
    function_sort_key,
    function_to_dict,
    iter_functions,
    iter_symbols,
    load_request_and_output,
    normalize_text,
    symbol_to_dict,
    write_json,
)


def main():
    output_path, request = load_request_and_output(getScriptArgs())
    query = normalize_text(request.get("query", "")).strip().lower()
    limit = int(request.get("limit", 50))
    if not query:
        raise RuntimeError("query is required")

    function_matches = []
    symbol_matches = []
    seen = set()

    for function in iter_functions(currentProgram):
        item = function_to_dict(function, currentProgram)
        haystack = " ".join(
            filter(
                None,
                [
                    item.get("name"),
                    item.get("full_name"),
                    item.get("signature"),
                    item.get("namespace"),
                ],
            )
        ).lower()
        if query not in haystack:
            continue
        key = ("function", item.get("name"), item.get("entry_point"))
        if key in seen:
            continue
        seen.add(key)
        item["kind"] = "FUNCTION"
        item["match_source"] = "function"
        function_matches.append(item)

    function_matches.sort(key=function_sort_key)

    for symbol in iter_symbols(currentProgram):
        item = symbol_to_dict(symbol)
        haystack = " ".join(
            filter(None, [item.get("name"), item.get("namespace"), item.get("kind")])
        ).lower()
        if query not in haystack:
            continue
        key = (item.get("kind"), item.get("name"), item.get("address"))
        if key in seen:
            continue
        seen.add(key)
        item["match_source"] = "symbol"
        symbol_matches.append(item)

    symbol_matches.sort(
        key=lambda item: (
            1 if item.get("is_external") else 0,
            normalize_text(item.get("kind") or ""),
            normalize_text(item.get("name") or ""),
            normalize_text(item.get("address") or ""),
        )
    )

    all_matches = function_matches + symbol_matches
    matches = all_matches[:limit]
    total = len(all_matches)

    write_json(
        output_path,
        {
            "program_id": request.get("program_id"),
            "query": request.get("query"),
            "total_matches": total,
            "returned": len(matches),
            "limit": limit,
            "truncated": total > len(matches),
            "matches": matches,
        },
    )


main()
