"""
VARUNA — incident PDF report (Workstream A, Phase 12).

Real generation via reportlab. Every section is rendered from the composed
OperatorCase; a section the backend did not produce is printed with its
honest status (NOT_AVAILABLE / NOT_CONFIGURED / SIMULATED / the section's
own `reason`) rather than omitted or filled in.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

_NAVY = colors.HexColor("#1a2440")
_SAFFRON = colors.HexColor("#e8871a")
_MUTED = colors.HexColor("#5b6472")


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("VTitle", parent=ss["Title"], fontSize=18, textColor=_NAVY,
                          spaceAfter=2))
    ss.add(ParagraphStyle("VSub", parent=ss["Normal"], fontSize=9, textColor=_MUTED,
                          spaceAfter=10))
    ss.add(ParagraphStyle("VH2", parent=ss["Heading2"], fontSize=11, textColor=_NAVY,
                          spaceBefore=10, spaceAfter=4))
    ss.add(ParagraphStyle("VBody", parent=ss["Normal"], fontSize=8.5, leading=11))
    ss.add(ParagraphStyle("VMuted", parent=ss["Normal"], fontSize=8, textColor=_MUTED,
                          leading=10))
    return ss


def _kv_table(rows: list[tuple[str, Any]], ss) -> Table:
    data = [[Paragraph(f"<b>{k}</b>", ss["VBody"]),
             Paragraph("—" if v is None else str(v), ss["VBody"])] for k, v in rows]
    t = Table(data, colWidths=[52 * mm, 116 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#dfe3e8")),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    return t


def _section_status(sec: Any) -> str:
    """Honest one-line status for a SectionEnvelope."""
    if sec is None:
        return "NOT_AVAILABLE — section absent from the operator case"
    status = getattr(getattr(sec, "status", None), "value", None)
    mode = getattr(getattr(sec, "evidence_mode", None), "value", None)
    reason = getattr(sec, "reason", None)
    if status == "produced":
        return f"PRODUCED (evidence_mode={mode or 'unknown'})"
    return f"{(status or 'unknown').upper()} — {reason or 'no reason supplied'}"


def build_incident_report(
    operator_case: Any, *, alerts: list[Any] | None = None,
    mission_audit: list[dict] | None = None,
    smriti_hits: list[dict] | None = None,
    channel_report: dict[str, str] | None = None,
    run_id: str | None = None,
) -> bytes:
    ss = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, title=f"VARUNA Incident Report — {operator_case.case_id}",
        author="VARUNA GRID", leftMargin=21 * mm, rightMargin=21 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
    )
    S: list[Any] = []

    def sec(name: str):
        return getattr(operator_case, name, None)

    def val(name: str):
        s = sec(name)
        return getattr(s, "value", None) if s is not None else None

    # ------------------------------------------------ header
    S.append(Paragraph("VARUNA GRID — Incident Report", ss["VTitle"]))
    S.append(Paragraph(
        "EXPERIMENTAL / UNVALIDATED — this report documents a system run and its "
        "provenance. It is not a validated scientific finding and must not be used "
        "as sole basis for enforcement.", ss["VSub"]))

    sys_status = sec("system_status")
    S.append(Paragraph("1. Case &amp; run metadata", ss["VH2"]))
    S.append(_kv_table([
        ("Case ID", operator_case.case_id),
        ("Run ID", run_id or "NOT_AVAILABLE"),
        ("Generated at", datetime.now(timezone.utc).isoformat(timespec="seconds")),
        ("Case status", getattr(sys_status, "case_status", None)),
        ("Scientific status", getattr(sys_status, "scientific_status", None)),
        ("EngineMode", getattr(sys_status, "engine_mode", None) or "NOT_AVAILABLE"),
        ("Recommendation", getattr(getattr(operator_case, "recommendation", None), "value", None)),
        ("Schema version", getattr(operator_case, "schema_version", None)),
    ], ss))

    # ------------------------------------------------ starting point
    sp = getattr(operator_case, "starting_point", None)
    pt = getattr(sp, "point", None) if sp else None
    S.append(Paragraph("2. Starting point (spill origin)", ss["VH2"]))
    S.append(_kv_table([
        ("Contract status", getattr(getattr(sp, "status", None), "value", "NOT_AVAILABLE")),
        ("Latitude", f"{pt.lat:.5f}" if pt else "NOT_AVAILABLE"),
        ("Longitude", f"{pt.lon:.5f}" if pt else "NOT_AVAILABLE"),
        ("Source", getattr(getattr(sp, "source", None), "value", None)),
        ("Land classification",
         getattr(getattr(sp, "land_classification", None), "value", None)),
        ("Reason", getattr(sp, "reason", None) or "—"),
    ], ss))

    # ------------------------------------------------ evidence chain
    det = val("detection")
    S.append(Paragraph("3. NETRA — detection", ss["VH2"]))
    S.append(_kv_table([
        ("Status", _section_status(sec("detection"))),
        ("Classification", getattr(det, "classification", None) if det else None),
        ("Confidence (uncalibrated)", getattr(det, "confidence", None) if det else None),
        ("Area km²", getattr(det, "area_km2", None) if det else None),
        ("Model version", getattr(det, "netra_model_version", None) if det else None),
    ], ss))

    S.append(Paragraph("4. PRATIVARTAN — origin reconstruction", ss["VH2"]))
    S.append(_kv_table([("Status", _section_status(sec("origin")))], ss))

    intel = getattr(operator_case, "intelligence", None)
    hyps = getattr(intel, "hypotheses", None) if intel else None
    items = getattr(hyps, "hypotheses", None) or [] if hyps else []
    S.append(Paragraph("5. CHHAYA — source hypotheses", ss["VH2"]))
    if items:
        best = max(items, key=lambda h: getattr(h, "posterior", 0.0))
        S.append(_kv_table([
            ("Top hypothesis", getattr(getattr(best, "source_class", None), "value",
                                       getattr(best, "source_class", None))),
            ("Relative plausibility", f"{getattr(best, 'posterior', 0.0):.3f}"),
            ("Hypotheses considered", len(items)),
        ], ss))
        S.append(Paragraph(
            "CHHAYA output is <b>uncalibrated relative plausibility</b>, not a calibrated "
            "probability. It must not be reported as a likelihood of guilt.", ss["VMuted"]))
    else:
        S.append(_kv_table([("Status", "NOT_AVAILABLE — no hypotheses composed")], ss))

    attr = val("attribution")
    S.append(Paragraph("6. NYAYA — attribution", ss["VH2"]))
    S.append(_kv_table([
        ("Status", _section_status(sec("attribution"))),
        ("Top posterior", getattr(attr, "top_posterior", None) if attr else None),
    ], ss))

    fc = val("forecast")
    lfs = getattr(fc, "landfalls", None) or [] if fc else []
    S.append(Paragraph("7. PRAVAAH — forecast", ss["VH2"]))
    S.append(_kv_table([
        ("Status", _section_status(sec("forecast"))),
        ("Horizon (h)", getattr(fc, "horizon_hours", None) if fc else None),
        ("Trajectory artifact", getattr(fc, "trajectory_path", None) if fc else None),
        ("Predicted landfalls", len(lfs) if fc else "NOT_AVAILABLE"),
    ], ss))
    for lf in lfs:
        S.append(Paragraph(
            f"• {getattr(lf, 'location_name', '?')} — ETA {getattr(lf, 'hours_until', '?')} h, "
            f"p={getattr(lf, 'probability', '?')}", ss["VBody"]))

    v = val("validity")
    S.append(Paragraph("8. Validity gate", ss["VH2"]))
    v_state = getattr(getattr(v, "state", None), "value", getattr(v, "state", None)) if v else None
    S.append(_kv_table([
        ("Status", _section_status(sec("validity"))),
        ("State", v_state),
        ("Allows operational action",
         ("yes" if v_state in ("valid", "degraded") else "no") if v_state else "NOT_AVAILABLE"),
        ("Blocking reasons", ", ".join(getattr(v, "blocking_reasons", None) or []) or "—"),
    ], ss))

    S.append(PageBreak())

    # ------------------------------------------------ operational record
    S.append(Paragraph("9. Alert history", ss["VH2"]))
    alerts = alerts or []
    if alerts:
        rows = [["Alert", "Severity", "Dimension", "Status", "Ack by"]]
        for a in alerts:
            rows.append([
                getattr(a, "alert_id", "?"),
                getattr(getattr(a, "severity", None), "value", "?"),
                getattr(a, "material_dimension", None) or getattr(a, "event_type", "—"),
                getattr(getattr(a, "status", None), "value", "?"),
                getattr(a, "acknowledged_by", None) or "—",
            ])
        t = Table(rows, colWidths=[34 * mm, 22 * mm, 46 * mm, 34 * mm, 32 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dfe3e8")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        S.append(t)
    else:
        S.append(Paragraph("NOT_AVAILABLE — no alerts were generated for this case. For a "
                           "fail-closed case this is the correct outcome.", ss["VBody"]))

    S.append(Paragraph("10. Notification delivery", ss["VH2"]))
    if channel_report:
        S.append(_kv_table(list(channel_report.items()), ss))
        S.append(Paragraph(
            "NOT_CONFIGURED means no credentials/endpoint exist for that channel in this "
            "deployment. No external delivery is claimed or simulated as successful.",
            ss["VMuted"]))
    else:
        S.append(Paragraph("NOT_AVAILABLE — no channel report supplied.", ss["VBody"]))

    missions = val("mission") or []
    S.append(Paragraph("11. Mission &amp; authorization", ss["VH2"]))
    if missions:
        m = missions[0]
        S.append(_kv_table([
            ("Mission ID", getattr(m, "mission_id", None)),
            ("State", getattr(getattr(m, "state", None), "value", getattr(m, "state", None))),
            ("Asset", getattr(m, "asset_id", None)),
            ("Human approved by", getattr(m, "human_approved_by", None) or "NOT AUTHORIZED"),
        ], ss))
    else:
        S.append(Paragraph(
            f"NOT_AVAILABLE — {getattr(sec('mission'), 'reason', None) or 'no mission proposed'}",
            ss["VBody"]))

    S.append(Paragraph("12. Authorization audit (PRAMAN)", ss["VH2"]))
    if mission_audit:
        rows = [["When", "Principal", "Role", "Permission", "Allowed"]]
        for e in mission_audit:
            rows.append([str(e.get("at", ""))[:19], str(e.get("principal_id", "")),
                         str(e.get("role", "")), str(e.get("permission", "")),
                         "ALLOW" if e.get("allowed") else "DENY"])
        t = Table(rows, colWidths=[36 * mm, 30 * mm, 28 * mm, 44 * mm, 20 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dfe3e8")),
        ]))
        S.append(t)
    else:
        S.append(Paragraph("NOT_AVAILABLE — no authorization decisions recorded.", ss["VBody"]))

    prov = getattr(operator_case, "provenance", None)
    S.append(Paragraph("13. Provenance", ss["VH2"]))
    S.append(_kv_table([
        ("Artifact IDs", len(getattr(prov, "artifact_ids", None) or [])),
        ("Model versions", getattr(prov, "model_versions", None) or "—"),
        ("Processing versions", getattr(prov, "processing_versions", None) or "—"),
        ("Manifest artifact", getattr(prov, "manifest_artifact_id", None) or "NOT_AVAILABLE"),
    ], ss))

    S.append(Paragraph("14. SMRITI — advisory memory", ss["VH2"]))
    if smriti_hits:
        for h in smriti_hits[:5]:
            S.append(Paragraph(
                f"• {h.get('case_id','?')} — similarity {h.get('score','?')}", ss["VBody"]))
        S.append(Paragraph(
            "SMRITI is advisory only. It never overrides current evidence, validity, or "
            "authorization.", ss["VMuted"]))
    else:
        S.append(Paragraph("NOT_AVAILABLE — no similar prior cases retrieved.", ss["VBody"]))

    dt = getattr(intel, "decision_trace", None) if intel else None
    S.append(Paragraph("15. Decision trace", ss["VH2"]))
    if dt is not None:
        steps = getattr(dt, "steps", None) or []
        S.append(_kv_table([("Recorded steps", len(steps))], ss))
        for st in steps[:10]:
            S.append(Paragraph(f"• {getattr(st, 'summary', None) or st}", ss["VBody"]))
    else:
        S.append(Paragraph("NOT_AVAILABLE — no decision trace composed.", ss["VBody"]))

    S.append(Spacer(1, 8))
    S.append(Paragraph(
        "Generated by VARUNA GRID. Sections marked NOT_AVAILABLE / NOT_CONFIGURED were not "
        "produced by the backend for this run and have not been filled in.", ss["VMuted"]))

    doc.build(S)
    return buf.getvalue()
