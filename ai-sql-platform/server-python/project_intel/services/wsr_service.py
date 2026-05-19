from __future__ import annotations

"""
WSR (Weekly Status Report) generation pipeline.

Flow
----
  free text  ──parse_wsr_text()──►  WSRData
  WSRData    ──render_html()──►     HTML string  (browser preview)
  WSRData    ──render_pdf()──►      bytes         (download)
  WSRData    ──send_email()──►      SMTP dispatch (optional)

Environment variables (email)
-----------------------------
  SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD,
  SMTP_FROM (default = SMTP_USER), SMTP_TLS (default "true")
"""

import json
import logging
import os
import re
import textwrap
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Brand colours
# ---------------------------------------------------------------------------

_BRAND_DARK   = (27, 58, 107)      # navy  #1B3A6B
_BRAND_ACCENT = (0, 162, 210)      # teal  #00A2D2
_SECTION_BG   = (235, 242, 250)    # pale blue
_TABLE_HEADER = (27, 58, 107)

# ---------------------------------------------------------------------------
# Internal data model (mirrors WSRRequest schema)
# ---------------------------------------------------------------------------

@dataclass
class WSRData:
    project_name: str
    reporting_period: str
    project_module: str = ""
    key_highlights: list[dict] = field(default_factory=list)   # [{section, bullets}]
    blockers: list[str] = field(default_factory=list)
    key_risks: list[dict] = field(default_factory=list)        # [{group, items}]
    next_week_plan: list[dict] = field(default_factory=list)   # [{group, items}]
    completion_percentage: int | None = None
    report_recipients: list[str] = field(default_factory=list)
    defects_open: int = 0
    defects_closed: int = 0
    defects_in_progress: int = 0
    generated_by: str = ""


def _from_schema(req) -> WSRData:
    d = req.defects
    return WSRData(
        project_name=req.project_name,
        reporting_period=req.reporting_period,
        project_module=req.project_module or "",
        key_highlights=[h.model_dump() for h in req.key_highlights],
        blockers=req.blockers,
        key_risks=[g.model_dump() for g in req.key_risks],
        next_week_plan=[g.model_dump() for g in req.next_week_plan],
        completion_percentage=req.completion_percentage,
        report_recipients=req.report_recipients,
        defects_open=d.open if d else 0,
        defects_closed=d.closed if d else 0,
        defects_in_progress=d.in_progress if d else 0,
        generated_by=req.generated_by or "",
    )


# ---------------------------------------------------------------------------
# LLM parser: free text → WSRData
# ---------------------------------------------------------------------------

_PARSE_SYSTEM = (
    "You are a project reporting assistant. "
    "Extract structured WSR data from the provided text. "
    "Return only valid JSON with no markdown fences."
)

_PARSE_PROMPT = """\
Extract a structured Weekly Status Report from the text below.

Return ONLY a JSON object using this exact schema (use null for unknown/missing fields):
{{
  "project_name": "...",
  "reporting_period": "...",
  "project_module": "...",
  "key_highlights": [
    {{"section": "section title", "bullets": ["bullet 1", "bullet 2"]}}
  ],
  "blockers": ["blocker 1", "blocker 2"],
  "key_risks": [
    {{"group": "group name", "items": ["item 1", "item 2"]}}
  ],
  "next_week_plan": [
    {{"group": "group name", "items": ["item 1", "item 2"]}}
  ],
  "completion_percentage": 50,
  "report_recipients": ["email@example.com"],
  "defects": {{
    "open": 25,
    "closed": 50,
    "in_progress": 27
  }}
}}

Raw WSR text:
{text}
"""


def parse_wsr_text(text: str) -> WSRData:
    """Use LLM to extract structured WSRData from free-form text."""
    from project_intel.core.config import OPENAI_MODEL
    from project_intel.core.openai_client import get_openai_clients

    text = (text or "").strip()
    if not text:
        raise ValueError("empty_text")

    clients = get_openai_clients()
    if not clients:
        raise RuntimeError("OpenAI not configured — cannot parse WSR text.")

    prompt = _PARSE_PROMPT.format(text=text)
    last_error = ""
    for client in clients:
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": _PARSE_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = (resp.choices[0].message.content or "").strip()
            raw = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip().strip("`").strip()
            parsed = json.loads(raw)
            break
        except Exception as exc:
            status = getattr(exc, "status_code", None) or getattr(
                getattr(exc, "response", None), "status_code", None
            )
            if status in (401, 403, 404, 429):
                last_error = str(exc)
                continue
            raise
    else:
        raise RuntimeError(f"LLM unavailable: {last_error}")

    d = parsed.get("defects") or {}
    return WSRData(
        project_name=parsed.get("project_name") or "Unknown Project",
        reporting_period=parsed.get("reporting_period") or "",
        project_module=parsed.get("project_module") or "",
        key_highlights=parsed.get("key_highlights") or [],
        blockers=parsed.get("blockers") or [],
        key_risks=parsed.get("key_risks") or [],
        next_week_plan=parsed.get("next_week_plan") or [],
        completion_percentage=parsed.get("completion_percentage"),
        report_recipients=[r for r in (parsed.get("report_recipients") or []) if r],
        defects_open=int(d.get("open") or 0),
        defects_closed=int(d.get("closed") or 0),
        defects_in_progress=int(d.get("in_progress") or 0),
    )


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------

def _pct_bar(pct: int) -> str:
    filled = max(0, min(pct, 100))
    return (
        f'<div style="background:#dde6f0;border-radius:4px;height:14px;width:100%;margin:4px 0">'
        f'<div style="background:#1B3A6B;width:{filled}%;height:14px;border-radius:4px"></div></div>'
        f'<span style="font-size:12px;color:#555">{pct}% complete</span>'
    )


def render_html(data: WSRData) -> str:
    generated = datetime.utcnow().strftime("%d %b %Y %H:%M UTC")
    by_line = f" &nbsp;|&nbsp; Prepared by: {data.generated_by}" if data.generated_by else ""

    def section_header(title: str) -> str:
        return (
            f'<tr><td colspan="2" style="background:#1B3A6B;color:#fff;font-weight:bold;'
            f'font-size:13px;padding:8px 12px;letter-spacing:0.5px">{title}</td></tr>'
        )

    def group_block(groups: list[dict], numbered: bool = False) -> str:
        out = []
        for g in groups:
            items = g.get("items") or []
            tag = "ol" if numbered else "ul"
            lis = "".join(f"<li>{i}</li>" for i in items)
            out.append(
                f'<tr><td colspan="2" style="padding:6px 12px 10px">'
                f'<strong style="color:#1B3A6B">{g.get("group","")}</strong>'
                f'<{tag} style="margin:4px 0 0 18px;line-height:1.7">{lis}</{tag}></td></tr>'
            )
        return "".join(out)

    # Key highlights
    highlights_rows = ""
    for h in data.key_highlights:
        bullets = "".join(f"<li>{b}</li>" for b in (h.get("bullets") or []))
        highlights_rows += (
            f'<tr><td colspan="2" style="padding:6px 12px 10px">'
            f'<strong style="color:#1B3A6B">{h.get("section","")}</strong>'
            f'<ul style="margin:4px 0 0 18px;line-height:1.7">{bullets}</ul></td></tr>'
        )

    # Blockers
    blocker_items = "".join(f"<li>{b}</li>" for b in data.blockers)
    blockers_html = (
        f'<tr><td colspan="2" style="padding:6px 12px 10px">'
        f'<ul style="margin:4px 0 0 18px;line-height:1.7;color:#c0392b">{blocker_items}</ul></td></tr>'
    ) if data.blockers else ""

    # Risks
    risks_rows = group_block(data.key_risks)

    # Next week
    next_week_rows = group_block(data.next_week_plan, numbered=True)

    # Completion bar
    completion_html = ""
    if data.completion_percentage is not None:
        completion_html = (
            f'<tr style="background:#f5f9ff">'
            f'<td style="padding:8px 12px;font-weight:bold;width:40%">Overall Completion</td>'
            f'<td style="padding:8px 12px">{_pct_bar(data.completion_percentage)}</td></tr>'
        )

    # Defects table
    total = data.defects_open + data.defects_closed + data.defects_in_progress
    defects_html = ""
    if total > 0:
        defects_html = f"""
        {section_header("DEFECTS STATUS")}
        <tr><td colspan="2" style="padding:10px 12px">
          <table style="width:100%;border-collapse:collapse;font-size:13px;text-align:center">
            <tr style="background:#1B3A6B;color:#fff">
              <th style="padding:8px">Open</th>
              <th style="padding:8px">In-Progress</th>
              <th style="padding:8px">Closed</th>
              <th style="padding:8px">Total</th>
            </tr>
            <tr>
              <td style="padding:10px;background:#fdecea;font-size:20px;font-weight:bold;color:#c0392b">{data.defects_open}</td>
              <td style="padding:10px;background:#fff8e1;font-size:20px;font-weight:bold;color:#e67e22">{data.defects_in_progress}</td>
              <td style="padding:10px;background:#e8f5e9;font-size:20px;font-weight:bold;color:#27ae60">{data.defects_closed}</td>
              <td style="padding:10px;background:#eaf0fb;font-size:20px;font-weight:bold;color:#1B3A6B">{total}</td>
            </tr>
          </table>
        </td></tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: Arial, sans-serif; font-size: 13px; color: #222; margin: 0; background: #f0f4f8; }}
  .container {{ max-width: 820px; margin: 24px auto; background: #fff; border: 1px solid #cdd8e8; border-radius: 6px; overflow: hidden; }}
  table {{ width: 100%; border-collapse: collapse; }}
  tr {{ border-bottom: 1px solid #e5ecf5; }}
</style>
</head>
<body>
<div class="container">
  <!-- Header -->
  <div style="background:#1B3A6B;padding:18px 24px;display:flex;align-items:center;justify-content:space-between">
    <div>
      <div style="color:#00A2D2;font-size:11px;letter-spacing:2px;font-weight:bold">BUSINESSNEXT</div>
      <div style="color:#fff;font-size:20px;font-weight:bold;margin-top:2px">Weekly Status Report</div>
    </div>
    <div style="text-align:right;color:#a0b8d8;font-size:11px">
      Generated: {generated}{by_line}
    </div>
  </div>

  <table>
    <!-- Project info -->
    <tr style="background:#eaf0fb">
      <td style="padding:10px 12px;font-weight:bold;width:40%">Project</td>
      <td style="padding:10px 12px">{data.project_name}</td>
    </tr>
    <tr>
      <td style="padding:10px 12px;font-weight:bold">Reporting Period</td>
      <td style="padding:10px 12px">{data.reporting_period}</td>
    </tr>
    {"" if not data.project_module else f'<tr style="background:#eaf0fb"><td style="padding:10px 12px;font-weight:bold">Module</td><td style="padding:10px 12px">{data.project_module}</td></tr>'}
    {completion_html}

    <!-- Key Highlights -->
    {section_header("KEY HIGHLIGHTS THIS WEEK")}
    {highlights_rows}

    <!-- Blockers -->
    {section_header("BLOCKERS") if data.blockers else ""}
    {blockers_html}

    <!-- Risks -->
    {section_header("KEY RISKS / ISSUES") if data.key_risks else ""}
    {risks_rows}

    <!-- Next Week Plan -->
    {section_header("NEXT WEEK PLAN") if data.next_week_plan else ""}
    {next_week_rows}

    <!-- Defects -->
    {defects_html}

    <!-- Footer -->
    <tr>
      <td colspan="2" style="padding:10px 12px;background:#f5f9ff;font-size:11px;color:#888;text-align:center">
        This report is auto-generated by BUSINESSNEXT Project Intelligence Platform
        {"&nbsp;|&nbsp; Recipients: " + ", ".join(data.report_recipients) if data.report_recipients else ""}
      </td>
    </tr>
  </table>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# PDF renderer (fpdf2)
# ---------------------------------------------------------------------------

def render_pdf(data: WSRData) -> bytes:
    try:
        from fpdf import FPDF  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "fpdf2 is required for PDF export. Install: pip install 'fpdf2>=2.7.0'"
        ) from exc

    class _WSR(FPDF):
        def header(self):
            self.set_fill_color(*_BRAND_DARK)
            self.set_text_color(255, 255, 255)
            self.set_font("Helvetica", "B", 15)
            self.cell(0, 12, "BUSINESSNEXT  —  Weekly Status Report", fill=True,
                      new_x="LEFT", new_y="NEXT", align="C")
            self.set_text_color(0, 0, 0)
            self.set_font("Helvetica", "", 10)
            self.ln(2)

        def footer(self):
            self.set_y(-13)
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(140)
            self.cell(0, 8,
                      f"Auto-generated by BUSINESSNEXT Project Intelligence | Page {self.page_no()}/{{nb}}",
                      align="C")
            self.set_text_color(0)

    pdf = _WSR(orientation="P", unit="mm", format="A4")
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=18)

    W = pdf.w - pdf.l_margin - pdf.r_margin   # usable width
    L = pdf.l_margin

    def section_title(title: str):
        pdf.set_fill_color(*_BRAND_DARK)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_x(L)
        pdf.cell(W, 7, f"  {title}", fill=True, new_x="LEFT", new_y="NEXT")
        pdf.set_text_color(0)
        pdf.ln(1)

    def info_row(label: str, value: str, shaded: bool = False):
        if shaded:
            pdf.set_fill_color(*_SECTION_BG)
        else:
            pdf.set_fill_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_x(L)
        pdf.cell(55, 7, label, fill=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(W - 55, 7, value or "—", fill=True, new_x="LEFT", new_y="NEXT")

    def bullet_lines(items: list[str], indent: float = 6, marker: str = "•"):
        for item in items:
            pdf.set_font("Helvetica", "", 10)
            pdf.set_x(L + indent)
            wrapped = textwrap.fill(item, width=90)
            for i, line in enumerate(wrapped.splitlines()):
                pdf.set_x(L + indent)
                prefix = f"{marker} " if i == 0 else "   "
                pdf.cell(6, 6, prefix)
                pdf.multi_cell(W - indent - 6, 6, line, new_x="LEFT", new_y="NEXT")
        pdf.ln(1)

    def numbered_lines(items: list[str], indent: float = 6):
        for n, item in enumerate(items, 1):
            pdf.set_font("Helvetica", "", 10)
            pdf.set_x(L + indent)
            pdf.cell(8, 6, f"{n}.")
            pdf.multi_cell(W - indent - 8, 6, item, new_x="LEFT", new_y="NEXT")
        pdf.ln(1)

    # ---- Project info ----
    info_row("Project", data.project_name, shaded=True)
    info_row("Reporting Period", data.reporting_period)
    if data.project_module:
        info_row("Module", data.project_module, shaded=True)

    # Completion bar
    if data.completion_percentage is not None:
        pct = max(0, min(data.completion_percentage, 100))
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_x(L)
        pdf.set_fill_color(*_SECTION_BG)
        pdf.cell(55, 7, "Overall Completion", fill=True)
        bar_x = pdf.get_x()
        bar_y = pdf.get_y()
        bar_w = W - 55
        bar_h = 5
        # Background
        pdf.set_fill_color(210, 225, 240)
        pdf.rect(bar_x, bar_y + 1, bar_w, bar_h, style="F")
        # Fill
        pdf.set_fill_color(*_BRAND_DARK)
        pdf.rect(bar_x, bar_y + 1, bar_w * pct / 100, bar_h, style="F")
        pdf.set_xy(bar_x, bar_y)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(bar_w, 7, f"  {pct}%", new_x="LEFT", new_y="NEXT")
    pdf.ln(3)

    # ---- Key Highlights ----
    if data.key_highlights:
        section_title("KEY HIGHLIGHTS THIS WEEK")
        for h in data.key_highlights:
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_x(L + 3)
            pdf.cell(0, 6, h.get("section", ""), new_x="LEFT", new_y="NEXT")
            bullet_lines(h.get("bullets") or [], indent=8)

    # ---- Blockers ----
    if data.blockers:
        section_title("BLOCKERS")
        pdf.set_text_color(180, 30, 30)
        bullet_lines(data.blockers, indent=6)
        pdf.set_text_color(0)

    # ---- Key Risks ----
    if data.key_risks:
        section_title("KEY RISKS / ISSUES")
        for g in data.key_risks:
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_x(L + 3)
            pdf.cell(0, 6, g.get("group", ""), new_x="LEFT", new_y="NEXT")
            bullet_lines(g.get("items") or [], indent=8)

    # ---- Next Week Plan ----
    if data.next_week_plan:
        section_title("NEXT WEEK PLAN")
        for g in data.next_week_plan:
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_x(L + 3)
            pdf.cell(0, 6, g.get("group", ""), new_x="LEFT", new_y="NEXT")
            numbered_lines(g.get("items") or [], indent=8)

    # ---- Defects table ----
    total = data.defects_open + data.defects_closed + data.defects_in_progress
    if total > 0:
        section_title("DEFECTS STATUS")
        col_w = W / 4
        headers = ["Open", "In-Progress", "Closed", "Total"]
        values = [
            str(data.defects_open),
            str(data.defects_in_progress),
            str(data.defects_closed),
            str(total),
        ]
        colors = [(192, 57, 43), (230, 126, 34), (39, 174, 96), (27, 58, 107)]

        pdf.set_fill_color(*_TABLE_HEADER)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 10)
        for h in headers:
            pdf.cell(col_w, 8, h, fill=True, border=1, align="C")
        pdf.ln()

        pdf.set_font("Helvetica", "B", 14)
        for val, col in zip(values, colors):
            pdf.set_fill_color(245, 245, 245)
            pdf.set_text_color(*col)
            pdf.cell(col_w, 12, val, fill=True, border=1, align="C")
        pdf.set_text_color(0)
        pdf.ln(4)

    return bytes(pdf.output())


# ---------------------------------------------------------------------------
# Email sender
# ---------------------------------------------------------------------------

def send_email(data: WSRData, pdf_bytes: bytes) -> dict:
    """Send the WSR PDF to all report_recipients. Returns {ok, sent, skipped, error?}."""
    import smtplib
    from email.message import EmailMessage

    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        return {"ok": False, "error": "SMTP_HOST not configured", "sent": [], "skipped": []}

    port = int(os.getenv("SMTP_PORT", "587") or "587")
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    from_addr = os.getenv("SMTP_FROM", user).strip() or user
    use_tls = os.getenv("SMTP_TLS", "true").strip().lower() not in ("0", "false", "no", "n")

    recipients = [r.strip() for r in data.report_recipients if r.strip()]
    if not recipients:
        return {"ok": True, "sent": [], "skipped": [], "note": "no_recipients"}

    subject = (
        f"WSR | {data.project_name}"
        + (f" — {data.project_module}" if data.project_module else "")
        + f" | {data.reporting_period}"
    )
    filename = re.sub(r"[^a-zA-Z0-9_\-]", "_", data.project_name) + "_WSR.pdf"

    sent: list[str] = []
    skipped: list[str] = []

    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            if use_tls:
                smtp.starttls()
            if user and password:
                smtp.login(user, password)

            for recipient in recipients:
                try:
                    msg = EmailMessage()
                    msg["From"] = from_addr
                    msg["To"] = recipient
                    msg["Subject"] = subject
                    msg.set_content(
                        f"Please find the Weekly Status Report attached.\n\n"
                        f"Project : {data.project_name}\n"
                        f"Module  : {data.project_module or 'N/A'}\n"
                        f"Period  : {data.reporting_period}\n\n"
                        f"— BUSINESSNEXT Project Intelligence"
                    )
                    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf",
                                       filename=filename)
                    smtp.send_message(msg)
                    sent.append(recipient)
                except Exception as exc:
                    logger.warning("Email to %s failed: %s", recipient, exc)
                    skipped.append(recipient)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "sent": sent, "skipped": skipped}

    return {"ok": True, "sent": sent, "skipped": skipped}
