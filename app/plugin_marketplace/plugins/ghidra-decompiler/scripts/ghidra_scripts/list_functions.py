# -*- coding: utf-8 -*-
# @runtime Jython

from common import function_to_dict, iter_functions, load_request_and_output, normalize_text, write_json


def main():
    output_path, request = load_request_and_output(getScriptArgs())

    query = normalize_text(request.get("query", "")).strip().lower()
    limit = int(request.get("limit", 100))
    offset = int(request.get("offset", 0))

    all_functions = []
    for function in iter_functions(currentProgram):
        item = function_to_dict(function)
        if query and query not in item["name"].lower():
            continue
        all_functions.append(item)

    sliced = all_functions[offset : offset + limit]
    write_json(
        output_path,
        {
            "program_id": request.get("program_id"),
            "total_matches": len(all_functions),
            "returned": len(sliced),
            "offset": offset,
            "limit": limit,
            "truncated": offset + limit < len(all_functions),
            "functions": sliced,
        },
    )


main()
