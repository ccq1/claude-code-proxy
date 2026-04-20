# -*- coding: utf-8 -*-
# @runtime Jython

from ghidra.util.task import ConsoleTaskMonitor

from common import function_sort_key, function_to_dict, load_request_and_output, resolve_function, write_json


def main():
    output_path, request = load_request_and_output(getScriptArgs())
    limit = int(request.get("limit", 100))
    resolution = resolve_function(currentProgram, request)
    function = resolution.get("function")

    if function is None:
        payload = {
            "success": False,
            "program_id": request.get("program_id"),
            "error_code": resolution.get("error_code") or "target_function_not_found",
            "error_message": resolution.get("error_message") or "target function not found",
            "resolved_by": resolution.get("resolved_by"),
        }
        if resolution.get("candidates") is not None:
            payload["candidates"] = resolution.get("candidates")
        if resolution.get("candidate_count") is not None:
            payload["candidate_count"] = resolution.get("candidate_count")
        write_json(output_path, payload)
        return

    try:
        active_monitor = monitor
    except Exception:
        active_monitor = ConsoleTaskMonitor()

    callers = [function_to_dict(item, currentProgram) for item in function.getCallingFunctions(active_monitor)]
    callees = [function_to_dict(item, currentProgram) for item in function.getCalledFunctions(active_monitor)]
    callers.sort(key=function_sort_key)
    callees.sort(key=function_sort_key)

    write_json(
        output_path,
        {
            "success": True,
            "program_id": request.get("program_id"),
            "resolved_by": resolution.get("resolved_by"),
            "function": function_to_dict(function, currentProgram),
            "incoming_count": len(callers),
            "outgoing_count": len(callees),
            "incoming": callers[:limit],
            "outgoing": callees[:limit],
            "limit": limit,
            "incoming_truncated": len(callers) > limit,
            "outgoing_truncated": len(callees) > limit,
        },
    )


main()
