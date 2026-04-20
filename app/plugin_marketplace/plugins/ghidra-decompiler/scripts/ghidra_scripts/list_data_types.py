# -*- coding: utf-8 -*-
# @runtime Jython

from common import load_request_and_output, normalize_text, write_json


def _data_type_kind(data_type):
    class_name = normalize_text(data_type.getClass().getSimpleName()) or ""
    lowered = class_name.lower()
    if "structure" in lowered:
        return "structure"
    if "union" in lowered:
        return "union"
    if "enum" in lowered:
        return "enum"
    if "typedef" in lowered or "type_def" in lowered:
        return "typedef"
    if "functiondefinition" in lowered:
        return "function_definition"
    if "pointer" in lowered:
        return "pointer"
    return "other"


def _safe_length(data_type):
    try:
        return int(data_type.getLength())
    except Exception:
        return None


def _safe_category_path(data_type):
    try:
        return normalize_text(data_type.getCategoryPath().getPath())
    except Exception:
        return None


def _component_to_dict(component):
    return {
        "field_name": normalize_text(component.getFieldName()),
        "offset": int(component.getOffset()),
        "length": int(component.getLength()),
        "data_type": normalize_text(component.getDataType().getDisplayName()),
        "comment": normalize_text(component.getComment()),
    }


def _enum_value_to_dict(data_type, value):
    return {
        "name": normalize_text(data_type.getName(value)),
        "value": int(value),
    }


def _data_type_to_dict(data_type, include_members=False):
    kind = _data_type_kind(data_type)
    item = {
        "name": normalize_text(data_type.getName()),
        "display_name": normalize_text(data_type.getDisplayName()),
        "path": _safe_category_path(data_type),
        "kind": kind,
        "length": _safe_length(data_type),
        "description": normalize_text(data_type.getDescription()),
    }

    if include_members:
        if kind in ("structure", "union"):
            try:
                item["members"] = [_component_to_dict(component) for component in data_type.getComponents()[:20]]
            except Exception:
                item["members"] = []
        elif kind == "enum":
            try:
                values = list(data_type.getValues())
                values.sort()
                item["values"] = [_enum_value_to_dict(data_type, value) for value in values[:50]]
            except Exception:
                item["values"] = []

    return item


def main():
    output_path, request = load_request_and_output(getScriptArgs())
    query = normalize_text(request.get("query", "")).strip().lower()
    kind_filter = normalize_text(request.get("kind", "")).strip().lower()
    limit = int(request.get("limit", 100))
    include_members = bool(request.get("include_members", False))

    dtm = currentProgram.getDataTypeManager()
    iterator = dtm.getAllDataTypes()
    matches = []

    while iterator.hasNext():
        data_type = iterator.next()
        item = _data_type_to_dict(data_type, include_members=include_members)
        if kind_filter and item.get("kind") != kind_filter:
            continue
        haystack = " ".join(filter(None, [item.get("name"), item.get("display_name"), item.get("path"), item.get("description")])).lower()
        if query and query not in haystack:
            continue
        matches.append(item)

    matches.sort(key=lambda item: (item.get("kind") or "", item.get("path") or "", item.get("name") or ""))
    sliced = matches[:limit]

    write_json(
        output_path,
        {
            "success": True,
            "program_id": request.get("program_id"),
            "query": request.get("query"),
            "kind": request.get("kind"),
            "include_members": include_members,
            "total_matches": len(matches),
            "returned": len(sliced),
            "limit": limit,
            "truncated": len(matches) > len(sliced),
            "data_types": sliced,
        },
    )


main()
