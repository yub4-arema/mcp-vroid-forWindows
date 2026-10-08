"""Select native Windows or Hyprland window management."""
import sys

if sys.platform == "win32":
    from ._windows_window import (  # noqa: F401
        Window, WORKSPACE, active_workspace, assert_vroid_focused,
        dismiss_screensaver, enter, find_window, focus, fullscreen,
        is_vroid_focused, launch, launch_and_wait, leave, park, prepare,
        save_dialog_window, terminate, wait_for_window,
    )
elif sys.platform.startswith("linux"):
    from ._linux_window import (  # noqa: F401
        Window, WORKSPACE, active_workspace, assert_vroid_focused,
        dismiss_screensaver, enter, find_window, focus, fullscreen,
        hyprctl, hyprctl_json, is_vroid_focused, launch, launch_and_wait,
        leave, park, prepare, wait_for_window,
    )

    def terminate():
        import subprocess
        subprocess.run(["pkill", "-f", "VRoidStudio.exe"], capture_output=True)
else:
    raise RuntimeError("mcp-vroid supports Windows and Linux/Hyprland only")
