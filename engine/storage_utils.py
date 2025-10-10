"""
Helpers for working with Django storage-backed files (e.g., S3/R2).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from tempfile import NamedTemporaryFile
from typing import BinaryIO, Iterator


def open_field_file(field_file, mode: str = "rb") -> BinaryIO:
    """
    Ensure a FieldFile is opened and rewound, returning the underlying file object.
    """
    field_file.open(mode)
    file_obj = getattr(field_file, "file", field_file)
    try:
        file_obj.seek(0)
    except (AttributeError, OSError):
        pass
    return file_obj


@contextmanager
def ensure_local_file(field_file) -> Iterator[str]:
    """
    Yield a local filesystem path for a FieldFile, downloading to a temp file if needed.
    """
    try:
        path = field_file.path
        if path and os.path.exists(path):
            yield path
            return
    except (AttributeError, NotImplementedError, ValueError, OSError):
        pass

    suffix = ""
    name = getattr(field_file, "name", None)
    if name:
        suffix = os.path.splitext(name)[1]

    file_obj = open_field_file(field_file)

    tmp_file = NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        while True:
            chunk = file_obj.read(1024 * 1024)
            if not chunk:
                break
            tmp_file.write(chunk)
        tmp_file.flush()
        tmp_file.close()

        try:
            file_obj.seek(0)
        except Exception:
            pass

        yield tmp_file.name
    finally:
        try:
            os.unlink(tmp_file.name)
        except FileNotFoundError:
            pass
