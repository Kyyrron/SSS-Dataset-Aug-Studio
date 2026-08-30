"""Parameter form auto-generated from an augmentation's Pydantic schema.

The extensibility contract of the studio: a new augmentation family declares
its physical parameters (units, bounds, description) once in its ``Params``
model; this widget renders sliders/spinboxes/combos for them with **zero
per-family GUI code**.  General instance parameters (enabled, probability,
strength) are rendered above the physical ones.

Since v0.3.0 every float parameter row carries a **law selector**: *fixed*
(the value doubles as the nominal preview value) or a stochastic law
(uniform / normal / log-uniform) whose a/b values appear on a second line.
Laws are stored on the instance (``AugmentationInstance.distributions``) and
are consumed by dataset generation; previews always render nominal values.
"""

from __future__ import annotations

import typing
from typing import Any, Callable, Optional, get_args, get_origin

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.pipeline import AugmentationInstance
from ..core import registry

__all__ = ["ParamsForm"]

SLIDER_STEPS = 400


def _bounds(field) -> tuple[Optional[float], Optional[float]]:
    lo = hi = None
    for m in field.metadata:
        v = getattr(m, "ge", None)
        if v is None:
            v = getattr(m, "gt", None)
        if v is not None:
            lo = float(v)
        v = getattr(m, "le", None)
        if v is None:
            v = getattr(m, "lt", None)
        if v is not None:
            hi = float(v)
    return lo, hi


def _unit_of(desc: str) -> str:
    if desc and desc.rstrip().endswith("]") and "[" in desc:
        return desc.rstrip()[desc.rindex("[") + 1 : -1]
    return ""


class _FloatRow(QWidget):
    """Slider + spinbox pair bound to one float parameter."""

    def __init__(self, value: float, lo: float, hi: float, on_change: Callable[[float], None]):
        super().__init__()
        self._on_change = on_change
        self._lo, self._hi = lo, hi
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, SLIDER_STEPS)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(lo, hi)
        self.spin.setDecimals(3)
        self.spin.setSingleStep(max((hi - lo) / 100.0, 0.001))
        self.spin.setValue(value)
        self._sync_slider(value)
        lay.addWidget(self.slider, 3)
        lay.addWidget(self.spin, 1)
        self.slider.valueChanged.connect(self._slider_moved)
        self.spin.valueChanged.connect(self._spin_moved)

    def _sync_slider(self, v: float) -> None:
        frac = 0.0 if self._hi == self._lo else (v - self._lo) / (self._hi - self._lo)
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(frac * SLIDER_STEPS)))
        self.slider.blockSignals(False)

    def _slider_moved(self, step: int) -> None:
        v = self._lo + (self._hi - self._lo) * step / SLIDER_STEPS
        self.spin.blockSignals(True)
        self.spin.setValue(v)
        self.spin.blockSignals(False)
        self._on_change(v)

    def _spin_moved(self, v: float) -> None:
        self._sync_slider(v)
        self._on_change(v)


_LAWS = ["fixed", "uniform", "normal", "loguniform"]
_LAW_LABELS = {"uniform": ("low", "high"), "normal": ("mean", "std"), "loguniform": ("low", "high")}


class _ParamEditor(QWidget):
    """One float parameter: nominal value row + optional stochastic-law row."""

    def __init__(
        self,
        value: float,
        lo: float,
        hi: float,
        law: Optional[dict],
        on_value: Callable[[float], None],
        on_law: Callable[[Optional[dict]], None],
    ):
        super().__init__()
        self._on_law = on_law
        self._lo, self._hi = lo, hi
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(1)

        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        self.float_row = _FloatRow(value, lo, hi, on_value)
        row1.addWidget(self.float_row, 1)
        self.law = QComboBox()
        self.law.addItems(_LAWS)
        self.law.setFixedWidth(92)
        self.law.setToolTip(
            "fixed: this parameter keeps its value.\n"
            "uniform / normal / loguniform: during dataset generation each copy samples "
            "a fresh value from the law below; the value on the left is the nominal "
            "value used by the live preview."
        )
        row1.addWidget(self.law)
        col.addLayout(row1)

        self._law_row = QWidget()
        lrow = QHBoxLayout(self._law_row)
        lrow.setContentsMargins(18, 0, 0, 0)
        self._la = QLabel("low")
        self.a = QDoubleSpinBox()
        self._lb = QLabel("high")
        self.b = QDoubleSpinBox()
        for sp in (self.a, self.b):
            sp.setRange(-1e6, 1e6)
            sp.setDecimals(4)
        lrow.addWidget(self._la)
        lrow.addWidget(self.a, 1)
        lrow.addWidget(self._lb)
        lrow.addWidget(self.b, 1)
        col.addWidget(self._law_row)

        # initial state
        if law:
            self.law.setCurrentText(law.get("dist", "fixed"))
            if law.get("dist") == "normal":
                self.a.setValue(float(law.get("mean", value)))
                self.b.setValue(float(law.get("std", 0.0)))
            else:
                self.a.setValue(float(law.get("low", value)))
                self.b.setValue(float(law.get("high", value)))
        else:
            self.a.setValue(value)
            self.b.setValue(value)
        self._refresh_law_row()

        self.law.currentTextChanged.connect(lambda _: (self._refresh_law_row(), self._emit_law()))
        self.a.valueChanged.connect(lambda _: self._emit_law())
        self.b.valueChanged.connect(lambda _: self._emit_law())

    def _refresh_law_row(self) -> None:
        kind = self.law.currentText()
        self._law_row.setVisible(kind != "fixed")
        if kind in _LAW_LABELS:
            la, lb = _LAW_LABELS[kind]
            self._la.setText(la)
            self._lb.setText(lb)

    def _emit_law(self) -> None:
        kind = self.law.currentText()
        if kind == "fixed":
            self._on_law(None)
        elif kind == "normal":
            self._on_law({"dist": "normal", "mean": self.a.value(), "std": max(self.b.value(), 1e-6)})
        elif kind == "loguniform":
            lo, hi = sorted((max(self.a.value(), 1e-9), max(self.b.value(), 1e-9)))
            self._on_law({"dist": "loguniform", "low": lo, "high": hi})
        else:
            self._on_law({"dist": "uniform", "low": min(self.a.value(), self.b.value()),
                          "high": max(self.a.value(), self.b.value())})


class ParamsForm(QScrollArea):
    """Editor for one AugmentationInstance; emits via ``on_changed`` callback."""

    def __init__(self, on_changed: Callable[[], None]):
        super().__init__()
        self.setWidgetResizable(True)
        self._on_changed = on_changed
        self._instance: Optional[AugmentationInstance] = None
        self._body = QWidget()
        self.setWidget(self._body)
        self._layout = QVBoxLayout(self._body)
        self._layout.addWidget(QLabel("Select an augmentation instance to edit its parameters."))
        self._layout.addStretch()

    # --------------------------------------------------------------- build
    def set_instance(self, instance: Optional[AugmentationInstance]) -> None:
        self._instance = instance
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if instance is None:
            self._layout.addWidget(QLabel("Select an augmentation instance to edit its parameters."))
            self._layout.addStretch()
            return

        fam = registry.get(instance.family)
        params_model = instance.validated_params()

        title = QLabel(f"<b>{fam.name}</b> — instance “{instance.label}”")
        title.setWordWrap(True)
        self._layout.addWidget(title)
        eq = QLabel(f"<code>{fam.card.equation}</code>")
        eq.setWordWrap(True)
        eq.setStyleSheet("color: #8fbf8f;")
        self._layout.addWidget(eq)

        gen = QFrame()
        gform = QFormLayout(gen)
        name_edit = QLineEdit(instance.label)
        name_edit.editingFinished.connect(lambda: self._set_general("label", name_edit.text()))
        gform.addRow("Instance name", name_edit)
        enabled = QCheckBox("enabled")
        enabled.setChecked(instance.enabled)
        enabled.toggled.connect(lambda v: self._set_general("enabled", bool(v)))
        gform.addRow("State", enabled)
        prob = QDoubleSpinBox()
        prob.setRange(0.0, 1.0)
        prob.setSingleStep(0.05)
        prob.setValue(instance.probability)
        prob.setToolTip("Application probability during dataset generation (preview always applies enabled instances).")
        prob.valueChanged.connect(lambda v: self._set_general("probability", float(v)))
        gform.addRow("Probability", prob)
        strength = _FloatRow(instance.strength, 0.0, 2.0, lambda v: self._set_general("strength", v))
        gform.addRow("Strength", strength)
        self._layout.addWidget(gen)

        sep = QLabel("<b>Physical parameters</b>")
        self._layout.addWidget(sep)
        phys = QFrame()
        form = QFormLayout(phys)
        for fname, field in fam.Params.model_fields.items():
            self._add_field(form, fname, field, getattr(params_model, fname))
        self._layout.addWidget(phys)
        self._layout.addStretch()

    def _add_field(self, form: QFormLayout, fname: str, field, value: Any) -> None:
        desc = field.description or ""
        unit = _unit_of(desc)
        label = fname.replace("_", " ") + (f"  ({unit})" if unit and unit != "-" else "")
        ann = field.annotation
        origin = get_origin(ann)
        w: QWidget
        if ann is bool:
            cb = QCheckBox()
            cb.setChecked(bool(value))
            cb.toggled.connect(lambda v, n=fname: self._set_param(n, bool(v)))
            w = cb
        elif origin is typing.Literal or (origin is None and isinstance(value, str)):
            combo = QComboBox()
            options = [str(a) for a in get_args(ann)] if origin is typing.Literal else ["port", "starboard", "both"]
            combo.addItems(options)
            combo.setCurrentText(str(value))
            combo.currentTextChanged.connect(lambda v, n=fname: self._set_param(n, v))
            w = combo
        elif ann is int:
            lo, hi = _bounds(field)
            sp = QSpinBox()
            sp.setRange(int(lo if lo is not None else -1000), int(hi if hi is not None else 1000))
            sp.setValue(int(value))
            sp.valueChanged.connect(lambda v, n=fname: self._set_param(n, int(v)))
            w = sp
        else:  # float — nominal value + per-parameter stochastic law (v0.3.0)
            lo, hi = _bounds(field)
            lo = lo if lo is not None else -100.0
            hi = hi if hi is not None else 100.0
            law = (self._instance.distributions or {}).get(fname) if self._instance else None
            w = _ParamEditor(
                float(value), lo, hi, law,
                lambda v, n=fname: self._set_param(n, v),
                lambda d, n=fname: self._set_law(n, d),
            )
        w.setToolTip(desc)
        lab = QLabel(label)
        lab.setToolTip(desc)
        form.addRow(lab, w)

    # -------------------------------------------------------------- update
    def _set_param(self, name: str, value: Any) -> None:
        if self._instance is None:
            return
        p = dict(self._instance.params)
        p[name] = value
        self._instance.params = p
        self._on_changed()

    def _set_law(self, name: str, law: Optional[dict]) -> None:
        if self._instance is None:
            return
        dists = dict(self._instance.distributions)
        if law is None:
            dists.pop(name, None)
        else:
            dists[name] = law
        self._instance.distributions = dists
        # distributions are excluded from config_hash -> no preview recompute,
        # but the strip tooltip should reflect the stochastic state
        self._on_changed()

    def _set_general(self, name: str, value: Any) -> None:
        if self._instance is None:
            return
        setattr(self._instance, name, value)
        self._on_changed()
