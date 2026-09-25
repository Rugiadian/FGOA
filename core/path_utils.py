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
