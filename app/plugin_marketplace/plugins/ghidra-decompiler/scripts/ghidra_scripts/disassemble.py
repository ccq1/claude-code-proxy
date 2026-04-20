# -*- coding: utf-8 -*-
# @runtime Jython

from common import (
    address_from_string,
    address_to_string,
    bytes_to_hex,
    function_to_dict,
    load_request_and_output,
    normalize_text,
    resolve_function,
    write_json,
)


def _instruction_to_dict(instruction):
    byte_values = []
    try:
        byte_values = [int(value) & 0xFF for value in instruction.getBytes()]
    except Exception:
        byte_values = []

    flow_type = None
    try:
        flow_type = normalize_text(instruction.getFlowType().toString())
    except Exception:
        flow_type = normalize_text(instruction.getFlowType())

    target_addresses = []
    try:
        flows = instruction.getFlows()
        if flows is not None:
            for address in flows:
                target_addresses.append(address_to_string(address))
    except Exception:
        pass

    fallthrough = None
    try:
        fallthrough = address_to_string(instruction.getFallThrough())
    except Exception:
        fallthrough = None

    return {
        "address": address_to_string(instruction.getAddress()),
        "mnemonic": normalize_text(instruction.getMnemonicString()),
        "text": normalize_text(instruction.toString()),
        "bytes": bytes_to_hex(byte_values),
        "length": int(instruction.getLength()),
        "flow_type": flow_type,
        "fallthrough": fallthrough,
        "target_addresses": target_addresses,
    }


def main():
    output_path, request = load_request_and_output(getScriptArgs())
    max_instructions = int(request.get("max_instructions", 80))

    listing = currentProgram.getListing()
    resolution = resolve_function(currentProgram, request)
    function = resolution.get("function")
    start_instruction = None
    resolved_function = None
    scope = "address"

    if function is not None:
        resolved_function = function_to_dict(function, currentProgram)
        start_instruction = listing.getInstructionAt(function.getEntryPoint())
        scope = "function"
    else:
        address_text = request.get("address", "")
        address = address_from_string(currentProgram, address_text)
        if address is None:
            write_json(
                output_path,
                {
                    "success": False,
                    "program_id": request.get("program_id"),
                    "error_code": "invalid_address",
                    "error_message": "invalid address: {0}".format(address_text),
                },
            )
            return
        start_instruction = listing.getInstructionAt(address)
        if start_instruction is None:
            start_instruction = listing.getInstructionContaining(address)
        if start_instruction is None:
            write_json(
                output_path,
                {
                    "success": False,
                    "program_id": request.get("program_id"),
                    "error_code": "instruction_not_found",
                    "error_message": "no instruction found at address {0}".format(address_text),
                },
            )
            return

    instructions = []
    current_instruction = start_instruction
    body = None
    if function is not None:
        try:
            body = function.getBody()
        except Exception:
            body = None

    while current_instruction is not None and len(instructions) < max_instructions:
        if body is not None and not body.contains(current_instruction.getAddress()):
            break
        instructions.append(_instruction_to_dict(current_instruction))
        current_instruction = current_instruction.getNext()

    write_json(
        output_path,
        {
            "success": True,
            "program_id": request.get("program_id"),
            "scope": scope,
            "resolved_by": resolution.get("resolved_by"),
            "resolved_function": resolved_function,
            "returned": len(instructions),
            "instruction_count": len(instructions),
            "max_instructions": max_instructions,
            "truncated": current_instruction is not None and len(instructions) >= max_instructions,
            "instructions": instructions,
        },
    )


main()
