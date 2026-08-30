"""Physics-Informed Side-Scan Sonar Augmentation Studio.

A scientific framework for physically plausible SSS dataset augmentation,
built for the master thesis *Adaptive AI-Driven SSS Survey on a Small USV*.
"""

from .core.image import SonarImage
from .core.labels import LabelSet, YoloBox
from .core.meta import AcquisitionMeta
from .core.pipeline import AugmentationInstance, AugmentationPipeline, PipelineResult
from .core import registry

__version__ = "0.4.0"

__all__ = [
    "SonarImage", "AcquisitionMeta", "LabelSet", "YoloBox",
    "AugmentationPipeline", "AugmentationInstance", "PipelineResult",
    "registry", "__version__",
]
