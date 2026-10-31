"""STAGE 8 — Payoff & foreshadowing (Card 06-MULTI-QUADRANT). Author-implied threads are marked AUTHOR,
planner additions INFERRED. Every seed must point at a chapter that exists in the outline; one
correction retry fixes threads that do not, and any still invalid are dropped (and reported) rather
than silently never planted."""

from __future__ import annotations

from .. import storage
from ..ai import planning_model
from ..ai.planning import generate_payoff_plan
from .common import Progress, no_progress
from .outline import volume_material


def payoff_context(name: str, state: dict) -> str:
    store = storage.get_sorted_material(name)
    return "\n\n".join(
        f"--- VOLUME {v['volumeNumber']}: {v['title']}{' (FINISHED - already written by the author)' if v.get('pinnedFrom') else ''} ---\n"
        f"Premise: {v['premise']}\n\n" +
        "\n".join(f"Ch {c['chapterNumber']}: {c['title']} - {c['synopsis']}" for c in v["chapters"]) +
        f"\n\nBinned author material:\n{volume_material(state, v, store, verbatim=False) or '(none)'}"
        for v in state["plan"]["volumes"])


def run_payoff(name: str, state: dict, progress: Progress = no_progress) -> dict:
    plan = state.get("plan")
    if not plan:
        raise ValueError("Approve the volume outline first.")
    progress("Reading every volume's outline and material to design the setups and payoffs...", 10)
    counts = {v["volumeNumber"]: len(v["chapters"]) for v in plan["volumes"]}
    finished = frozenset(v["volumeNumber"] for v in plan["volumes"] if v.get("pinnedFrom"))
    result = generate_payoff_plan(plan.get("universeSummary", ""), payoff_context(name, state), storage.standing_cards(name), counts, planning_model(state),
                                  finished=finished)
    state["payoffPlan"] = result
    storage.save_state(name, state)
    dropped = result.get("dropped", 0)
    progress(f"{len(result['payoffs'])} foreshadowing threads planned" + (f" ({dropped} dropped: they pointed at chapters that do not exist)" if dropped else "") + ".", 100)
    return state


def seed_status_report(state: dict) -> str:
    vol = state["currentVolume"]
    lines = []
    for p in (state.get("payoffPlan") or {}).get("payoffs") or []:
        if p["setupVolume"] <= vol <= p["payoffVolume"]:
            when = (f"PENDING payoff Vol {p['payoffVolume']} Ch {p['payoffChapterNumber']}" if p["payoffVolume"] > vol
                    else f"PAYS OFF this volume (Ch {p['payoffChapterNumber']})")
            lines.append(f"- [{p['threadName']}] planted Vol {p['setupVolume']} Ch {p['setupChapterNumber']}: {p['setupDescription']}\n  {when}: {p['payoffDescription']}")
    return "\n".join(lines)


def approve_payoff(name: str, state: dict) -> dict:
    plan = state.get("payoffPlan")
    if not plan:
        raise ValueError("No payoff plan to approve.")
    mode = state["mode"]
    total = state["totalVolumes"]
    # Human-readable copies; the writer reads seeds from state, per chapter, setup only
    for v in range(1, total + 1):
        for f in storage.list_memory(name, mode, v):
            if f.startswith("payoff_seed_"):
                storage.delete_memory(name, mode, v, f)
    for p in plan["payoffs"]:
        if p["setupVolume"] <= total:
            storage.write_memory(name, mode, p["setupVolume"], f"payoff_seed_{p['id']}.txt",
                                 f"=== FORESHADOWING SEED ({p['origin']}) ===\nThread: {p['threadName']}\nPlant: Volume {p['setupVolume']}, Chapter {p['setupChapterNumber']}\n"
                                 f"{p['setupDescription']}\n\nPayoff: Volume {p['payoffVolume']}, Chapter {p['payoffChapterNumber']}\n{p['payoffDescription']}\n\nImpact: {p['narrativeImpact']}\n")
    master = f"=== MASTER PAYOFF ARCHITECTURE ===\nOverall Strategy:\n{plan['overallStrategy']}\n\n" + "\n\n".join(
        f"{i + 1}. [{p['threadName']}] ({p['origin']})\nPlant Vol {p['setupVolume']} Ch {p['setupChapterNumber']}: {p['setupDescription']}\n"
        f"Payoff Vol {p['payoffVolume']} Ch {p['payoffChapterNumber']}: {p['payoffDescription']}\nImpact: {p['narrativeImpact']}" for i, p in enumerate(plan["payoffs"]))
    for v in range(1, total + 1):
        storage.write_memory(name, mode, v, "master_payoff_plan.txt", master)
    state["status"] = "WRITING_MODE"
    state["chaptersInCurrentPass"] = 0
    storage.save_state(name, state)
    return state
