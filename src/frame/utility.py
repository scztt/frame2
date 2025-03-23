import os


def tail_lines(filepath: str, num_lines=100) -> str:
    """Reads the last `num_lines` of a file."""
    with open(filepath, "rb") as f:
        f.seek(0, os.SEEK_END)
        end = f.tell()
        buffer = bytearray()
        line_count = 0
        pointer = end

        while line_count <= num_lines and pointer > 0:
            pointer -= 1
            f.seek(pointer)
            byte = f.read(1)
            buffer.extend(byte)
            if byte == b"\n":
                line_count += 1

    # Reverse the buffer, convert to bytes, and decode to string
    return bytes(reversed(buffer)).decode("utf-8", errors="replace")
