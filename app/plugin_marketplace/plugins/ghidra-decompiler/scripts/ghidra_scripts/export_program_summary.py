# -*- coding: utf-8 -*-
# @runtime Jython

from common import (
    address_to_string,
    function_sort_key,
    function_to_dict,
    iter_functions,
    load_request_and_output,
    normalize_text,
    write_json,
)

INTERNAL_START_NAMES = ("main", "_start", "start", "entry", "_entry", "__start")
EXTERNAL_START_NAMES = ("__libc_start_main", "__uClibc_main", "__libc_main_start")


def _matches_name(item, names):
    name = (normalize_text(item.get("name")) or "").lower()
    full_name = (normalize_text(item.get("full_name")) or "").lower()
    for candidate in names:
        lowered = candidate.lower()
        if name == lowered or full_name == lowered or full_name.endswith("::" + lowered):
            return True
    return False


def _function_for_address(program, address):
    if address is None:
        return None
    function_manager = program.getFunctionManager()
    function = function_manager.getFunctionAt(address)
    if function is None:
        function = function_manager.getFunctionContaining(address)
    return function


def _entry_point_candidates(program):
    candidates = []
    seen = set()

    try:
        iterator = program.getSymbolTable().getExternalEntryPointIterator()
        while iterator.hasNext():
            address = iterator.next()
            function = _function_for_address(program, address)
            if function is not None:
                item = function_to_dict(function, program)
            else:
                item = {
                    "name": None,
                    "entry_point": address_to_string(address),
                    "address": address_to_string(address),
                    "is_external": False,
                    "is_thunk": False,
                    "is_entry_point": True,
                }
            key = (item.get("entry_point") or item.get("address"), item.get("name"))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(item)
    except Exception:
        pass

    candidates.sort(
        key=lambda item: (
            1 if item.get("is_external") else 0,
            1 if item.get("is_thunk") else 0,
            normalize_text(item.get("entry_point") or item.get("address") or ""),
        )
    )
    return candidates


def main():
    output_path, request = load_request_and_output(getScriptArgs())

    internal_function_count = 0
    external_function_count = 0
    thunk_function_count = 0
    main_candidates = []
    start_candidates = []
    external_startup_candidates = []

    for function in iter_functions(currentProgram):
        item = function_to_dict(function, currentProgram)
        if item.get("is_external"):
            external_function_count += 1
        else:
            internal_function_count += 1
        if item.get("is_thunk"):
            thunk_function_count += 1

        if _matches_name(item, INTERNAL_START_NAMES):
            if item.get("is_external"):
                external_startup_candidates.append(item)
            else:
                if _matches_name(item, ("main",)):
                    main_candidates.append(item)
                start_candidates.append(item)
        elif item.get("is_external") and _matches_name(item, EXTERNAL_START_NAMES):
            external_startup_candidates.append(item)

    main_candidates.sort(key=function_sort_key)
    start_candidates.sort(key=function_sort_key)
    external_startup_candidates.sort(key=function_sort_key)
    entry_point_candidates = _entry_point_candidates(currentProgram)

    analysis_hints = []
    if not main_candidates:
        analysis_hints.append(
            "未发现命名为 main 的内部函数；若样本已 strip，优先从 entry/_start 或 entry_point_candidates 开始。"
        )
    if start_candidates:
        analysis_hints.append(
            "建议先查看启动函数 {0}，再沿启动链继续收缩范围。".format(
                ", ".join(
                    filter(None, [item.get("name") for item in start_candidates[:3]])
                )
            )
        )
    if external_startup_candidates:
        analysis_hints.append(
            "若启动链命中 __libc_start_main / __uClibc_main 一类外部符号，优先跟踪其首个函数参数定位真实主逻辑。"
        )

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

    result["internal_function_count"] = internal_function_count
    result["external_function_count"] = external_function_count
    result["thunk_function_count"] = thunk_function_count
    result["entry_point_candidates"] = entry_point_candidates[:5]
    result["entry_point"] = None
    if entry_point_candidates:
        result["entry_point"] = (
            entry_point_candidates[0].get("entry_point")
            or entry_point_candidates[0].get("address")
        )
    result["main_candidates"] = main_candidates[:5]
    result["suggested_start_functions"] = start_candidates[:5]
    result["external_startup_candidates"] = external_startup_candidates[:5]
    result["analysis_hints"] = analysis_hints

    write_json(output_path, result)


main()
