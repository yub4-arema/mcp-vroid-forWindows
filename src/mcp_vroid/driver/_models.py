"""Window geometry shared by the platform backends."""
from dataclasses import dataclass


@dataclass
class Window:
    address: str
    cls: str
    title: str
    x: int
    y: int
    w: int
    h: int
    workspace: int
    focused: bool
    fullscreen: bool = False

    @property
    def geometry(self) -> tuple[int, int, int, int]:
        """Desktop (x, y, w, h): physical pixels on Windows, logical on Linux."""
        return self.x, self.y, self.w, self.h

    def to_layout(self, x: float, y: float) -> tuple[float, float]:
        return self.x + x, self.y + y
