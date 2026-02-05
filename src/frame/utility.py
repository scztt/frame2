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


import inspect
from functools import lru_cache

@lru_cache(maxsize=None)
def _get_signature(func):
    """Cache inspect.signature results for speed."""
    return inspect.signature(func)

def call_with_known_args(func, *args, **kwargs):
    """
    Call `func` with *args and **kwargs, filtering out any kwargs that
    aren't accepted by the function (unless it has **kwargs).
    """
    sig = _get_signature(func)
    params = sig.parameters

    # Check if the function accepts arbitrary keyword arguments (**kwargs)
    accepts_var_kw = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
    )

    # If it does, we can just pass everything
    if accepts_var_kw:
        return func(*args, **kwargs)

    # Otherwise, filter kwargs to those explicitly in the signature
    filtered_kwargs = {k: v for k, v in kwargs.items() if k in params}

    try:
        return func(*args, **filtered_kwargs)
    except TypeError as e:
        # Optional: debug fallback for ambiguous signatures
        raise TypeError(
            f"Error calling {func.__name__} with filtered args={args}, kwargs={filtered_kwargs}"
        ) from e
