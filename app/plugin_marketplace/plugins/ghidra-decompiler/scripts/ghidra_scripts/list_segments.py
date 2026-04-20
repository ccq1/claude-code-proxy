# -*- coding: utf-8 -*-
# @runtime Jython

from common import address_to_string, load_request_and_output, normalize_text, write_json


def _block_to_dict(block):
    permissions = "".join(
        [
            "r" if block.isRead() else "-",
            "w" if block.isWrite() else "-",
            "x" if block.isExecute() else "-",
        ]
    )

    source_name = None
    try:
        source_name = normalize_text(block.getSourceName())
    except Exception:
        source_name = None

    block_type = None
    try:
        block_type = normalize_text(block.getType().toString())
    except Exception:
        block_type = normalize_text(block.getType())

    return {
        "name": normalize_text(block.getName()),
        "start": address_to_string(block.getStart()),
        "end": address_to_string(block.getEnd()),
        "size": int(block.getSize()),
        "permissions": permissions,
        "read": bool(block.isRead()),
        "write": bool(block.isWrite()),
        "execute": bool(block.isExecute()),
        "initialized": bool(block.isInitialized()),
        "loaded": bool(block.isLoaded()),
        "volatile": bool(block.isVolatile()),
        "artificial": bool(block.isArtificial()),
        "type": block_type,
        "source_name": source_name,
    }


def main():
    output_path, request = load_request_and_output(getScriptArgs())
    limit = int(request.get("limit", 200))

    blocks = []
    memory = currentProgram.getMemory()
    for block in memory.getBlocks():
        blocks.append(_block_to_dict(block))

    blocks.sort(key=lambda item: (item.get("start") or "", item.get("name") or ""))
    sliced = blocks[:limit]

    write_json(
        output_path,
        {
            "success": True,
            "program_id": request.get("program_id"),
            "total_segments": len(blocks),
            "returned": len(sliced),
            "limit": limit,
            "truncated": len(blocks) > len(sliced),
            "segments": sliced,
        },
    )


main()
