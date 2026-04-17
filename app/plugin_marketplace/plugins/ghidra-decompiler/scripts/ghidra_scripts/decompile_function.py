# -*- coding: utf-8 -*-
# @runtime Jython

from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

from common import find_function, function_to_dict, load_request_and_output, write_json


def main():
    output_path, request = load_request_and_output(getScriptArgs())
    function = find_function(currentProgram, request)
    if function is None:
        raise RuntimeError("target function not found")

    timeout_seconds = int(request.get("timeout_seconds", 30))
    interface = DecompInterface()
    interface.openProgram(currentProgram)

    try:
        try:
            active_monitor = monitor
        except Exception:
            active_monitor = ConsoleTaskMonitor()

        result = interface.decompileFunction(function, timeout_seconds, active_monitor)
        if not result.decompileCompleted():
            raise RuntimeError("decompile did not complete: " + result.getErrorMessage())

        decompiled_function = result.getDecompiledFunction()
        decompiled_c = ""
        if decompiled_function is not None:
            decompiled_c = decompiled_function.getC()

        write_json(
            output_path,
            {
                "program_id": request.get("program_id"),
                "function": function_to_dict(function),
                "decompiled_c": decompiled_c,
                "error_message": result.getErrorMessage(),
            },
        )
    finally:
        try:
            interface.closeProgram()
        except Exception:
            pass
        try:
            interface.dispose()
        except Exception:
            pass


main()
