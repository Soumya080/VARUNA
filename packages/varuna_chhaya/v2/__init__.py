"""CHHAYA v2 — real vessel-evidence pipeline (2026-09-02).

Additive, non-breaking sibling to the existing v1 `varuna_chhaya` package
(`protocol.py::ChhayaProvider`, `service.py::ChhayaService`, `mock.py`). v1 is
untouched. This subpackage implements the architecture mandated by the
"VARUNA / NETRA — WORKSTREAM B: CHHAYA INTELLIGENCE" build task:

    SAR -> vessel candidates -> georeference -> AIS association
    -> PRATIVARTAN origin/corridor consistency -> temporal consistency
    -> deterministic ranking -> CHHAYA evidence -> NYAYA handoff

CHHAYA produces vessel EVIDENCE. It is not the attribution authority — see
`packages/varuna_nyaya/chhaya_bridge.py` for the (additive, non-invasive)
handoff point into NYAYA. No file under `packages/varuna_nyaya/` other than
that new bridge module is modified by this package.

No model is trained or fine-tuned anywhere in this subpackage. See
`reports/chhaya_v2/CHHAYA_V2_BENCHMARK_REPORT.md` for the pretrained-model
benchmark that justifies the detector selected here (classical CA-CFAR,
`detectors/cfar.py`) and for why the researched pretrained neural candidate
(`detectors/xview3_frcnn.py`) is implemented as an honestly NOT_CONFIGURED
detector rather than a fabricated one.
"""
