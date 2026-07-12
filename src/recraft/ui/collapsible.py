"""Compact collapsible control section."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolButton, QVBoxLayout, QWidget


class CollapsibleSection(QWidget):
    """A titled section that gives preview space back when collapsed."""

    def __init__(self, title: str, content: QWidget, expanded: bool = False) -> None:
        super().__init__(); self.toggle = QToolButton(text=title, checkable=True, checked=expanded); self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.toggled.connect(self._set_expanded); self.content = content
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.addWidget(self.toggle); layout.addWidget(content)
        self._set_expanded(expanded)

    def _set_expanded(self, expanded: bool) -> None:
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow); self.content.setVisible(expanded)
