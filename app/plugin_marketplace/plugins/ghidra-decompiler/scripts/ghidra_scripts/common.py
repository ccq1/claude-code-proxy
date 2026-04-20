# -*- coding: utf-8 -*-

import json
import jarray

from ghidra.program.util import DefinedDataIterator

try:
    text_type = unicode
except NameError:
    text_type = str


def normalize_text(value):
    if value is None:
        return None
    if isinstance(value, text_type):
        return value
    try:
        return text_type(value)
    except Exception:
        return str(value)


def load_request_and_output(script_args):
    if len(script_args) < 2:
        raise ValueError("expected output_path and request_path")
    output_path = script_args[0]
    request_path = script_args[1]
    with open(request_path, "r") as handle:
        request = json.load(handle)
    return output_path, request


def write_json(output_path, payload):
    with open(output_path, "w") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def address_to_string(address):
    if address is None:
        return None
    try:
        return normalize_text(address.toString())
    except Exception:
        return normalize_text(address)


def namespace_name(namespace):
    if namespace is None:
        return None
    try:
        return normalize_text(namespace.getName())
    except Exception:
        return normalize_text(namespace)


def function_signature(function):
    for getter in (
        lambda: function.getSignature().getPrototypeString(True, True),
        lambda: function.getPrototypeString(False, False),
        lambda: function.getSignature().getPrototypeString(False, False),
        lambda: function.getName(),
    ):
        try:
            return normalize_text(getter())
        except Exception:
            continue
    return None


def function_is_external(function):
    for getter in (
        lambda: function.isExternal(),
        lambda: function.getSymbol().isExternal(),
    ):
        try:
            if getter():
                return True
        except Exception:
            continue

    try:
        full_name = normalize_text(function.getName(True)) or ""
    except Exception:
        full_name = ""
    namespace = namespace_name(function.getParentNamespace()) or ""
    return full_name.startswith("<EXTERNAL>::") or namespace in ("EXTERNAL", "<EXTERNAL>")


def function_is_thunk(function):
    try:
        return bool(function.isThunk())
    except Exception:
        return False


def function_is_entry_point(program, function):
    try:
        symbol_table = program.getSymbolTable()
        entry_point = function.getEntryPoint()
        if symbol_table.isExternalEntryPoint(entry_point):
            return True
    except Exception:
        pass

    try:
        symbols = program.getSymbolTable().getSymbols(function.getEntryPoint())
        for symbol in symbols:
            try:
                if symbol.isExternalEntryPoint():
                    return True
            except Exception:
                continue
    except Exception:
        pass

    return False


def function_to_dict(function, program=None):
    body_size = None
    try:
        body_size = int(function.getBody().getNumAddresses())
    except Exception:
        body_size = None

    is_external = function_is_external(function)
    is_thunk = function_is_thunk(function)
    is_entry_point = function_is_entry_point(program, function) if program is not None else False

    result = {
        "name": normalize_text(function.getName()),
        "entry_point": address_to_string(function.getEntryPoint()),
        "signature": function_signature(function),
        "namespace": namespace_name(function.getParentNamespace()),
        "body_size": body_size,
        "is_external": is_external,
        "is_thunk": is_thunk,
        "is_entry_point": is_entry_point,
    }
    try:
        result["full_name"] = normalize_text(function.getName(True))
    except Exception:
        result["full_name"] = result["name"]
    return result


def function_sort_key(item):
    return (
        1 if item.get("is_external") else 0,
        1 if item.get("is_thunk") else 0,
        normalize_text(item.get("name") or ""),
        normalize_text(item.get("entry_point") or ""),
    )


def iter_functions(program):
    iterator = program.getFunctionManager().getFunctions(True)
    while iterator.hasNext():
        yield iterator.next()


def _address_from_string(program, address_text):
    if not address_text:
        return None
    text = normalize_text(address_text).strip()
    factory = program.getAddressFactory()
    try:
        return factory.getAddress(text)
    except Exception:
        try:
            return factory.getDefaultAddressSpace().getAddress(text)
        except Exception:
            if text.lower().startswith("0x"):
                try:
                    return factory.getDefaultAddressSpace().getAddress(text[2:])
                except Exception:
                    return None
    return None


def address_from_string(program, address_text):
    return _address_from_string(program, address_text)


def read_memory_bytes(program, address, length):
    if address is None or length <= 0:
        return []

    memory = program.getMemory()
    buffer = jarray.zeros(int(length), "b")
    count = memory.getBytes(address, buffer)
    if count is None:
        count = len(buffer)
    if count < 0:
        count = 0
    return [int(buffer[index]) & 0xFF for index in range(min(int(count), len(buffer)))]


def bytes_to_hex(byte_values):
    return "".join("%02x" % (value & 0xFF) for value in byte_values)


def bytes_to_ascii(byte_values):
    chars = []
    for value in byte_values:
        if 32 <= value <= 126:
            chars.append(chr(value))
        else:
            chars.append(".")
    return "".join(chars)


def chunk_byte_values(byte_values, chunk_size):
    items = []
    total = len(byte_values)
    start = 0
    while start < total:
        items.append(byte_values[start : start + chunk_size])
        start += chunk_size
    return items


def find_function(program, request):
    resolution = resolve_function(program, request)
    return resolution.get("function")


def resolve_function(program, request):
    address_text = normalize_text(request.get("address", "")).strip()
    function_name = normalize_text(request.get("function_name", "")).strip()
    function_manager = program.getFunctionManager()

    if address_text:
        address = _address_from_string(program, address_text)
        if address is None:
            return {
                "function": None,
                "resolved_by": "address",
                "error_code": "invalid_address",
                "error_message": "invalid address: {0}".format(address_text),
            }
        function = function_manager.getFunctionAt(address)
        if function is not None:
            return {
                "function": function,
                "resolved_by": "address_exact",
            }
        function = function_manager.getFunctionContaining(address)
        if function is not None:
            return {
                "function": function,
                "resolved_by": "address_containing",
            }
        return {
            "function": None,
            "resolved_by": "address",
            "error_code": "target_function_not_found",
            "error_message": "no function found at address {0}".format(address_text),
        }

    if function_name:
        exact_internal = []
        exact_external = []
        partial_internal = []
        partial_external = []
        function_name_lower = function_name.lower()
        for function in iter_functions(program):
            current_name = normalize_text(function.getName())
            full_name = None
            try:
                full_name = normalize_text(function.getName(True))
            except Exception:
                full_name = current_name

            is_external = function_is_external(function)
            if current_name == function_name or full_name == function_name:
                if is_external:
                    exact_external.append(function)
                else:
                    exact_internal.append(function)
                continue

            matches_partial = False
            for candidate_name in (current_name, full_name):
                if candidate_name and function_name_lower in candidate_name.lower():
                    matches_partial = True
                    break

            if not matches_partial:
                continue

            if is_external:
                partial_external.append(function)
            else:
                partial_internal.append(function)

        if exact_internal:
            return {
                "function": exact_internal[0],
                "resolved_by": "function_name_exact",
            }
        if exact_external:
            return {
                "function": exact_external[0],
                "resolved_by": "function_name_exact_external",
            }
        if len(partial_internal) == 1:
            return {
                "function": partial_internal[0],
                "resolved_by": "function_name_partial_internal",
            }
        if len(partial_internal) > 1:
            candidates = [function_to_dict(function, program) for function in partial_internal[:5]]
            candidates.sort(key=function_sort_key)
            return {
                "function": None,
                "resolved_by": "function_name",
                "error_code": "ambiguous_function_name",
                "error_message": "multiple internal functions matched function_name={0}".format(function_name),
                "candidates": candidates,
                "candidate_count": len(partial_internal),
            }
        if partial_external:
            candidates = [function_to_dict(function, program) for function in partial_external[:5]]
            candidates.sort(key=function_sort_key)
            return {
                "function": None,
                "resolved_by": "function_name",
                "error_code": "external_function_only_match",
                "error_message": "only external functions matched function_name={0}".format(function_name),
                "candidates": candidates,
                "candidate_count": len(partial_external),
            }

        return {
            "function": None,
            "resolved_by": "function_name",
            "error_code": "target_function_not_found",
            "error_message": "no function matched function_name={0}".format(function_name),
        }

    return {
        "function": None,
        "resolved_by": "none",
        "error_code": "target_function_not_found",
        "error_message": "no function selector provided",
    }


def iter_string_data(program):
    try:
        iterator = DefinedDataIterator.definedStrings(program)
        while iterator.hasNext():
            yield iterator.next()
        return
    except Exception:
        pass

    iterator = program.getListing().getDefinedData(True)
    while iterator.hasNext():
        data = iterator.next()
        try:
            if data.hasStringValue():
                yield data
        except Exception:
            continue


def string_data_to_dict(data):
    value = None
    try:
        value = data.getValue()
    except Exception:
        value = None

    if value is None:
        try:
            value = data.getDefaultValueRepresentation()
        except Exception:
            value = None

    text_value = normalize_text(value)
    try:
        length = int(data.getLength())
    except Exception:
        length = None

    return {
        "address": address_to_string(data.getMinAddress()),
        "length": length,
        "value": text_value,
    }


def iter_symbols(program):
    symbol_table = program.getSymbolTable()
    iterators = []

    for producer in (
        lambda: symbol_table.getAllSymbols(True),
        lambda: symbol_table.getAllSymbols(False),
        lambda: symbol_table.getDefinedSymbols(),
    ):
        try:
            iterator = producer()
            if iterator is not None:
                iterators.append(iterator)
        except Exception:
            continue

    seen = set()
    for iterator in iterators:
        while iterator.hasNext():
            symbol = iterator.next()
            key = (
                normalize_text(symbol.getName()),
                address_to_string(symbol.getAddress()),
            )
            if key in seen:
                continue
            seen.add(key)
            yield symbol


def symbol_to_dict(symbol):
    kind = None
    try:
        kind = normalize_text(symbol.getSymbolType().toString())
    except Exception:
        kind = normalize_text(symbol.getSymbolType())

    is_external = False
    try:
        if symbol.isExternal():
            is_external = True
    except Exception:
        pass
    if not is_external:
        namespace = namespace_name(symbol.getParentNamespace()) or ""
        is_external = namespace in ("EXTERNAL", "<EXTERNAL>")

    is_entry_point = False
    try:
        is_entry_point = bool(symbol.isExternalEntryPoint())
    except Exception:
        is_entry_point = False

    return {
        "name": normalize_text(symbol.getName()),
        "address": address_to_string(symbol.getAddress()),
        "kind": kind,
        "namespace": namespace_name(symbol.getParentNamespace()),
        "is_external": is_external,
        "is_entry_point": is_entry_point,
    }
