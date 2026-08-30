"""Integrated Scientific Encyclopedia browser.

Renders the per-family markdown pages shipped in
``sss_aug_studio/documentation/encyclopedia/``.  Equations are shown in
fenced code blocks (a documented simplification of the pre-rendered-SVG
plan, docs/architecture.md §7 Known approximations); the content contract per
page — physical explanation, mathematical model, implementation, verified
references, expected visual effect, limitations, validation hooks — is
unchanged.
"""

from __future__ import annotations

from importlib import resources

from PySide6.QtWidgets import QDialog, QHBoxLayout, QListWidget, QTextBrowser

__all__ = ["EncyclopediaDialog"]


def _pages() -> dict[str, str]:
    out: dict[str, str] = {}
    pkg = resources.files("sss_aug_studio.documentation") / "encyclopedia"
    try:
        for entry in sorted(pkg.iterdir(), key=lambda e: e.name):  # type: ignore[attr-defined]
            if entry.name.endswith(".md"):
                out[entry.name] = entry.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        pass
    return out


class EncyclopediaDialog(QDialog):
    def __init__(self, parent=None, page: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Scientific Encyclopedia — Physics-Informed SSS Augmentation")
        self.resize(980, 720)
        lay = QHBoxLayout(self)
        self._pages = _pages()
        self.listw = QListWidget()
        for name in self._pages:
            self.listw.addItem(name)
        self.listw.setMaximumWidth(260)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        lay.addWidget(self.listw)
        lay.addWidget(self.browser, 1)
        self.listw.currentTextChanged.connect(self._show)
        if page and page in self._pages:
            self.listw.setCurrentRow(list(self._pages).index(page))
        elif self._pages:
            self.listw.setCurrentRow(0)

    def _show(self, name: str) -> None:
        self.browser.setMarkdown(self._pages.get(name, "*page not found*"))
