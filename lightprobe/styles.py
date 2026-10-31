"""Author style settings (POV, genre lens S01–S18, density), chapter-range helpers and the engine
state machine."""

from __future__ import annotations

import json
from functools import lru_cache

from .config import CARDS_DIR, DEFAULT_MODEL

# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

STAGES: list[tuple[str, str]] = [
    ("SORTING_MODE", "1. Ingestion"),
    ("INGESTION_REVIEW", "2. Review Intake"),
    ("BIBLE_REVIEW", "3. Universe Bible"),
    ("STYLE_LAB", "4. Author Style"),
    ("BIN_REVIEW", "5. Volume Bins"),
    ("GAP_REVIEW", "6. Gap-Fill"),
    ("OUTLINE_REVIEW", "7. Volume Outline"),
    ("FORESHADOWING_MODE", "8. Payoff Planner"),
    ("WRITING_MODE", "9. Novel Writing"),
    ("CHAPTER_REVIEW", "9b. Review Pass"),
    ("HANDOFF_MODE", "10. Continuity Handoff"),
    ("COMPLETED", "11. Complete"),
]
STATE_ORDER = [s for s, _ in STAGES]
STAGE_LABEL = dict(STAGES)
WRITING_LOOP_STATES = ["WRITING_MODE", "CHAPTER_REVIEW", "HANDOFF_MODE", "COMPLETED"]

MODES = {"SLOW_BURN_MODE": "Slow Burn Mode", "RUSH_MODE": "Rush Mode"}
RUSH_CHAPTER_RANGE = (40, 100)

# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------

POV_MODES = {
    "THIRD_LIMITED": "Third-Person Limited",
    "FIRST_PERSON_SOUL": "First-Person Soul (LNF-LP1)",
    "TESTIMONY_MEMOIR": "Testimony / Memoir (LNF-06)",
}
DENSITIES = {
    "EXTENSIVE_NOVEL": "Extensive Novel",
    "BALANCED": "Balanced",
    "ATMOSPHERIC_DEEP_DIVE": "Atmospheric Deep Dive",
}
SENSORY = {
    "ALL_SENSES": "All senses",
    "TACTILE_AND_ACOUSTIC": "Tactile & acoustic",
    "VISCERAL_BODY": "Visceral body",
    "ATMOSPHERIC_PRESSURE": "Atmospheric pressure",
}


@lru_cache(maxsize=1)
def genre_presets() -> list[dict]:
    return json.loads((CARDS_DIR / "genre_presets.json").read_text(encoding="utf-8"))


def default_style_config() -> dict:
    return {
        "povMode": "THIRD_LIMITED",
        "genreLens": "DYNAMIC_PROBE_DETECT",
        "proseDensity": "EXTENSIVE_NOVEL",
        "pacingFluctuation": True,
        "sensoryPriority": "ALL_SENSES",
        "showDontTellStrictness": "STRICT_ZERO_TELLING",
        "customStyleNotes": "",
    }


def default_models() -> dict:
    return {"planning": DEFAULT_MODEL, "writing": DEFAULT_MODEL}


def format_style_prompt(style: dict | None) -> str:
    cfg = {**default_style_config(), **(style or {})}
    preset = next((g for g in genre_presets() if g["id"] == cfg["genreLens"]), None)
    pov = cfg["povMode"]
    if pov == "FIRST_PERSON_SOUL":
        pov_text = ("FIRST-PERSON DEEP DIVE (LNF-LP1) - Narrate from directly inside the focal soul, transmitting "
                    "their real-time interiority, sensory biases, and blind spots.")
    elif pov == "TESTIMONY_MEMOIR":
        pov_text = "TESTIMONY / MEMOIR (LNF-06) - Structured lived testimony, documentary gravity, concrete material evidence."
    else:
        pov_text = "THIRD-PERSON LIMITED - Deeply anchored to the focal soul’s physical sensory horizon. Never jump heads."
    density = cfg["proseDensity"]
    if density == "ATMOSPHERIC_DEEP_DIVE":
        density_text = "Deep Atmospheric Slow-Burn - Dense, deliberate, rich sensory texture with heavy environmental acoustics."
    elif density == "BALANCED":
        density_text = "Balanced Narrative Momentum - Dynamic scene rhythm with visceral impact."
    else:
        density_text = ("Extensive Novel Style - Expansive micro-beats, fully fleshed-out scenes with tactile grounding, "
                        "dialogue with pauses and body actions, NEVER condensed summaries.")
    pacing = ("ENABLED. Dynamic chapter length and flow. Heavy climactic and atmospheric beats must be extensive, deep-dive "
              "chapters; kinetic pivots must deliver rapid, staccato impact." if cfg["pacingFluctuation"]
              else "Standard steady pacing across all chapters.")
    lines = [
        "=== LOCKED AUTHOR STYLE & VOICE DNA (MANDATORY STANDING MATRIX) ===",
        f"1. POV MODE: {pov_text}",
        f"2. PRIMARY GENRE LENS: {preset['label'] + ': ' + preset['description'] if preset else 'Dynamic Moment Detection (S01-S18)'}",
        f"3. PROSE DENSITY & EXTENSIVE NOVEL FLOW: {density_text}",
        f"4. PACING FLUCTUATION: {pacing}",
        f"5. SENSORY PRIORITY: {cfg['sensoryPriority']} (Physical temperature, ambient acoustics, tactile resistance, air pressure, bodily reactions).",
        f"6. SHOW-DON'T-TELL ENFORCEMENT: {cfg['showDontTellStrictness']} - ZERO emotional labeling (\"she was terrified\"). "
        "Only physical actions, nervous micro-gestures, and sensory realities.",
    ]
    if cfg.get("customStyleNotes"):
        lines.append(f"CUSTOM UNIVERSE STYLE NOTES:\n{cfg['customStyleNotes']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Chapters per volume
# ---------------------------------------------------------------------------

def clamp_chapters(n: int | float | None, rng: dict | None) -> int:
    """Keeps a chapter count inside the author's range (empty bounds are ignored)."""
    out = max(1, round(n or 1))
    if rng and rng.get("min"):
        out = max(out, int(rng["min"]))
    if rng and rng.get("max"):
        out = min(out, int(rng["max"]))
    return out


def describe_chapter_range(rng: dict | None) -> str:
    lo, hi = (rng or {}).get("min"), (rng or {}).get("max")
    if not lo and not hi:
        return ""
    if lo and hi:
        return f"{lo}-{hi} chapters per volume"
    return f"at least {lo} chapters per volume" if lo else f"at most {hi} chapters per volume"
