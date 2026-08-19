"""Parameter sampling distributions for dataset generation.

Each scalar physical parameter of an augmentation instance may be wrapped in
a distribution; per-image samples are drawn from the deterministic RNG tree,
so identical master seeds reproduce identical parameter draws.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

__all__ = ["DistSpec", "sample_value", "Fixed", "Uniform", "Normal", "LogUniform", "Choice"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Fixed(_Base):
    dist: Literal["fixed"] = "fixed"
    value: float | int | bool | str

    def sample(self, rng: np.random.Generator):
        return self.value


class Uniform(_Base):
    dist: Literal["uniform"] = "uniform"
    low: float
    high: float

    def sample(self, rng: np.random.Generator) -> float:
        return float(rng.uniform(self.low, self.high))


class Normal(_Base):
    dist: Literal["normal"] = "normal"
    mean: float
    std: float = Field(gt=0)
    clip_low: float | None = None
    clip_high: float | None = None

    def sample(self, rng: np.random.Generator) -> float:
        v = float(rng.normal(self.mean, self.std))
        if self.clip_low is not None:
            v = max(v, self.clip_low)
        if self.clip_high is not None:
            v = min(v, self.clip_high)
        return v


class LogUniform(_Base):
    dist: Literal["loguniform"] = "loguniform"
    low: float = Field(gt=0)
    high: float = Field(gt=0)

    def sample(self, rng: np.random.Generator) -> float:
        return float(np.exp(rng.uniform(np.log(self.low), np.log(self.high))))


class Choice(_Base):
    dist: Literal["choice"] = "choice"
    options: list[float | int | bool | str]

    def sample(self, rng: np.random.Generator):
        return self.options[int(rng.integers(0, len(self.options)))]


DistSpec = Annotated[Union[Fixed, Uniform, Normal, LogUniform, Choice], Field(discriminator="dist")]


def sample_value(spec, rng: np.random.Generator):
    """Sample from a DistSpec instance or pass plain literals through."""
    if isinstance(spec, (Fixed, Uniform, Normal, LogUniform, Choice)):
        return spec.sample(rng)
    if isinstance(spec, dict) and "dist" in spec:
        from pydantic import TypeAdapter

        return TypeAdapter(DistSpec).validate_python(spec).sample(rng)
    return spec
