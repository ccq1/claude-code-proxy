# -*- coding: utf-8 -*-
# @runtime Jython

from common import (
    address_from_string,
    address_to_string,
    bytes_to_ascii,
    bytes_to_hex,
    chunk_byte_values,
    load_request_and_output,
    read_memory_bytes,
    write_json,
)


def _hex_rows(base_address, byte_values, width):
    rows = []
    base_offset = int(base_address.getOffset())
    for index, chunk in enumerate(chunk_byte_values(byte_values, width)):
        row_offset = base_offset + (index * width)
        rows.append(
            {
                "address": "%08x" % row_offset,
                "hex": " ".join("%02x" % value for value in chunk),
                "ascii": bytes_to_ascii(chunk),
            }
        )
    return rows


def main():
    output_path, request = load_request_and_output(getScriptArgs())
    address_text = request.get("address", "")
    length = int(request.get("length", 128))
    row_width = int(request.get("row_width", 16))

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

    byte_values = read_memory_bytes(currentProgram, address, length)
    write_json(
        output_path,
        {
            "success": True,
            "program_id": request.get("program_id"),
            "address": address_to_string(address),
            "requested_length": length,
            "returned_length": len(byte_values),
            "hex": bytes_to_hex(byte_values),
            "ascii": bytes_to_ascii(byte_values),
            "rows": _hex_rows(address, byte_values, max(1, row_width)),
        },
    )


main()
