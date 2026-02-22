#!/usr/bin/env python3
"""Generate architecture flow diagrams from canonical backend config."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings, app_config  # noqa: E402


def _incident_flow_dot(settings: Settings) -> str:
    return f"""digraph IncidentFlow {{
  rankdir=LR;
  splines=ortho;
  nodesep=0.55;
  ranksep=0.8;
  graph [fontname="Helvetica", fontsize=10, bgcolor="transparent"];
  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10, color="#3a4d73", fillcolor="#13203a", fontcolor="#e4ebfb"];
  edge [color="#6f86b3", penwidth=1.1, arrowsize=0.8];

  ingest [label="POST /api/v1/events\\nPersist event + update rolling 60s"];
  baseline [label="Baseline update gate\\nIf matching OPEN incident exists\\n=> baseline frozen"];
  detect [label="Anomaly compare\\nreq_ratio/tok_ratio vs baseline\\nlow>={app_config.incident_severity_ratio_low}\\nmedium>={app_config.incident_severity_ratio_medium}\\nhigh>={app_config.incident_severity_ratio_high}"];
  dedup [label="Dedup window\\nincident_dedup_window_seconds={settings.incident_dedup_window_seconds}\\nOpen+fingerprint hit => update evidence/count"];
  create [label="Create incident\\nstatus=open\\nseverity from ratio"];
  escalate [label="Escalation (open only)\\nlow->medium/high or medium->high\\nwm={settings.incident_escalation_window_medium_seconds}s\\nwh={settings.incident_escalation_window_high_seconds}s\\nmin_hits_m={settings.incident_escalation_min_hits_medium}, min_hits_h={settings.incident_escalation_min_hits_high}\\nscore_m>={settings.incident_escalation_score_threshold_medium}, score_h>={settings.incident_escalation_score_threshold_high}\\n10x guard score={app_config.incident_escalation_high_score_required}"];
  keep_open [label="Incident remains open\\nlast_seen_at refreshed", fillcolor="#172946", color="#4d6f9b"];
  auto_close [label="Auto-close worker\\nstatus=open and last_seen_at older than\\nINCIDENT_AUTO_CLOSE_SECONDS={settings.incident_auto_close_seconds}\\n=> status=auto_resolved", fillcolor="#1f2a44", color="#5f78a3"];
  resolved [label="Statuses\\nopen -> auto_resolved\\n(or manually resolved)", fillcolor="#20304f", color="#607ba8"];

  ingest -> baseline -> detect -> dedup;
  dedup -> create [label="no open match"];
  dedup -> escalate [label="open match"];
  create -> keep_open;
  escalate -> keep_open;
  keep_open -> auto_close;
  auto_close -> resolved;
}}"""


def _protect_flow_dot(settings: Settings) -> str:
    return f"""digraph ProtectDecisionFlow {{
  rankdir=LR;
  splines=ortho;
  nodesep=0.55;
  ranksep=0.85;
  graph [fontname="Helvetica", fontsize=10, bgcolor="transparent"];
  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10, color="#3f516f", fillcolor="#141f34", fontcolor="#e4ebfb"];
  edge [color="#6f86b3", penwidth=1.1, arrowsize=0.8];

  start [label="POST /api/v1/protect/decision"];
  mode [label="protect_enabled?"];
  allow_off [label="allow\\nreason=ok", fillcolor="#173525", color="#3f8c62", fontcolor="#dcfce7"];
  cooldown [label="cooldown key exists + active?\\nprotect_block_cooldown_seconds={settings.protect_block_cooldown_seconds}"];
  block_cooldown [label="block\\nreason=cooldown_active\\ninclude retry_after_seconds", fillcolor="#3d1b26", color="#87445d", fontcolor="#ffd9e2"];
  req_cap [label="requests_60s >= protect_max_req_per_min?"];
  block_req [label="block\\nreason=req_limit\\nset cooldown key", fillcolor="#3d1b26", color="#87445d", fontcolor="#ffd9e2"];
  tok_cap [label="tokens_60s >= protect_max_tok_per_min?"];
  block_tok [label="block\\nreason=tok_limit\\nset cooldown key", fillcolor="#3d1b26", color="#87445d", fontcolor="#ffd9e2"];
  sev_high [label="incident severity == high?"];
  block_high [label="block\\nreason=incident_high\\nset cooldown key", fillcolor="#3d1b26", color="#87445d", fontcolor="#ffd9e2"];
  sev_medium [label="incident severity == medium?"];
  warn_medium [label="warn\\nreason=incident_medium", fillcolor="#3e341e", color="#9f8140", fontcolor="#fff0c9"];
  predictive [label="predictive near-cap check\\nif protect_max_tok_per_min set\\nand estimated_next_tokens present\\nnear_cap_factor={app_config.protect_near_cap_factor}"];
  warn_predictive [label="warn\\nreason=predictive_near_cap\\n(warn only, no predictive block)", fillcolor="#3e341e", color="#9f8140", fontcolor="#fff0c9"];
  allow [label="allow\\nreason=ok", fillcolor="#173525", color="#3f8c62", fontcolor="#dcfce7"];
  sdk [label="SDK enforcement (Node/Python)\\nallow/warn => provider call\\nblock => LLMTBGBlockedError\\nfail-open/fail-closed on timeout/error", fillcolor="#1b3140", color="#4f7f99"];

  start -> mode;
  mode -> allow_off [label="no"];
  mode -> cooldown [label="yes"];
  cooldown -> block_cooldown [label="yes"];
  cooldown -> req_cap [label="no"];
  req_cap -> block_req [label="yes"];
  req_cap -> tok_cap [label="no"];
  tok_cap -> block_tok [label="yes"];
  tok_cap -> sev_high [label="no"];
  sev_high -> block_high [label="yes"];
  sev_high -> sev_medium [label="no"];
  sev_medium -> warn_medium [label="yes"];
  sev_medium -> predictive [label="no"];
  predictive -> warn_predictive [label="near-cap met"];
  predictive -> allow [label="else"];

  allow_off -> sdk;
  block_cooldown -> sdk;
  block_req -> sdk;
  block_tok -> sdk;
  block_high -> sdk;
  warn_medium -> sdk;
  warn_predictive -> sdk;
  allow -> sdk;
}}"""


def _render_svg(dot_path: Path, svg_path: Path) -> None:
    dot_bin = shutil.which("dot")
    if dot_bin is None:
        raise RuntimeError("Graphviz 'dot' is required to generate diagrams. Install graphviz and retry.")
    subprocess.run([dot_bin, "-Tsvg", str(dot_path), "-o", str(svg_path)], check=True)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")


def _copy_svg(svg_path: Path, public_path: Path) -> None:
    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(svg_path.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> None:
    settings = Settings()
    docs_arch_dir = REPO_ROOT / "docs" / "architecture"
    public_arch_dir = REPO_ROOT / "frontend" / "public" / "architecture"

    incident_dot_path = docs_arch_dir / "incident_flow.dot"
    protect_dot_path = docs_arch_dir / "protect_decision_flow.dot"
    incident_svg_path = docs_arch_dir / "incident_flow.svg"
    protect_svg_path = docs_arch_dir / "protect_decision_flow.svg"

    _write_text(incident_dot_path, _incident_flow_dot(settings))
    _write_text(protect_dot_path, _protect_flow_dot(settings))
    _render_svg(incident_dot_path, incident_svg_path)
    _render_svg(protect_dot_path, protect_svg_path)
    _copy_svg(incident_svg_path, public_arch_dir / "incident_flow.svg")
    _copy_svg(protect_svg_path, public_arch_dir / "protect_decision_flow.svg")


if __name__ == "__main__":
    main()
