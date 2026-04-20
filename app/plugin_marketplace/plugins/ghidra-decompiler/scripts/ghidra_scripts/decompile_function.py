# -*- coding: utf-8 -*-
# @runtime Jython

from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

from common import (
    function_to_dict,
    load_request_and_output,
    normalize_text,
    resolve_function,
    write_json,
)


def _safe_bool(getter):
    try:
        return bool(getter())
    except Exception:
        return False


def _classify_error(error_message, timed_out=False, cancelled=False):
    text = (normalize_text(error_message) or "").lower()
    if timed_out or "timed out" in text or "timeout" in text:
        return "decompile_timeout"
    if cancelled or "abort" in text or "aborted" in text or "cancel" in text:
        return "decompile_aborted"
    return "decompile_failed"


def _base_payload(request):
    return {
        "success": False,
        "program_id": request.get("program_id"),
        "requested_function_name": request.get("function_name"),
        "requested_address": request.get("address"),
        "timeout_seconds": int(request.get("timeout_seconds", 30)),
    }


def main():
    output_path, request = load_request_and_output(getScriptArgs())
    payload = _base_payload(request)
    interface = None

    try:
        resolution = resolve_function(currentProgram, request)
        payload["resolved_by"] = resolution.get("resolved_by")

        if resolution.get("candidates") is not None:
            payload["candidates"] = resolution.get("candidates")
        if resolution.get("candidate_count") is not None:
            payload["candidate_count"] = resolution.get("candidate_count")

        function = resolution.get("function")
        if function is None:
            payload["error_code"] = resolution.get("error_code") or "target_function_not_found"
            payload["error_message"] = resolution.get("error_message") or "target function not found"
            write_json(output_path, payload)
            return

        resolved_function = function_to_dict(function, currentProgram)
        payload["resolved_function"] = resolved_function

        timeout_seconds = int(request.get("timeout_seconds", 30))
        interface = DecompInterface()
        interface.openProgram(currentProgram)

        try:
            active_monitor = monitor
        except Exception:
            active_monitor = ConsoleTaskMonitor()

        try:
            result = interface.decompileFunction(function, timeout_seconds, active_monitor)
        except Exception as exc:
            error_message = normalize_text(exc)
            payload["error_code"] = _classify_error(error_message, cancelled=True)
            payload["error_message"] = error_message or exc.__class__.__name__
            payload["exception_type"] = exc.__class__.__name__
            write_json(output_path, payload)
            return

        decompile_status = {
            "completed": _safe_bool(result.decompileCompleted),
            "failed_to_start": _safe_bool(result.failedToStart),
            "timed_out": _safe_bool(result.isTimedOut),
            "cancelled": _safe_bool(result.isCancelled),
            "error_message": normalize_text(result.getErrorMessage()),
        }
        payload["decompile_status"] = decompile_status

        if not decompile_status["completed"]:
            payload["error_code"] = _classify_error(
                decompile_status.get("error_message"),
                timed_out=decompile_status.get("timed_out"),
                cancelled=decompile_status.get("cancelled"),
            )
            payload["error_message"] = (
                decompile_status.get("error_message") or "decompile did not complete"
            )
            write_json(output_path, payload)
            return

        decompiled_function = result.getDecompiledFunction()
        decompiled_c = ""
        if decompiled_function is not None:
            decompiled_c = normalize_text(decompiled_function.getC()) or ""

        if not decompiled_c.strip():
            payload["error_code"] = "empty_decompile_result"
            payload["error_message"] = (
                decompile_status.get("error_message") or "decompiler returned empty C output"
            )
            write_json(output_path, payload)
            return

        payload["success"] = True
        payload["function"] = resolved_function
        payload["decompiled_c"] = decompiled_c
        payload["error_message"] = decompile_status.get("error_message")
        write_json(output_path, payload)
    except Exception as exc:
        payload["error_code"] = "decompile_script_error"
        payload["error_message"] = normalize_text(exc) or exc.__class__.__name__
        payload["exception_type"] = exc.__class__.__name__
        write_json(output_path, payload)
    finally:
        if interface is not None:
            try:
                interface.closeProgram()
            except Exception:
                pass
            try:
                interface.dispose()
            except Exception:
                pass


main()
