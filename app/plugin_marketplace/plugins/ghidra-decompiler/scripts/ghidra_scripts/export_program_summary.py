# -*- coding: utf-8 -*-
# @runtime Jython

from common import address_to_string, load_request_and_output, normalize_text, write_json


def main():
    output_path, request = load_request_and_output(getScriptArgs())

    result = {
        "success": True,
        "program_id": request.get("program_id"),
        "program_name": normalize_text(currentProgram.getName()),
        "executable_format": normalize_text(currentProgram.getExecutableFormat()),
        "language_id": normalize_text(currentProgram.getLanguageID()),
        "image_base": address_to_string(currentProgram.getImageBase()),
        "binary_path": request.get("binary_path"),
        "sha256": request.get("sha256"),
    }

    try:
        result["compiler_spec_id"] = normalize_text(
            currentProgram.getCompilerSpec().getCompilerSpecID()
        )
    except Exception:
        result["compiler_spec_id"] = None

    try:
        result["function_count"] = int(currentProgram.getFunctionManager().getFunctionCount())
    except Exception:
        result["function_count"] = None

    write_json(output_path, result)


main()
