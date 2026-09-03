"""
VARUNA — alert message rendering.

Replaces a stub that returned the literal string
``f"Alert {template_id} with context {context}"`` — which would have been sent
verbatim to an operator's phone had anything called it.

Every renderer here states, in the message body, whether the alert came from a
REAL run or a REPLAY/SIMULATED one. An SMS that reaches a duty officer at
02:00 must never leave them guessing whether a drill is a real spill.
"""
from __future__ import annotations

import html
from typing import Any

__all__ = ["AlertTemplates", "render_subject", "render_text", "render_html", "render_sms"]

#: SMS is billed and truncated per segment; keep well inside 2 segments.
SMS_MAX_CHARS = 300


def _f(alert: Any, name: str, default: Any = None) -> Any:
    if isinstance(alert, dict):
        return alert.get(name, default)
    v = getattr(alert, name, default)
    return getattr(v, "value", v)


def _mode_banner(alert: Any) -> str:
    """The one thing that must never be ambiguous."""
    engine = (_f(alert, "engine_mode") or "unknown").upper()
    if engine == "REAL":
        return "REAL OPERATIONAL ALERT"
    if _f(alert, "is_simulated", True):
        return f"{engine} — NOT A REAL OPERATIONAL EVENT"
    return f"{engine}"


def render_subject(alert: Any) -> str:
    sev = str(_f(alert, "severity", "info")).upper()
    case = _f(alert, "case_id", "unknown-case")
    dim = _f(alert, "material_dimension") or _f(alert, "event_type", "alert")
    prefix = "" if (_f(alert, "engine_mode") or "").lower() == "real" else "[DRILL] "
    return f"{prefix}[VARUNA {sev}] {case} — {dim}"


def render_text(alert: Any) -> str:
    lines = [
        _mode_banner(alert),
        "",
        f"Case:      {_f(alert, 'case_id', '—')}",
        f"Severity:  {str(_f(alert, 'severity', '—')).upper()}",
        f"Changed:   {_f(alert, 'material_dimension') or _f(alert, 'event_type', '—')}",
        f"Raised:    {_f(alert, 'created_at', '—')}",
        "",
        "What changed",
        f"  {_f(alert, 'reason', '—')}",
    ]
    basis = _f(alert, "severity_basis")
    if basis:
        lines += ["", "Why this severity", f"  {basis}"]

    prev, cur = _f(alert, "previous_value"), _f(alert, "current_value")
    if prev is not None or cur is not None:
        lines += ["", f"Previous:  {prev}", f"Now:       {cur}"]

    routing = _f(alert, "routing") or {}
    recipients = routing.get("recipients") if isinstance(routing, dict) else None
    if recipients:
        roles = ", ".join(r.get("role", "?") for r in recipients)
        lines += ["", f"Routed to: {roles}"]

    refs = _f(alert, "evidence_refs") or []
    if refs:
        lines += ["", "Evidence:  " + ", ".join(str(r) for r in refs)]

    lines += [
        "",
        "Acknowledge in the VARUNA cockpit. This message is a notification "
        "only — acknowledging by replying has no effect.",
    ]
    return "\n".join(lines)


_SEV_COLOR = {
    "critical": "#b3261e", "high": "#b3261e", "medium": "#e8871a",
    "warning": "#e8871a", "low": "#1a7f5a", "info": "#1a7f5a",
    "blocked": "#5b6472",
}


def render_html(alert: Any) -> str:
    e = html.escape
    sev = str(_f(alert, "severity", "info")).lower()
    colour = _SEV_COLOR.get(sev, "#5b6472")
    is_real = (_f(alert, "engine_mode") or "").lower() == "real"
    banner_bg = "#b3261e" if is_real else "#e8871a"

    rows = []

    def row(k: str, v: Any) -> None:
        if v not in (None, "", []):
            rows.append(
                f'<tr><td style="padding:6px 12px 6px 0;color:#5b6472;'
                f'font-size:13px;white-space:nowrap">{e(k)}</td>'
                f'<td style="padding:6px 0;font-size:13px;color:#12213d">{e(str(v))}</td></tr>')

    row("Case", _f(alert, "case_id"))
    row("Severity", str(_f(alert, "severity", "")).upper())
    row("Changed", _f(alert, "material_dimension") or _f(alert, "event_type"))
    row("Raised", _f(alert, "created_at"))
    row("Previous", _f(alert, "previous_value"))
    row("Now", _f(alert, "current_value"))
    refs = _f(alert, "evidence_refs") or []
    if refs:
        row("Evidence", ", ".join(str(r) for r in refs))

    basis = _f(alert, "severity_basis")
    basis_block = (
        f'<p style="margin:14px 0 0;padding:10px 12px;background:#f4f6f9;'
        f'border-left:3px solid {colour};font-size:13px;color:#3b4759">'
        f'<strong>Why this severity:</strong> {e(str(basis))}</p>' if basis else "")

    return f"""<!doctype html>
<html><body style="margin:0;background:#eef1f5;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<div style="max-width:600px;margin:0 auto;background:#ffffff">
  <div style="height:3px;background:linear-gradient(90deg,#e8871a 33%,#ffffff 33% 66%,#1a7f5a 66%)"></div>
  <div style="background:{banner_bg};color:#ffffff;padding:8px 20px;font-size:12px;
              letter-spacing:.08em;text-transform:uppercase;font-weight:600">
    {e(_mode_banner(alert))}
  </div>
  <div style="padding:20px">
    <div style="font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#5b6472">
      VARUNA GRID · Maritime oil-spill response
    </div>
    <h1 style="margin:6px 0 2px;font-size:20px;color:#12213d">
      {e(str(_f(alert, 'material_dimension') or _f(alert, 'event_type', 'Alert')))}
    </h1>
    <p style="margin:0 0 14px;font-size:14px;color:#3b4759">{e(str(_f(alert, 'reason', '')))}</p>
    <table style="border-collapse:collapse;width:100%">{''.join(rows)}</table>
    {basis_block}
    <p style="margin:18px 0 0;font-size:12px;color:#5b6472">
      Acknowledge in the VARUNA cockpit. This message is a notification only —
      replying to it has no effect.
    </p>
  </div>
  <div style="padding:10px 20px;background:#12213d;color:#8d9bb2;font-size:11px">
    Govt. of India · Restricted · For official use only
  </div>
</div></body></html>"""


def render_sms(alert: Any) -> str:
    """Short, unambiguous, and truncated on a word boundary."""
    prefix = "" if (_f(alert, "engine_mode") or "").lower() == "real" else "[DRILL] "
    sev = str(_f(alert, "severity", "")).upper()
    case = _f(alert, "case_id", "?")
    dim = _f(alert, "material_dimension") or _f(alert, "event_type", "alert")
    reason = str(_f(alert, "reason", "") or "")
    msg = f"{prefix}VARUNA {sev}: {case} — {dim}. {reason} Acknowledge in the cockpit."
    if len(msg) <= SMS_MAX_CHARS:
        return msg
    cut = msg[:SMS_MAX_CHARS - 1].rsplit(" ", 1)[0]
    return cut + "…"


class AlertTemplates:
    """Kept as a class for the existing import site; the module-level
    functions above are the real API."""

    @staticmethod
    def format_alert(template_id: str, context: dict[str, Any]) -> str:
        return render_text(context)

    subject = staticmethod(render_subject)
    text = staticmethod(render_text)
    html = staticmethod(render_html)
    sms = staticmethod(render_sms)
