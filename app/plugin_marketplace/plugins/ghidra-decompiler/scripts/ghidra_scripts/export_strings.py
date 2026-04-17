# -*- coding: utf-8 -*-
# @runtime Jython

import codecs
import json

from common import iter_string_data, load_request_and_output, normalize_text, string_data_to_dict, write_json


def main():
    output_path, request = load_request_and_output(getScriptArgs())
    min_length = int(request.get("min_length", 4))
    limit = int(request.get("limit", 50))
    offset = int(request.get("offset", 0))
    query = normalize_text(request.get("query", "")).strip().lower()
    save_to_file = bool(request.get("save_to_file", False))
    artifact_output_path = normalize_text(request.get("artifact_output_path", "")).strip()

    results = []
    total = 0
    preview_end = offset + limit

    artifact_handle = None
    if save_to_file and artifact_output_path:
        artifact_handle = codecs.open(artifact_output_path, "w", "utf-8")

    try:
        for data in iter_string_data(currentProgram):
            item = string_data_to_dict(data)
            value = item.get("value") or ""
            normalized_value = normalize_text(value)
            lowered_value = normalized_value.lower()
            if len(normalized_value) < min_length:
                continue
            if query and query not in lowered_value:
                continue

            if artifact_handle is not None:
                artifact_handle.write(
                    json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
                )

            if total >= offset and total < preview_end:
                results.append(item)
            total += 1
    finally:
        if artifact_handle is not None:
            artifact_handle.close()

    write_json(
        output_path,
        {
            "program_id": request.get("program_id"),
            "total_matches": total,
            "returned": len(results),
            "min_length": min_length,
            "limit": limit,
            "offset": offset,
            "query": request.get("query", ""),
            "truncated": offset + len(results) < total,
            "save_to_file": save_to_file,
            "artifact_path": artifact_output_path if artifact_handle is not None else None,
            "artifact_format": "jsonl" if artifact_handle is not None else None,
            "artifact_record_count": total if artifact_handle is not None else None,
            "strings": results,
        },
    )


main()
