# -*- coding: utf-8 -*-

import json

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


def function_to_dict(function):
    body_size = None
    try:
        body_size = int(function.getBody().getNumAddresses())
    except Exception:
        body_size = None

    result = {
        "name": normalize_text(function.getName()),
        "entry_point": address_to_string(function.getEntryPoint()),
        "signature": function_signature(function),
        "namespace": namespace_name(function.getParentNamespace()),
        "body_size": body_size,
    }
    try:
        result["full_name"] = normalize_text(function.getName(True))
    except Exception:
        result["full_name"] = result["name"]
    return result


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


def find_function(program, request):
    address_text = normalize_text(request.get("address", "")).strip()
    function_name = normalize_text(request.get("function_name", "")).strip()
    function_manager = program.getFunctionManager()

    if address_text:
        address = _address_from_string(program, address_text)
        if address is not None:
            function = function_manager.getFunctionAt(address)
            if function is None:
                function = function_manager.getFunctionContaining(address)
            if function is not None:
                return function

    if function_name:
        exact_match = None
        partial_match = None
        function_name_lower = function_name.lower()
        for function in iter_functions(program):
            current_name = normalize_text(function.getName())
            if current_name == function_name:
                exact_match = function
                break
            if partial_match is None and current_name and function_name_lower in current_name.lower():
                partial_match = function
        if exact_match is not None:
            return exact_match
        if partial_match is not None:
            return partial_match

    return None


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

    return {
        "name": normalize_text(symbol.getName()),
        "address": address_to_string(symbol.getAddress()),
        "kind": kind,
        "namespace": namespace_name(symbol.getParentNamespace()),
    }
