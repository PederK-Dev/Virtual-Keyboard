"""Filesystem locations shared by source and packaged application builds."""

import os
import sys


APP_DIRECTORY_NAME = "VirtualKeyboard"


def user_data_directory(source_file, environ=None, frozen=None):
    """Return the persistent data directory for this execution mode."""
    environ = os.environ if environ is None else environ
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen

    if not frozen:
        return os.path.dirname(os.path.abspath(source_file))

    base = (
        environ.get("APPDATA")
        or environ.get("LOCALAPPDATA")
        or os.path.expanduser("~")
    )
    directory = os.path.join(base, APP_DIRECTORY_NAME)
    os.makedirs(directory, exist_ok=True)
    return directory


def bundled_resource(source_file, relative_path, bundle_root=None):
    """Resolve a file in source checkout or PyInstaller's extraction directory."""
    if bundle_root is None:
        bundle_root = getattr(
            sys,
            "_MEIPASS",
            os.path.dirname(os.path.abspath(source_file)),
        )
    return os.path.join(bundle_root, relative_path)
