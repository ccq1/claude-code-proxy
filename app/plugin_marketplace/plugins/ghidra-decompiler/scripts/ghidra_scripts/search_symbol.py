# -*- coding: utf-8 -*-
# @runtime Jython

from common import function_to_dict, iter_functions, iter_symbols, load_request_and_output, normalize_text, symbol_to_dict, write_json


def main():
    output_path, request = load_request_and_output(getScriptArgs())
    query = normalize_text(request.get("query", "")).strip().lower()
    limit = int(request.get("limit", 50))
    if not query:
        raise RuntimeError("query is required")

    matches = []
    total = 0
    seen = set()

    for function in iter_functions(currentProgram):
        item = function_to_dict(function)
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
        total += 1
        if len(matches) < limit:
            item["kind"] = "FUNCTION"
            matches.append(item)

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
        total += 1
        if len(matches) < limit:
            matches.append(item)

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
