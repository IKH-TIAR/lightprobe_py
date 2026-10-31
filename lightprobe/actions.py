"""Every pipeline action, with the stage gates. The creators are a required step in the loop: each stage
is entered only through its approval action, and an action runs only in the stages listed for it.

`dispatch` runs quick actions immediately and starts model-calling actions as background jobs."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Callable

from . import jobs, storage
from .pipeline import bible, bins, gaps, ingest, outline, payoff, style_lab, writing
from .styles import STATE_ORDER, WRITING_LOOP_STATES, format_style_prompt

ANY = None
WRITING_STATES = ["FORESHADOWING_MODE", "WRITING_MODE", "CHAPTER_REVIEW", "HANDOFF_MODE"]


@dataclass
class Action:
    gates: list[str] | None
    fn: Callable
    job_label: str | None = None   # set = runs as a background job


def _p(payload: dict, key: str, default=None):
    return (payload or {}).get(key, default)


# --- quick actions that are not part of a pipeline module --------------------------------------

def _update_settings(name: str, state: dict, payload: dict) -> dict:
    if "targetVolumes" in payload:
        tv = payload["targetVolumes"]
        state["targetVolumes"] = int(tv) if tv not in (None, "", 0) else None
    if "chapterRange" in payload:
        rng = payload["chapterRange"] or {}
        state["chapterRange"] = {k: (int(rng[k]) if rng.get(k) not in (None, "", 0) else None) for k in ("min", "max")}
    if "volumePins" in payload:
        state["volumePins"] = {f: int(v) for f, v in (payload["volumePins"] or {}).items() if v not in (None, "", 0)}
    if "messFileSettings" in payload:
        state["messFileSettings"] = payload["messFileSettings"] or {}
    if "models" in payload:
        state["models"] = {**state["models"], **payload["models"]}
    if "styleConfig" in payload:
        state["styleConfig"] = {**state["styleConfig"], **payload["styleConfig"]}
        storage.write_core(name, "01-AUTHOR-STYLE-LOCK.md", f"# 01-AUTHOR-STYLE-LOCK\n{format_style_prompt(state['styleConfig'])}")
    bins.validate_settings(state)
    storage.save_state(name, state)
    return state


def _set_status(name: str, state: dict, payload: dict) -> dict:
    target = _p(payload, "status")
    if target not in STATE_ORDER:
        raise ValueError(f"Unknown stage {target}.")
    if target == state["status"]:
        return state
    if target in WRITING_LOOP_STATES:
        if target != state.get("resumeStatus"):
            raise ValueError("The writing stages are reached through their approval steps, not by navigation.")
        state["resumeStatus"] = None
    else:
        if STATE_ORDER.index(target) > STATE_ORDER.index(state.get("furthestStatus") or state["status"]):
            raise ValueError("Complete the earlier stages before opening this one.")
        if state["status"] in WRITING_LOOP_STATES:
            state["resumeStatus"] = state["status"]
    state["status"] = target
    storage.save_state(name, state)
    return state


def _approve(next_status: str, check: Callable[[dict], str | None] = lambda s: None):
    def fn(name: str, state: dict, payload: dict) -> dict:
        problem = check(state)
        if problem:
            raise ValueError(problem)
        state["status"] = next_status
        storage.save_state(name, state)
        return state
    return fn


def spawn_parallel_track(name: str, state: dict, payload: dict) -> dict:
    """Creates the other mode's track from the same sorted intake, Bible, roster and locked style, so it
    starts at Volume Bins instead of re-sorting."""
    other = "RUSH_MODE" if state["mode"] == "SLOW_BURN_MODE" else "SLOW_BURN_MODE"
    new_name = storage.safe_name(f"{name}_{'Rush' if other == 'RUSH_MODE' else 'SlowBurn'}")
    if storage.universe_dir(new_name).exists():
        raise ValueError(f'"{new_name}" already exists.')
    src, dst = storage.universe_dir(name), storage.universe_dir(new_name)
    dst.mkdir(parents=True)
    for sub in ("MESS", "SORTED", "SHARED_CORE_KNOWLEDGE", "STYLE_LAB"):
        if (src / sub).exists():
            shutil.copytree(src / sub, dst / sub)
    new = storage.new_state(new_name, other, state["styleConfig"], state["models"])
    for k in ("messSortResult", "universeBible", "soulRoster", "styleLab", "targetVolumes", "chapterRange", "volumePins", "messFileSettings"):
        new[k] = state.get(k)
    new["status"] = new["furthestStatus"] = "BIN_REVIEW" if state.get("styleLab", {}) and state["styleLab"].get("lockedId") else "BIBLE_REVIEW"
    storage.save_state(new_name, new)
    state["parallelTrack"] = new_name
    storage.save_state(name, state)
    return state


ACTIONS: dict[str, Action] = {
    # Settings and navigation
    "UPDATE_SETTINGS": Action(ANY, _update_settings),
    "SET_STATUS": Action(ANY, _set_status),
    "SPAWN_PARALLEL_TRACK": Action(["BIN_REVIEW", "GAP_REVIEW", "OUTLINE_REVIEW", *WRITING_STATES, "COMPLETED"], spawn_parallel_track),
    # 1-2 Intake
    "INGEST": Action(["SORTING_MODE", "INGESTION_REVIEW"], lambda n, s, p, pr: ingest.run_ingestion(n, s, bool(_p(p, "fresh")), pr), "MESS sort"),
    "RESOLVE_UNCLEAR": Action(["INGESTION_REVIEW", "BIBLE_REVIEW"], lambda n, s, p, pr: ingest.run_resolve_unclear(n, s, pr), "Checking flagged items"),
    "ANSWER_UNCLEAR": Action(["INGESTION_REVIEW", "BIBLE_REVIEW", "STYLE_LAB", "BIN_REVIEW", "GAP_REVIEW", "OUTLINE_REVIEW"],
                             lambda n, s, p: ingest.answer_unclear(n, s, _p(p, "answers", {}))),
    "APPROVE_INGESTION": Action(["INGESTION_REVIEW"], _approve("BIBLE_REVIEW", lambda s: None if (s.get("messSortResult") or {}).get("complete") else "The MESS sort has not finished.")),
    # 3 Bible
    "GENERATE_BIBLE": Action(["INGESTION_REVIEW", "BIBLE_REVIEW"], lambda n, s, p, pr: bible.run_bible(n, s, pr), "Universe Bible"),
    "REPAIR_SOULS": Action(["BIBLE_REVIEW"], lambda n, s, p, pr: bible.repair_souls(n, s, _p(p, "entries"), pr), "Character repair"),
    "APPROVE_BIBLE": Action(["BIBLE_REVIEW"], _approve("STYLE_LAB", lambda s: None if s.get("soulRoster") else "Build the Universe Bible and Soul Roster first.")),
    # 4 Style Lab
    "STYLE_GENERATE": Action(["STYLE_LAB"], lambda n, s, p, pr: style_lab.run_style_lab(n, s, pr, _p(p, "sceneBrief"), _p(p, "notes")), "Style Lab"),
    "STYLE_REFINE": Action(["STYLE_LAB"], lambda n, s, p, pr: style_lab.refine_candidate(n, s, _p(p, "id"), _p(p, "feedback", ""), pr), "Refining style"),
    "STYLE_RESAMPLE": Action(["STYLE_LAB"], lambda n, s, p, pr: style_lab.rewrite_samples(n, s, _p(p, "sceneBrief", ""), pr), "New test scene"),
    "STYLE_SET_NOTES": Action(["STYLE_LAB"], lambda n, s, p: style_lab.set_notes(n, s, _p(p, "notes", ""))),
    "STYLE_LOCK": Action(["STYLE_LAB"], lambda n, s, p: style_lab.lock_style(n, s, _p(p, "id"))),
    # 5 Volume bins
    "BUILD_BINS": Action(["BIN_REVIEW"], lambda n, s, p, pr: bins.run_bins(n, s, pr), "Volume bins"),
    "MOVE_ITEM": Action(["BIN_REVIEW"], lambda n, s, p: bins.move_item(n, s, _p(p, "id"), _p(p, "toVolume"))),
    "EDIT_VOLUME": Action(["BIN_REVIEW"], lambda n, s, p: bins.edit_volume(n, s, int(_p(p, "volume")), _p(p, "title", ""), _p(p, "premise", ""), _p(p, "summary", ""))),
    "APPROVE_BINS": Action(["BIN_REVIEW"], lambda n, s, p: bins.approve_bins(n, s)),
    # 6 Gap-fill
    "GAP_RUN": Action(["GAP_REVIEW"], lambda n, s, p, pr: gaps.run_gap_fill(n, s, _p(p, "volumes"), bool(_p(p, "includeFinished")), pr), "Gap-fill"),
    "GAP_SET_STATUS": Action(["GAP_REVIEW"], lambda n, s, p: gaps.set_event_status(n, s, int(_p(p, "volume")), _p(p, "id"), _p(p, "status"))),
    "GAP_EDIT": Action(["GAP_REVIEW"], lambda n, s, p: gaps.edit_event(n, s, int(_p(p, "volume")), _p(p, "id"), _p(p, "fields", {}))),
    "GAP_ADD": Action(["GAP_REVIEW"], lambda n, s, p: gaps.add_event(n, s, int(_p(p, "volume")), _p(p, "fields", {}))),
    "GAP_ANSWER": Action(["GAP_REVIEW"], lambda n, s, p: gaps.answer_question(n, s, int(_p(p, "volume")), _p(p, "id"), _p(p, "answer", ""))),
    "GAP_NOTES": Action(["GAP_REVIEW"], lambda n, s, p: gaps.set_notes(n, s, int(_p(p, "volume")), _p(p, "notes", ""))),
    "GAP_CONFIRM": Action(["GAP_REVIEW"], lambda n, s, p: gaps.confirm_volume(n, s, int(_p(p, "volume")), bool(_p(p, "acceptRemaining")))),
    "GAP_REOPEN": Action(["GAP_REVIEW"], lambda n, s, p: gaps.reopen_volume(n, s, int(_p(p, "volume")))),
    "APPROVE_GAPS": Action(["GAP_REVIEW"], lambda n, s, p: gaps.approve_gaps(n, s)),
    # 7 Outline
    "OUTLINE_RUN": Action(["OUTLINE_REVIEW"], lambda n, s, p, pr: outline.run_outline(n, s, bool(_p(p, "resume")), pr), "Volume outline"),
    "OUTLINE_VOLUME": Action(["OUTLINE_REVIEW"], lambda n, s, p, pr: outline.regenerate_volume_outline(n, s, int(_p(p, "volume")), pr), "Volume outline"),
    "APPROVE_PLAN": Action(["OUTLINE_REVIEW"], lambda n, s, p: outline.approve_plan(n, s)),
    # 8 Payoff
    "PAYOFF_RUN": Action(["FORESHADOWING_MODE"], lambda n, s, p, pr: payoff.run_payoff(n, s, pr), "Payoff planner"),
    "APPROVE_PAYOFF": Action(["FORESHADOWING_MODE"], lambda n, s, p: payoff.approve_payoff(n, s)),
    # 9-10 Writing
    "SET_START_VOLUME": Action(["FORESHADOWING_MODE", "WRITING_MODE"], lambda n, s, p: writing.set_start_volume(n, s, int(_p(p, "volume")))),
    "WRITE_CHAPTER": Action(["WRITING_MODE"], lambda n, s, p, pr: writing.generate_chapter(n, s, pr), "Writing chapter"),
    "SAVE_DRAFT": Action(["WRITING_MODE"], lambda n, s, p: writing.save_draft(n, s, _p(p, "title"), _p(p, "content"))),
    "DISCARD_DRAFT": Action(["WRITING_MODE"], lambda n, s, p: writing.discard_draft(n, s)),
    "ELEVATE_DRAFT": Action(["WRITING_MODE"], lambda n, s, p, pr: writing.elevate_draft(n, s, _p(p, "title", ""), _p(p, "content", ""), pr), "Elevating prose"),
    "APPROVE_PASS": Action(["CHAPTER_REVIEW"], lambda n, s, p: writing.approve_pass(n, s)),
    "RESET_VOLUME": Action(WRITING_STATES, lambda n, s, p: writing.reset_volume(n, s, int(_p(p, "volume")))),
    "KEEP_VOLUME_CHAPTERS": Action(WRITING_STATES, lambda n, s, p: writing.keep_volume_chapters(n, s, int(_p(p, "volume")))),
    "HANDOFF": Action(["HANDOFF_MODE"], lambda n, s, p, pr: writing.handoff(n, s, pr), "Volume handoff"),
    "SUBTLETY_AUDIT": Action(["WRITING_MODE", "CHAPTER_REVIEW", "HANDOFF_MODE"], lambda n, s, p, pr: writing.subtlety_audit(n, s, pr), "Subtlety audit"),
}


APPROVALS = {"APPROVE_INGESTION", "APPROVE_BIBLE", "STYLE_LOCK", "APPROVE_BINS", "APPROVE_GAPS", "APPROVE_PLAN", "APPROVE_PAYOFF"}


def allowed(action: str, state: dict) -> bool:
    a = ACTIONS.get(action)
    return bool(a) and (a.gates is None or state["status"] in a.gates)


def dispatch(name: str, action: str, payload: dict | None = None) -> dict | jobs.Job:
    """Quick actions return the new state; model-calling actions start a background job and return it."""
    a = ACTIONS.get(action)
    if not a:
        raise ValueError(f"Unknown action {action}.")
    if jobs.running(name):
        raise RuntimeError("A step is still running for this universe. Wait for it to finish (or stop it) first.")
    state = storage.load_state(name)
    if state is None:
        raise ValueError(f"Universe {name} not found.")
    if a.gates is not None and state["status"] not in a.gates:
        raise ValueError(f"This step is not available at this stage ({state['status']}).")
    if a.job_label:
        return jobs.start(name, action, a.job_label, lambda n, s, progress: a.fn(n, s, payload or {}, progress))
    result = a.fn(name, state, payload or {})
    if action in APPROVALS and result.get("resumeStatus"):
        # Passing a gate again means the stages after it are re-entered through their own gates
        result["resumeStatus"] = None
        storage.save_state(name, result)
    return result
