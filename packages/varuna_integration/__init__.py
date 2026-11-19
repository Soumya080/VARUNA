"""
VARUNA GRID v2 — Track 4 integration boundaries.

This package contains ONLY wiring: the dependency-injected boundaries that let
the existing scientific producers (NETRA, PRATIVARTAN, NYAYA, ValidityGate,
PRAVAAH, ABHIYAN, Mission, Alerts) be composed into one live case pipeline.

It deliberately contains no science. Every number that reaches an operator is
computed by the owning subsystem and passed through here unmodified. If you
find yourself computing a confidence, a centroid, a probability or a ranking in
this package, it belongs in the producing subsystem instead.

Two vocabularies are kept strictly separate (see ADR-0006 and
docs/api/OPERATOR_CASE_CONTRACT_V1.md):

  EvidenceMode   REAL | SIMULATED | UNAVAILABLE — *provenance quality* of a
                 value that exists. Monotonic-worsening only; nothing in this
                 package may upgrade it.
  StageStatus    PRODUCED | NOT_YET_PRODUCED | BLOCKED — *did this stage run*.
                 Orthogonal to provenance: a stage can be PRODUCED/SIMULATED,
                 or BLOCKED with no value at all.
"""
from varuna_integration.stage import StageResult, StageStatus

__all__ = ["StageResult", "StageStatus"]
