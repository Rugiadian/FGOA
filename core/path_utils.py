"""
Path Utilities for FGOA.
Handles repository-relative paths for reference images to ensure cross-machine portability
when projects and reference images are committed and pulled from GitHub.
"""
import os
from typing import Optional


def get_project_root() -> str:
    """Returns the absolute path to the root of the FGOA repository."""
    # Assuming this file is at core/path_utils.py -> parent of core is repo root
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(current_dir, ".."))


def get_references_dir() -> str:
    """Returns the primary repository references directory (references/)."""
    refs_dir = os.path.join(get_project_root(), "references")
    os.makedirs(refs_dir, exist_ok=True)
    return refs_dir


def to_relative_path(path: Optional[str], base_dir: Optional[str] = None) -> Optional[str]:
    """
    Converts an absolute or relative image path to a repository-relative path (e.g. 'references/img.png').
    Uses forward slashes for cross-platform JSON compatibility.
    """
    if not path:
        return None

    path_str = str(path).strip()
    if not path_str:
        return None

    base = os.path.abspath(base_dir or get_project_root())

    # If already relative, normalize slashes
    if not os.path.isabs(path_str):
        return path_str.replace("\\", "/")

    abs_path = os.path.abspath(path_str)

    # If path is inside project root or base_dir
    try:
        rel = os.path.relpath(abs_path, base)
        if not rel.startswith(".."):
            return rel.replace("\\", "/")
    except ValueError:
        pass

    # If it's in user's legacy ~/.fgoa_refs, check if it's mirrored in references/
    fname = os.path.basename(abs_path)
    repo_ref = os.path.join(get_references_dir(), fname)
    if os.path.exists(repo_ref):
        return f"references/{fname}"

    # Default fallback: if it has 'references', make it relative to references
    if "references" in abs_path:
        parts = abs_path.replace("\\", "/").split("/references/")
        if len(parts) > 1:
            return f"references/{parts[-1]}"

    return abs_path.replace("\\", "/")


def to_absolute_path(path: Optional[str], base_dir: Optional[str] = None) -> Optional[str]:
    """
    Converts a relative or foreign machine absolute path to a valid local absolute path.
    Recovers broken image links by matching filename against project references/ folder.
    """
    if not path:
        return None

    path_str = str(path).strip()
    if not path_str:
        return None

    base = os.path.abspath(base_dir or get_project_root())
    refs_dir = get_references_dir()

    # 1. If it's already an absolute path and exists locally, return it
    if os.path.isabs(path_str) and os.path.exists(path_str):
        return os.path.abspath(path_str)

    # 2. If it's a relative path, check against base_dir / project root
    if not os.path.isabs(path_str):
        candidate = os.path.abspath(os.path.join(base, path_str))
        if os.path.exists(candidate):
            return candidate

    # 3. Portability recovery: extract filename and look inside repo references/
    fname = os.path.basename(path_str)
    candidate_ref = os.path.join(refs_dir, fname)
    if os.path.exists(candidate_ref):
        return candidate_ref

    # 4. Check legacy ~/.fgoa_refs if candidate exists there
    legacy_candidate = os.path.expanduser(os.path.join("~/.fgoa_refs", fname))
    if os.path.exists(legacy_candidate):
        return os.path.abspath(legacy_candidate)

    # 5. Fallback: return resolved path relative to base
    return os.path.abspath(os.path.join(base, path_str)) if not os.path.isabs(path_str) else path_str


def get_trace_dir(base_dir: Optional[str] = None) -> str:
    """Returns the primary repository trace logs directory (trace_logs/)."""
    root = os.path.abspath(base_dir or get_project_root())
    trace_dir = os.path.join(root, "trace_logs")
    os.makedirs(trace_dir, exist_ok=True)
    return trace_dir


def to_trace_relative_path(path: Optional[str], base_dir: Optional[str] = None) -> Optional[str]:
    """
    Converts a trace screenshot path to repository-relative path (e.g. 'trace_logs/loop_001_.../shot_0001.jpg').
    Ensures forward-slash normalization for cross-platform and cross-PC compatibility.
    """
    if not path:
        return None
    path_str = str(path).strip()
    if not path_str:
        return None

    if not os.path.isabs(path_str):
        return path_str.replace("\\", "/")

    abs_path = os.path.abspath(path_str)
    root = os.path.abspath(base_dir or get_project_root())

    try:
        rel = os.path.relpath(abs_path, root)
        if not rel.startswith(".."):
            return rel.replace("\\", "/")
    except ValueError:
        pass

    norm_slash = abs_path.replace("\\", "/")
    if "/trace_logs/" in norm_slash:
        parts = norm_slash.split("/trace_logs/")
        if len(parts) > 1:
            return f"trace_logs/{parts[-1]}"

    return norm_slash


def to_trace_absolute_path(path: Optional[str], base_dir: Optional[str] = None) -> Optional[str]:
    """
    Converts a trace screenshot path (relative, URL-encoded, or from a foreign computer)
    to the local machine's valid absolute path with multi-stage fallback and filename recovery.
    """
    if not path:
        return None
    import urllib.parse
    raw_str = str(path).strip()
    if not raw_str:
        return None

    # Handle URL decoding (e.g. %20, %5C, Korean chars)
    path_str = urllib.parse.unquote(raw_str)

    # Clean leading slashes before Windows drive letter (e.g. '/C:/...' or '///C:/...')
    path_str = path_str.replace("\\", "/")
    while path_str.startswith("/") and len(path_str) > 2 and path_str[2] == ":":
        path_str = path_str[1:]

    root = os.path.abspath(base_dir or get_project_root())
    trace_dir = get_trace_dir(root)

    # 1. If it's already an absolute path and exists locally on this PC:
    if os.path.isabs(path_str) and os.path.exists(path_str):
        return os.path.abspath(path_str)

    # 2. If it's a relative path and exists locally:
    if not os.path.isabs(path_str):
        candidate = os.path.abspath(os.path.join(root, path_str))
        if os.path.exists(candidate):
            return candidate

    # 3. Cross-PC re-anchoring: if path contains 'trace_logs', map to current PC's project trace_logs:
    if "trace_logs" in path_str:
        parts = path_str.split("trace_logs/")
        if len(parts) > 1:
            rel_tail = parts[-1]
            candidate = os.path.abspath(os.path.join(trace_dir, rel_tail))
            if os.path.exists(candidate):
                return candidate

    # 4. Deep Recovery by filename: search inside local trace_logs for matching filename
    filename = os.path.basename(path_str)
    if filename and os.path.exists(trace_dir):
        for sub_root, _, files in os.walk(trace_dir):
            if filename in files:
                return os.path.abspath(os.path.join(sub_root, filename))

    # 5. Fallback candidate
    if "trace_logs" in path_str:
        parts = path_str.split("trace_logs/")
        if len(parts) > 1:
            return os.path.abspath(os.path.join(trace_dir, parts[-1]))

    return os.path.abspath(os.path.join(root, path_str)) if not os.path.isabs(path_str) else path_str

