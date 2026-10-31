"""STAGE 4 — Style Lab. The creators test candidate author styles until one is right, then lock it.

Candidates: the author's own Voice DNA (from their prose; events-only files never teach the voice),
a polished version of it, and distinct unique voices for this universe. Each has a test passage of
the SAME scene. Locking writes 03-AUTHOR-VOICE-DNA.md and 01-AUTHOR-STYLE-REMINDER.md (generated
files; the client's 03-AUTHOR-VOICE.md card is never overwritten) and the style lock.
"""

from __future__ import annotations

from .. import storage
from ..ai import planning_model, writing_model
from ..ai.style import extract_author_voice_dna, format_dna_doc, propose_style_variants, refine_style, write_style_sample
from ..styles import format_style_prompt
from .common import Progress, is_events_only, no_progress, read_canon, source_file

VOICE_SAMPLE_BUDGET = 80000
CANDIDATE_COUNT = 3


def pick_voice_samples(name: str, state: dict) -> list[str]:
    """The author's verbatim narrative prose: voice samples first, then the longest draft passages."""
    store = storage.get_sorted_material(name)
    usable = [it for it in store["items"].values()
              if it.get("verbatim") and len(it["text"]) > 200 and not is_events_only(state, source_file(it["source"]))]
    voice = sorted((it for it in usable if it["kind"] == "VOICE_SAMPLE"), key=lambda x: len(x["text"]), reverse=True)
    drafts = [] if len(voice) >= 3 else sorted((it for it in usable if it["kind"] == "CHAPTER_MATERIAL"), key=lambda x: len(x["text"]), reverse=True)
    out, budget = [], VOICE_SAMPLE_BUDGET
    for it in voice + drafts:
        text = it["text"][:15000]
        budget -= len(text)
        if budget < 0:
            break
        out.append(text)
    return out


def universe_brief(state: dict) -> str:
    bible = state.get("universeBible") or {}
    souls = ((state.get("soulRoster") or {}).get("souls") or [])[:12]
    return "\n".join([
        f"Core premise: {bible.get('corePremise', '')}",
        f"Civilizational model: {bible.get('civilizationalModel', '')}",
        "Main characters:\n" + "\n".join(f"- {s['name']}: {s.get('essence', '')}" for s in souls),
        "Themes: " + "; ".join((bible.get("themes") or [])[:10]),
    ])


def default_scene_brief(state: dict) -> str:
    beats = (state.get("messSortResult") or {}).get("arcBeats") or []
    if not beats:
        return "An ordinary morning for the main character, the day before everything changes."
    b = beats[0]
    return f"{b['event']} (what changes: {b['irreversibleChange']})"


def _lab(state: dict) -> dict:
    lab = state.get("styleLab") or {}
    lab.setdefault("candidates", [])
    lab.setdefault("creatorNotes", "")
    lab.setdefault("sceneBrief", default_scene_brief(state))
    lab.setdefault("lockedId", None)
    state["styleLab"] = lab
    return lab


def _write_sample(name: str, state: dict, cand: dict, scene: str) -> None:
    rules = "\n\n".join(x for x in (storage.read_core(name, "03-AUTHOR-VOICE.md"), storage.read_core(name, "04-NO-DRIFT-NO-SLOP.md"),
                                    format_style_prompt(state.get("styleConfig"))) if x)
    cand["sample"] = write_style_sample(cand, scene, read_canon(name), rules, writing_model(state))
    cand["sampleScene"] = scene
    d = storage.universe_dir(name) / "STYLE_LAB"
    d.mkdir(exist_ok=True)
    (d / f"{cand['id']}.md").write_text(f"# {cand['name']}\n\n{cand.get('pitch', '')}\n\n## Test passage\n\n{cand['sample']}", encoding="utf-8")


def run_style_lab(name: str, state: dict, progress: Progress = no_progress, scene_brief: str | None = None, notes: str | None = None) -> dict:
    """Generates a fresh set of candidates (replacing unlocked ones) with test passages."""
    if not state.get("universeBible"):
        raise ValueError("Build the Universe Bible first.")
    lab = _lab(state)
    if scene_brief is not None and scene_brief.strip():
        lab["sceneBrief"] = scene_brief.strip()
    if notes is not None:
        lab["creatorNotes"] = notes
    model = planning_model(state)
    candidates: list[dict] = []
    samples = pick_voice_samples(name, state)
    author_dna = None
    if samples:
        progress(f"Extracting the author's Voice DNA from {len(samples)} samples of their own prose...", 5)
        author_dna = extract_author_voice_dna(samples, (state.get("universeBible") or {}).get("corePremise", ""), model)
        candidates.append({**author_dna, "name": "Author's Own Voice", "pitch": "Extracted from the author's own prose.", "origin": "AUTHOR"})
    else:
        progress("No usable prose samples of the author's own voice (events-only files are excluded) - designing unique voices.", 5)
    variant_count = CANDIDATE_COUNT - len(candidates)
    progress(f"Designing {variant_count} style candidates for this universe...", 20)
    variants = propose_style_variants(author_dna, universe_brief(state), storage.read_core(name, "03-AUTHOR-VOICE.md"),
                                      lab["creatorNotes"], variant_count, model)
    for i, v in enumerate(variants):
        candidates.append({**v, "origin": "POLISHED" if author_dna and i == 0 else "UNIQUE"})
    used = {c["id"] for c in lab["candidates"]}
    next_id = 1
    for c in candidates:
        while f"S{next_id}" in used:
            next_id += 1
        c["id"] = f"S{next_id}"
        used.add(c["id"])
        c["history"] = []
        c["sample"] = ""
    # Keep any candidate the creators already locked; replace the rest. Saved now, so a stop while the test
    # passages are written keeps every candidate and every passage already written.
    lab["candidates"] = [c for c in lab["candidates"] if c["id"] == lab.get("lockedId")] + candidates
    storage.save_state(name, state)
    for i, c in enumerate(candidates):
        progress(f'Writing the test passage for "{c["name"]}" ({i + 1}/{len(candidates)})...', 35 + round(i / len(candidates) * 60))
        _write_sample(name, state, c, lab["sceneBrief"])
        storage.save_state(name, state)
    progress(f"{len(candidates)} style candidates ready. Compare the test passages, refine, and lock one.", 100)
    return state


def refine_candidate(name: str, state: dict, cand_id: str, feedback: str, progress: Progress = no_progress) -> dict:
    lab = _lab(state)
    cand = next((c for c in lab["candidates"] if c["id"] == cand_id), None)
    if not cand:
        raise ValueError(f"Style candidate {cand_id} not found.")
    if not feedback.strip():
        raise ValueError("Write what should change first.")
    progress(f'Revising "{cand["name"]}" from your feedback...', 10)
    revised = refine_style(cand, feedback, universe_brief(state), planning_model(state))
    history = cand.get("history", []) + [{"feedback": feedback, "previous": {k: cand.get(k) for k in ("name", "overallVoiceSummary")}}]
    cand.update({k: v for k, v in revised.items() if v}, history=history)
    progress("Writing the new test passage...", 50)
    _write_sample(name, state, cand, lab["sceneBrief"])
    storage.save_state(name, state)
    progress(f'"{cand["name"]}" revised.', 100)
    return state


def rewrite_samples(name: str, state: dict, scene_brief: str, progress: Progress = no_progress) -> dict:
    """Re-tests every candidate on a new scene."""
    lab = _lab(state)
    lab["sceneBrief"] = scene_brief.strip() or default_scene_brief(state)
    for i, c in enumerate(lab["candidates"]):
        progress(f'Writing the test passage for "{c["name"]}" ({i + 1}/{len(lab["candidates"])})...', round(i / max(1, len(lab["candidates"])) * 95))
        _write_sample(name, state, c, lab["sceneBrief"])
        storage.save_state(name, state)
    progress("Test passages rewritten on the new scene.", 100)
    return state


def set_notes(name: str, state: dict, notes: str) -> dict:
    """Creator notes applied to every new or refined candidate (e.g. "less telling")."""
    _lab(state)["creatorNotes"] = notes
    storage.save_state(name, state)
    return state


def lock_style(name: str, state: dict, cand_id: str) -> dict:
    """Approval action: locks the chosen voice for every chapter and volume, and opens Volume Bins."""
    lab = _lab(state)
    cand = next((c for c in lab["candidates"] if c["id"] == cand_id), None)
    if not cand:
        raise ValueError(f"Style candidate {cand_id} not found.")
    lab["lockedId"] = cand_id
    origin = {"AUTHOR": "extracted from the author's own prose", "POLISHED": "the author's voice, polished in the Style Lab"}.get(
        cand.get("origin"), "designed in the Style Lab")
    storage.write_core(name, "03-AUTHOR-VOICE-DNA.md", format_dna_doc(cand, f"{cand['name']} - {origin}; locked by the creators"))
    storage.write_core(name, "01-AUTHOR-STYLE-REMINDER.md",
                       f"# 01-AUTHOR-STYLE-REMINDER (re-read before every chapter)\n\n{cand.get('overallVoiceSummary', '')}\n\nNEVER: {cand.get('neverDoes', '')}")
    storage.write_core(name, "01-AUTHOR-STYLE-LOCK.md", f"# 01-AUTHOR-STYLE-LOCK\n{format_style_prompt(state.get('styleConfig'))}")
    state["status"] = "BIN_REVIEW"
    storage.save_state(name, state)
    return state
