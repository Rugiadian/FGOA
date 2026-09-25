"""
Configuration file manager for FGOA.
Generates machine-specific config filenames (e.g. fgoa_config_HOSTNAME.json)
to prevent git merge conflicts when working across multiple PCs.
"""
import os
import re
import socket
import shutil
from typing import Dict, Any


def get_machine_id() -> str:
    """Returns a sanitized machine identifier based on hostname/computername."""
    name = os.environ.get("COMPUTERNAME") or socket.gethostname() or "default"
    clean = re.sub(r'[^a-zA-Z0-9_\-]', '_', name).strip('_')
    return clean or "default"


def get_config_filepath() -> str:
    """
    Returns the machine-specific config file path (e.g., 'fgoa_config_DESKTOP-ABC.json').
    Automatically migrates existing settings from legacy 'fgoa_config.json' if needed.
    """
    machine_id = get_machine_id()
    machine_file = f"fgoa_config_{machine_id}.json"

    # Migration: copy existing legacy config to machine-specific config if not created yet
    if not os.path.exists(machine_file) and os.path.exists("fgoa_config.json"):
        try:
            shutil.copyfile("fgoa_config.json", machine_file)
        except Exception:
            pass

    return machine_file
