"""Augmentation Library dock (Area 2) — the heart of the application.

One science card per family: name, phenomenon, key equation, reference
count, family enable/disable (toggles all its instances), an "add instance"
button (multi-instance support), and a "details" link to the encyclopedia
page.  The card list is generated from the registry, so new families appear
automatically.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core import registry
from ..core.pipeline import AugmentationInstance, AugmentationPipeline

__all__ = ["LibraryPanel"]


class _ScienceCard(QFrame):
    def __init__(self, fam_cls, on_add: Callable[[str], None], on_details: Callable[[str], None], on_toggle: Callable[[str, bool], None]):
        super().__init__()
        self.setObjectName("scienceCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        card = fam_cls.card
        lay = QVBoxLayout(self)
        head = QHBoxLayout()
        title = QLabel(f"<b>{card.name}</b>")
        title.setWordWrap(True)
        head.addWidget(title, 1)
        self.enable = QCheckBox("on")
        self.enable.setChecked(True)
        self.enable.setToolTip("Enable/disable every instance of this family.")
        self.enable.toggled.connect(lambda v: on_toggle(fam_cls.key, bool(v)))
        head.addWidget(self.enable)
        lay.addLayout(head)

        phen = QLabel(card.phenomenon)
        phen.setWordWrap(True)
        phen.setStyleSheet("color:#a5b0ba;")
        lay.addWidget(phen)
        eq = QLabel(f"<code>{card.equation}</code>")
        eq.setWordWrap(True)
        eq.setStyleSheet("color:#8fbf8f;")
        lay.addWidget(eq)
        refs = QLabel(f"{len(card.references)} reference(s) — {card.references[0].split(',')[0]} et seq.")
        refs.setWordWrap(True)
        refs.setStyleSheet("color:#7f8b96; font-size: 10px;")
        lay.addWidget(refs)

        btns = QHBoxLayout()
        b_add = QPushButton("＋ instance")
        b_add.setToolTip("Add a new named parameter set of this family to the pipeline.")
        b_add.clicked.connect(lambda: on_add(fam_cls.key))
        b_doc = QPushButton("Details / encyclopedia")
        b_doc.clicked.connect(lambda: on_details(card.doc_page))
        btns.addWidget(b_add)
        btns.addWidget(b_doc)
        lay.addLayout(btns)


class LibraryPanel(QScrollArea):
    instance_added = Signal(str)     # instance_id
    open_doc = Signal(str)           # encyclopedia page
    pipeline_changed = Signal()

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self._pipeline: Optional[AugmentationPipeline] = None
        body = QWidget()
        self.setWidget(body)
        lay = QVBoxLayout(body)
        lay.addWidget(QLabel("<b>Augmentation library</b>"))
        self._counters: dict[str, int] = {}
        fams = registry.all_families()
        sections = (
            ("geometry", "Geometry — exact acquisition symmetries"),
            ("physics", "Physics-informed families"),
        )
        for section_key, section_title in sections:
            members = {k: c for k, c in fams.items() if getattr(c, "section", "physics") == section_key}
            if not members:
                continue
            head = QLabel(f"<b>{section_title}</b>")
            head.setStyleSheet("color:#5b9bd5; margin-top:6px;")
            lay.addWidget(head)
            for key, fam_cls in members.items():
                lay.addWidget(_ScienceCard(fam_cls, self._add_instance, self.open_doc.emit, self._toggle_family))
        lay.addStretch()

    def set_pipeline(self, pipeline: AugmentationPipeline) -> None:
        self._pipeline = pipeline

    def _add_instance(self, family: str) -> None:
        if self._pipeline is None:
            return
        n = self._counters.get(family, 0) + 1
        self._counters[family] = n
        label = f"profile {chr(64 + min(n, 26))}"
        inst = AugmentationInstance(family=family, label=label)
        self._pipeline.add(inst)
        self.pipeline_changed.emit()
        self.instance_added.emit(inst.instance_id)

    def _toggle_family(self, family: str, enabled: bool) -> None:
        if self._pipeline is None:
            return
        for inst in self._pipeline.instances:
            if inst.family == family:
                inst.enabled = enabled
        self.pipeline_changed.emit()
