"""Reproducibility manifest — stamped automatically onto every fit and figure.

The goal: any figure in a paper can be regenerated 18 months later from its manifest. It records
the source data + a content hash, the model and all fit settings, the full fitted parameters, the
library version, and a timestamp. Built automatically from a :class:`FitResult`, not something a
student must remember to attach.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from .. import __version__
from ..fitting.result import FitResult


@dataclass(frozen=True)
class ReproducibilityManifest:
    """Everything needed to regenerate a result."""

    data_source: str | None
    data_hash: str | None
    model: str
    parameters: dict[str, float]
    parameter_uncertainties: dict[str, float]
    fit_settings: dict[str, object]
    goodness_of_fit: dict[str, float]
    library_version: str
    timestamp: str
    extra: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_fit(
        cls,
        fit: FitResult,
        *,
        timestamp: str,
        data_source: str | None = None,
        extra: dict[str, str] | None = None,
    ) -> ReproducibilityManifest:
        return cls(
            data_source=data_source,
            data_hash=fit.data_hash,
            model=type(fit.model).__name__,
            parameters=fit.params,
            parameter_uncertainties=fit.param_uncertainties,
            fit_settings=fit.fit_settings,
            goodness_of_fit={
                "chi2_reduced": fit.chi2_reduced,
                "r_squared": fit.r_squared,
                "aicc": fit.aicc,
                "bic": fit.bic,
                "n_data": float(fit.n_data),
                "n_params": float(fit.n_params),
            },
            library_version=__version__,
            timestamp=timestamp,
            extra=extra or {},
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)
