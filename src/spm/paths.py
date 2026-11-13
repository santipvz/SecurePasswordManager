"""Locate the user's data directory on desktop systems."""

import ctypes
import os
import sys
from pathlib import Path
from uuid import UUID

LOCAL_APP_DATA_ID = UUID("f1b32785-6fba-4fcf-9d55-7b8e7f157091")
KF_FLAG_DONT_VERIFY = 0x4000


def _windows_known_local_app_data() -> str | None:
    # The GUID layout has four-byte alignment. Windows expects its little-endian representation.
    guid = (ctypes.c_uint32 * 4).from_buffer_copy(LOCAL_APP_DATA_ID.bytes_le)
    location = ctypes.c_wchar_p()
    get_path = ctypes.windll.shell32.SHGetKnownFolderPath
    get_path.argtypes = (
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p),
    )
    get_path.restype = ctypes.c_long
    free_path = ctypes.windll.ole32.CoTaskMemFree
    free_path.argtypes = (ctypes.c_void_p,)
    free_path.restype = None

    try:
        result = get_path(ctypes.byref(guid), KF_FLAG_DONT_VERIFY, None, ctypes.byref(location))
        return location.value if result == 0 else None
    finally:
        free_path(location)


def _windows_data_directory() -> Path:
    # Preserve the override that was accepted by existing installations.
    override = Path(os.environ.get("WIN_PD_OVERRIDE_LOCAL_APPDATA", "").strip())
    if override.is_absolute():
        return override
    location = _windows_known_local_app_data() or os.environ.get("LOCALAPPDATA", "")
    directory = Path(location)
    if directory.is_absolute():
        return directory
    return Path.home() / "AppData" / "Local"


def user_data_directory() -> Path:
    """Return the base directory for the current user's application data."""
    if sys.platform == "win32":
        return _windows_data_directory()
    override = Path(os.environ.get("XDG_DATA_HOME", ""))
    if override.is_absolute():
        return override
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path.home() / ".local" / "share"
