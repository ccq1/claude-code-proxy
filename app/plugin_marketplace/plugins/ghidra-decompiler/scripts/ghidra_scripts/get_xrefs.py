# -*- coding: utf-8 -*-
# @runtime Jython

from common import (
    address_from_string,
    address_to_string,
    function_to_dict,
    load_request_and_output,
    normalize_text,
    resolve_function,
    write_json,
)


def _reference_flags(reference_type):
    return {
        "is_call": bool(reference_type.isCall()) if hasattr(reference_type, "isCall") else False,
        "is_jump": bool(reference_type.isJump()) if hasattr(reference_type, "isJump") else False,
        "is_data": bool(reference_type.isData()) if hasattr(reference_type, "isData") else False,
        "is_read": bool(reference_type.isRead()) if hasattr(reference_type, "isRead") else False,
        "is_write": bool(reference_type.isWrite()) if hasattr(reference_type, "isWrite") else False,
    }


def _reference_to_dict(program, reference):
    reference_type = reference.getReferenceType()
    payload = {
        "from_address": address_to_string(reference.getFromAddress()),
        "to_address": address_to_string(reference.getToAddress()),
        "reference_type": normalize_text(reference_type.toString()),
        "operand_index": int(reference.getOperandIndex()),
    }
    payload.update(_reference_flags(reference_type))

    listing = program.getListing()
    from_function = listing.getFunctionContaining(reference.getFromAddress())
    if from_function is not None:
        payload["from_function"] = function_to_dict(from_function, program)

    to_function = listing.getFunctionContaining(reference.getToAddress())
    if to_function is not None:
        payload["to_function"] = function_to_dict(to_function, program)

    return payload


def _collect_references_to(program, address, limit):
    items = []
    seen = set()
    iterator = program.getReferenceManager().getReferencesTo(address)
    while iterator.hasNext() and len(items) < limit:
        reference = iterator.next()
        key = (
            address_to_string(reference.getFromAddress()),
            address_to_string(reference.getToAddress()),
            normalize_text(reference.getReferenceType().toString()),
            int(reference.getOperandIndex()),
        )
        if key in seen:
            continue
        seen.add(key)
        items.append(_reference_to_dict(program, reference))
    return items


def _collect_references_from_function(program, function, limit):
    items = []
    seen = set()
    listing = program.getListing()
    instruction = listing.getInstructionAt(function.getEntryPoint())
    body = function.getBody()

    while instruction is not None and body.contains(instruction.getAddress()) and len(items) < limit:
        for reference in program.getReferenceManager().getReferencesFrom(instruction.getAddress()):
            key = (
                address_to_string(reference.getFromAddress()),
                address_to_string(reference.getToAddress()),
                normalize_text(reference.getReferenceType().toString()),
                int(reference.getOperandIndex()),
            )
            if key in seen:
                continue
            seen.add(key)
            items.append(_reference_to_dict(program, reference))
            if len(items) >= limit:
                break
        instruction = instruction.getNext()

    return items


def _collect_references_from_address(program, address, limit):
    items = []
    seen = set()
    for reference in program.getReferenceManager().getReferencesFrom(address):
        key = (
            address_to_string(reference.getFromAddress()),
            address_to_string(reference.getToAddress()),
            normalize_text(reference.getReferenceType().toString()),
            int(reference.getOperandIndex()),
        )
        if key in seen:
            continue
        seen.add(key)
        items.append(_reference_to_dict(program, reference))
        if len(items) >= limit:
            break
    return items


def main():
    output_path, request = load_request_and_output(getScriptArgs())
    direction = normalize_text(request.get("direction", "to")).strip().lower()
    limit = int(request.get("limit", 100))
    if direction not in ("to", "from", "both"):
        direction = "to"

    resolution = resolve_function(currentProgram, request)
    function = resolution.get("function")
    target_address = None
    target_function = None

    if function is not None:
        target_function = function_to_dict(function, currentProgram)
        target_address = function.getEntryPoint()
    else:
        address_text = request.get("address", "")
        target_address = address_from_string(currentProgram, address_text)
        if target_address is None:
            payload = {
                "success": False,
                "program_id": request.get("program_id"),
                "error_code": resolution.get("error_code") or "invalid_address",
                "error_message": resolution.get("error_message") or "invalid address",
                "resolved_by": resolution.get("resolved_by"),
            }
            if resolution.get("candidates") is not None:
                payload["candidates"] = resolution.get("candidates")
            if resolution.get("candidate_count") is not None:
                payload["candidate_count"] = resolution.get("candidate_count")
            write_json(output_path, payload)
            return

    refs_to = []
    refs_from = []
    if direction in ("to", "both"):
        refs_to = _collect_references_to(currentProgram, target_address, limit)
    if direction in ("from", "both"):
        if function is not None:
            refs_from = _collect_references_from_function(currentProgram, function, limit)
        else:
            refs_from = _collect_references_from_address(currentProgram, target_address, limit)

    write_json(
        output_path,
        {
            "success": True,
            "program_id": request.get("program_id"),
            "direction": direction,
            "resolved_by": resolution.get("resolved_by"),
            "target_address": address_to_string(target_address),
            "target_function": target_function,
            "xrefs_to": refs_to,
            "xrefs_from": refs_from,
            "xrefs_to_count": len(refs_to),
            "xrefs_from_count": len(refs_from),
        },
    )


main()
