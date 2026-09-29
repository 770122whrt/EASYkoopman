"""Minimal AppLauncher import shim.

Keep this module small: workflow scripts import it before the Isaac app starts.
"""

try:
    from isaaclab.app import AppLauncher
except ImportError:
    from omni.isaac.lab.app import AppLauncher


__all__ = ["AppLauncher"]
