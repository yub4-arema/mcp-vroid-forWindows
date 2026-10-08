"""Platform-specific pointer, wheel and keyboard injection."""
import sys

if sys.platform == "win32":
    from ._windows_input import (  # noqa: F401
        clear_field, click, double_click, drag, hotkey, hscroll, key, move,
        scroll, set_safety, type_text, x_focus_ok,
    )
else:
    from ._linux_input import (  # noqa: F401
        clear_field, click, double_click, drag, hotkey, hscroll, key, move,
        scroll, set_safety, type_text, x_focus_ok,
    )
