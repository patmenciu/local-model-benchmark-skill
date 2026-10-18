"""Shared lexical and symlink-denying filesystem boundary; no directory scans."""
from pathlib import Path
import os


def _lexical(value):
    raw = os.fspath(value)
    if not raw or '\\' in raw or '\x00' in raw:
        raise ValueError('invalid path syntax')
    parts = Path(raw).parts
    if any(part in ('safe', '..') for part in parts):
        raise ValueError('forbidden path component')
    return Path(raw)


def _no_symlinks(path):
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ValueError('symlink paths are not allowed')


def workspace_root(value):
    candidate = _lexical(value)
    absolute = Path(os.path.abspath(candidate))
    _lexical(absolute)
    _no_symlinks(absolute)
    if not absolute.is_dir():
        raise ValueError('workspace does not exist')
    return absolute


def file_path(root, relative, *, must_exist=True):
    root = workspace_root(root)
    child = _lexical(relative)
    if child.is_absolute() or child == Path('.'):
        raise ValueError('use a relative file path')
    target = root / child
    if not target.is_relative_to(root):
        raise ValueError('path escapes workspace')
    _no_symlinks(target)
    if must_exist and not target.is_file():
        raise ValueError('input file does not exist')
    if not must_exist and not target.parent.is_dir():
        raise ValueError('output parent does not exist')
    return target


def write_new(root, relative, text):
    target = file_path(root, relative, must_exist=False)
    with target.open('x', encoding='utf-8') as handle:
        handle.write(text)
