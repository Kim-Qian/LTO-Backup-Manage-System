import os
from datetime import datetime, timezone
from config_manager import cfg
from ui import console, header, wait_for_keypress


# =============================================================================
# HEALTH SCORING
# =============================================================================

def _health_status(usage_pct, last_verify_result, success_rate, days_since_backup):
    """
    Return 'critical', 'warning', or 'good' based on four health indicators.

    Critical triggers (any one is enough):
      - Tape usage > 95 %
      - Last verify run returned FAILED/CORRUPTED
      - Backup success rate < 60 %

    Warning triggers (any one, if not already critical):
      - Tape usage > 80 %
      - Days since last backup > 30
      - Backup success rate < 80 %
      - Tape has data but has never been verified
    """
    if usage_pct > 95:
        return "critical"
    if last_verify_result in ("FAILED", "CORRUPTED", "PARTIAL"):
        return "critical"
    if success_rate is not None and success_rate < 0.60:
        return "critical"

    if usage_pct > 80:
        return "warning"
    if days_since_backup is not None and days_since_backup > 30:
        return "warning"
    if success_rate is not None and success_rate < 0.80:
        return "warning"
    if last_verify_result is None:
        return "warning"  # Never verified

    return "good"


# =============================================================================
# DATA COLLECTION
# =============================================================================

def _collect_tape_data(db, now):
    """Build a list of per-tape stat dicts for the report."""
    tape_rows = db.conn.execute(
        "SELECT tape_id, generation, encrypted, description, used_capacity "
        "FROM tapes ORDER BY tape_id"
    ).fetchall()

    tapes_data = []
    for tape_id, generation, encrypted, description, used_capacity in tape_rows:
        gen_info = cfg.get_generation_info(generation)
        max_cap  = gen_info.get("capacity", 1)
        usage_pct = used_capacity / max_cap * 100 if max_cap > 0 else 0

        labels = db.get_labels_for_tape(tape_id)

        # Backup job stats
        backup_jobs = db.conn.execute(
            "SELECT status, finished_at FROM jobs "
            "WHERE tape_id=? AND action='BACKUP'",
            (tape_id,)
        ).fetchall()
        total_jobs  = len(backup_jobs)
        failed_jobs = sum(1 for s, _ in backup_jobs if s == "FAILED")
        success_rate = (
            (total_jobs - failed_jobs) / total_jobs if total_jobs > 0 else None
        )

        # Last successful backup timestamp
        last_bk_row = db.conn.execute(
            "SELECT MAX(finished_at) FROM jobs "
            "WHERE tape_id=? AND status='SUCCESS' AND action='BACKUP'",
            (tape_id,)
        ).fetchone()
        last_backup_ts = last_bk_row[0] if last_bk_row else None

        days_since_backup = None
        if last_backup_ts:
            try:
                dt = datetime.fromisoformat(last_backup_ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                days_since_backup = (now - dt).days
            except Exception:
                pass

        # Last verify result
        verify_row = db.conn.execute(
            "SELECT status, finished_at FROM jobs "
            "WHERE tape_id=? AND action='VERIFY' "
            "ORDER BY job_id DESC LIMIT 1",
            (tape_id,)
        ).fetchone()
        last_verify_result = verify_row[0] if verify_row else None
        last_verify_ts     = verify_row[1] if verify_row else None

        health = _health_status(
            usage_pct, last_verify_result, success_rate, days_since_backup
        )

        tapes_data.append({
            "tape_id":           tape_id,
            "generation":        gen_info.get("name", generation),
            "encrypted":         bool(encrypted),
            "description":       description or "",
            "labels":            labels,
            "used_gb":           used_capacity / 1024 ** 3,
            "max_gb":            max_cap / 1024 ** 3,
            "usage_pct":         usage_pct,
            "total_jobs":        total_jobs,
            "failed_jobs":       failed_jobs,
            "success_rate":      success_rate,
            "last_backup_ts":    last_backup_ts,
            "days_since_backup": days_since_backup,
            "last_verify_result":last_verify_result,
            "last_verify_ts":    last_verify_ts,
            "health":            health,
        })

    return tapes_data


# =============================================================================
# HTML RENDERING HELPERS
# =============================================================================

def _fmt_ts(ts):
    """Short human-readable timestamp, or '—' if missing."""
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts


def _usage_bar(pct):
    """HTML snippet for a colour-coded usage progress bar."""
    clamped = min(max(pct, 0), 100)
    if clamped > 95:
        color = "#f44336"
    elif clamped > 80:
        color = "#ff9800"
    else:
        color = "#4caf50"
    return (
        f'<div class="bar-wrap">'
        f'<div class="bar-fill" style="width:{clamped:.1f}%;background:{color}"></div>'
        f'</div>'
        f'<span class="bar-label">{pct:.1f}%</span>'
    )


def _health_badge(status):
    """Coloured badge HTML for a health status string."""
    cfg_map = {
        "good":     ("🟢", "good",     "Good"),
        "warning":  ("🟡", "warning",  "Warning"),
        "critical": ("🔴", "critical", "Critical"),
    }
    icon, css, label = cfg_map.get(status, ("⚪", "good", status.capitalize()))
    return f'<span class="badge badge-{css}">{icon} {label}</span>'


def _verify_badge(result):
    cfg_map = {
        "SUCCESS": ("✅", "#4caf50", "Passed"),
        "FAILED":  ("❌", "#f44336", "Failed"),
        "PARTIAL": ("⚠️",  "#ff9800", "Partial"),
    }
    if result is None:
        return '<span style="color:#888">Never</span>'
    icon, color, label = cfg_map.get(result, ("ℹ️", "#888", result))
    return f'<span style="color:{color}">{icon} {label}</span>'


# =============================================================================
# FULL HTML GENERATION
# =============================================================================

def _render_html(summary, tapes_data):
    # ---- Summary cards --------------------------------------------------------
    total_used_str = f"{summary['total_used_tb']:.2f} TB"
    total_cap_str  = f"{summary['total_cap_tb']:.2f} TB"
    overall_pct    = (
        summary["total_used_tb"] / summary["total_cap_tb"] * 100
        if summary["total_cap_tb"] > 0 else 0
    )

    cards_html = f"""
    <div class="cards">
      <div class="card">
        <div class="card-icon">📼</div>
        <div class="card-value">{summary['tape_count']}</div>
        <div class="card-label">Total Tapes</div>
      </div>
      <div class="card">
        <div class="card-icon">💾</div>
        <div class="card-value">{total_used_str}</div>
        <div class="card-label">Used of {total_cap_str} ({overall_pct:.1f}%)</div>
      </div>
      <div class="card">
        <div class="card-icon">{'❌' if summary['failed_jobs'] > 0 else '✅'}</div>
        <div class="card-value" style="color:{'#f44336' if summary['failed_jobs'] > 0 else '#4caf50'}">{summary['failed_jobs']}</div>
        <div class="card-label">Failed Jobs (all time)</div>
      </div>
      <div class="card">
        <div class="card-icon">🕒</div>
        <div class="card-value" style="font-size:1.2em">{_fmt_ts(summary['last_backup'])}</div>
        <div class="card-label">Last Successful Backup</div>
      </div>
    </div>
    """

    # ---- Per-tape rows --------------------------------------------------------
    rows_html = ""
    for t in tapes_data:
        label_chips = "".join(
            f'<span class="chip">{l}</span>' for l in t["labels"]
        ) or '<span style="color:#555">—</span>'

        enc_badge = (
            '<span class="badge badge-enc">🔒 Encrypted</span>'
            if t["encrypted"]
            else '<span class="badge badge-plain">🔓 Plain</span>'
        )

        rate_str = (
            f"{t['success_rate'] * 100:.0f}%"
            if t["success_rate"] is not None else "—"
        )
        jobs_str = f"{t['total_jobs'] - t['failed_jobs']}/{t['total_jobs']}"

        last_bk_str = _fmt_ts(t["last_backup_ts"])
        if t["days_since_backup"] is not None:
            last_bk_str += f' <span class="dim">({t["days_since_backup"]}d ago)</span>'

        rows_html += f"""
        <tr>
          <td><strong>{t['tape_id']}</strong><br><span class="dim">{t['description']}</span></td>
          <td>{t['generation']}</td>
          <td>{enc_badge}</td>
          <td>{label_chips}</td>
          <td>
            {_usage_bar(t['usage_pct'])}
            <span class="dim">{t['used_gb']:.2f} / {t['max_gb']:.2f} GB</span>
          </td>
          <td>{jobs_str}<br><span class="dim">({rate_str} success)</span></td>
          <td>{last_bk_str}</td>
          <td>
            {_verify_badge(t['last_verify_result'])}
            <br><span class="dim">{_fmt_ts(t['last_verify_ts'])}</span>
          </td>
          <td>{_health_badge(t['health'])}</td>
        </tr>
        """

    # ---- Full HTML document ---------------------------------------------------
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LTO Health Report — {summary['generated_at']}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      background: #0d0d1a;
      color: #d0d0e8;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 14px;
      line-height: 1.6;
    }}

    /* ---- Header ---- */
    .page-header {{
      background: linear-gradient(135deg, #1a1a3e 0%, #0d0d1a 100%);
      border-bottom: 1px solid #2a2a5a;
      padding: 28px 40px 20px;
    }}
    .page-header h1 {{
      font-size: 1.8em;
      color: #7ab4ff;
      letter-spacing: 2px;
      text-transform: uppercase;
    }}
    .page-header .meta {{
      color: #557;
      margin-top: 4px;
      font-size: 0.85em;
    }}

    /* ---- Layout wrapper ---- */
    .content {{ padding: 30px 40px; }}

    /* ---- Summary cards ---- */
    .cards {{
      display: flex;
      gap: 18px;
      margin-bottom: 36px;
      flex-wrap: wrap;
    }}
    .card {{
      background: #141428;
      border: 1px solid #2a2a5a;
      border-radius: 10px;
      padding: 22px 28px;
      flex: 1;
      min-width: 180px;
      text-align: center;
    }}
    .card-icon  {{ font-size: 1.8em; margin-bottom: 8px; }}
    .card-value {{ font-size: 2em; font-weight: bold; color: #7ab4ff; }}
    .card-label {{ color: #668; font-size: 0.82em; margin-top: 4px; }}

    /* ---- Section title ---- */
    .section-title {{
      font-size: 1em;
      letter-spacing: 2px;
      text-transform: uppercase;
      color: #7ab4ff;
      margin-bottom: 14px;
      border-bottom: 1px solid #2a2a5a;
      padding-bottom: 6px;
    }}

    /* ---- Table ---- */
    .tape-table {{
      width: 100%;
      border-collapse: collapse;
    }}
    .tape-table th {{
      background: #1a1a3e;
      color: #8ab;
      font-size: 0.78em;
      letter-spacing: 1px;
      text-transform: uppercase;
      padding: 10px 14px;
      text-align: left;
      border-bottom: 2px solid #2a2a5a;
    }}
    .tape-table td {{
      padding: 12px 14px;
      border-bottom: 1px solid #1e1e3a;
      vertical-align: middle;
    }}
    .tape-table tr:hover td {{ background: #141428; }}

    /* ---- Usage bar ---- */
    .bar-wrap {{
      background: #1e1e3a;
      border-radius: 4px;
      height: 10px;
      width: 130px;
      overflow: hidden;
      display: inline-block;
      vertical-align: middle;
      margin-right: 6px;
    }}
    .bar-fill {{
      height: 100%;
      border-radius: 4px;
      transition: width 0.3s;
    }}
    .bar-label {{ font-size: 0.8em; color: #aaa; }}

    /* ---- Badges ---- */
    .badge {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 0.78em;
      font-weight: bold;
    }}
    .badge-good     {{ background: #1a3a1a; color: #4caf50; border: 1px solid #2d6b2d; }}
    .badge-warning  {{ background: #3a2a10; color: #ff9800; border: 1px solid #7a5200; }}
    .badge-critical {{ background: #3a1010; color: #f44336; border: 1px solid #7a2020; }}
    .badge-enc      {{ background: #1a2540; color: #6699ff; border: 1px solid #2244aa; }}
    .badge-plain    {{ background: #1a3020; color: #66aa66; border: 1px solid #225522; }}

    /* ---- Label chips ---- */
    .chip {{
      display: inline-block;
      background: #1e2850;
      color: #88aaff;
      border: 1px solid #2a3a7a;
      border-radius: 10px;
      padding: 1px 8px;
      font-size: 0.76em;
      margin: 1px 2px;
    }}

    /* ---- Misc ---- */
    .dim {{ color: #557; }}

    /* ---- Footer ---- */
    .footer {{
      text-align: center;
      color: #335;
      font-size: 0.78em;
      padding: 24px 40px;
      border-top: 1px solid #1a1a3a;
      margin-top: 40px;
    }}
  </style>
</head>
<body>

<div class="page-header">
  <h1>📼 LTO Backup — Health Report</h1>
  <div class="meta">Generated: {summary['generated_at']}</div>
</div>

<div class="content">

  {cards_html}

  <div class="section-title">Tape Health Overview</div>

  <table class="tape-table">
    <thead>
      <tr>
        <th>Tape / Description</th>
        <th>Generation</th>
        <th>Encryption</th>
        <th>Labels</th>
        <th>Usage</th>
        <th>Jobs (pass/total)</th>
        <th>Last Backup</th>
        <th>Last Verify</th>
        <th>Health</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>

</div>

<div class="footer">
  LTO Backup &amp; Manage System — Health Report
  &nbsp;·&nbsp; Generated {summary['generated_at']}
</div>

</body>
</html>
"""


# =============================================================================
# PUBLIC ENTRY POINT
# =============================================================================

def generate_health_report(db, output_path="health_report.html"):
    """
    Collect statistics for every tape and write a self-contained HTML report.
    Returns the path to the written file.
    """
    now = datetime.now(timezone.utc)

    # ---- Global summary stats ------------------------------------------------
    tape_count = db.conn.execute("SELECT COUNT(*) FROM tapes").fetchone()[0]
    total_used = db.conn.execute("SELECT SUM(used_capacity) FROM tapes").fetchone()[0] or 0
    failed_jobs = db.conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE status='FAILED'"
    ).fetchone()[0]
    last_backup_row = db.conn.execute(
        "SELECT MAX(finished_at) FROM jobs WHERE status='SUCCESS' AND action='BACKUP'"
    ).fetchone()
    last_backup = last_backup_row[0] if last_backup_row else None

    # Total theoretical capacity across all registered tapes
    all_gen_rows = db.conn.execute("SELECT generation FROM tapes").fetchall()
    total_cap = sum(
        cfg.get_generation_info(g[0]).get("capacity", 0)
        for g in all_gen_rows
    )

    summary = {
        "tape_count":    tape_count,
        "total_used_tb": total_used / 1024 ** 4,
        "total_cap_tb":  total_cap  / 1024 ** 4,
        "failed_jobs":   failed_jobs,
        "last_backup":   last_backup,
        "generated_at":  now.strftime("%Y-%m-%d %H:%M UTC"),
    }

    tapes_data = _collect_tape_data(db, now)
    html = _render_html(summary, tapes_data)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path


def health_report_workflow(db):
    """Interactive wrapper — asks for output path then generates the report."""
    header("📋 Health Report")

    default_path = "health_report.html"
    raw = input(f"Save report to [{default_path}]: ").strip()
    output_path = raw if raw else default_path

    console.print("[dim]Generating report…[/]")
    try:
        path = generate_health_report(db, output_path)
        abs_path = os.path.abspath(path)
        console.print(f"\n[green]✅ Report saved to:[/]  {abs_path}")
    except Exception as e:
        console.print(f"[red]Error generating report: {e}[/]")

    wait_for_keypress()
