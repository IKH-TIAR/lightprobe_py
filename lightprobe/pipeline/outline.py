"""STAGE 7 — Chapter outlines, built per volume from its bin plus its confirmed mini-events, inside the
creators' chapters-per-volume range. Resumable: finished volumes are kept when a stopped run is
continued."""

from __future__ import annotations

from .. import storage
from ..ai import planning_model
from ..ai.planning import calibrate_chapter_counts, outline_volume
from ..styles import clamp_chapters, format_style_prompt
from .common import Progress, bin_text, invalidate_downstream, no_progress, read_canon
from .gaps import accepted_events, volume_gap


def format_volume_outline(vol: dict, current: int | None = None) -> str:
    chapters = "\n\n".join(
        f"{'>>> CURRENT CHAPTER >>> ' if current == c['chapterNumber'] else ''}Chapter {c['chapterNumber']}: {c['title']}\n"
        f"Pacing: {c.get('pacingType') or '-'} | Genre: {c.get('momentGenre') or '-'} | Focal: {c.get('focalSoul') or '-'} | Time: {c.get('timeCoordinate') or '-'}\n"
        f"Synopsis: {c['synopsis']}" + (f"\nSources: {', '.join(c['sourceRefs'])}" if c.get("sourceRefs") else "")
        for c in vol.get("chapters") or [])
    return f"Volume {vol['volumeNumber']}: {vol['title']}\nPremise: {vol['premise']}\nTarget Chapters: {vol['targetChapterCount']}\n\nChapters Outline:\n{chapters}"


def volume_material(state: dict, vol: dict, store: dict, verbatim: bool) -> str:
    """A volume's bin: the author's material, the confirmed mini-events and the creators' answers."""
    n = vol["volumeNumber"]
    text = bin_text(state, vol.get("sourceItemIds") or [], store, verbatim=verbatim, mini_events=accepted_events(state, n))
    answered = [q for q in volume_gap(state, n)["questions"] if (q.get("answer") or "").strip()]
    if answered:
        text += "\n\nCREATORS' ANSWERS FOR THIS VOLUME (canon):\n" + "\n".join(f"- Q: {q['question']}\n  A: {q['answer']}" for q in answered)
    return text


def _build_plan(state: dict) -> dict:
    bins = state["bins"]
    return {
        "universeSummary": bins.get("universeSummary", ""),
        "totalVolumes": len(bins["volumes"]),
        "volumes": [{
            "volumeNumber": v["volumeNumber"], "title": v["title"], "premise": v["premise"], "summary": v["summary"],
            "targetChapterCount": v["targetChapterCount"], "sourceItemIds": list(v["itemIds"]),
            "miniEventIds": [e["id"] for e in accepted_events(state, v["volumeNumber"])], "pinnedFrom": v.get("pinnedFrom") or [],
            "chapters": [],
        } for v in bins["volumes"]],
    }


def run_outline(name: str, state: dict, resume: bool = False, progress: Progress = no_progress) -> dict:
    if not state.get("bins"):
        raise ValueError("Build the volume bins first.")
    model = planning_model(state)
    rng = state.get("chapterRange")
    store = storage.get_sorted_material(name)
    plan = state.get("plan")
    if not (resume and plan and plan.get("volumes")):
        invalidate_downstream(name, state, "OUTLINE_REVIEW", "reoutline", ("plan", "payoffPlan"))
        plan = _build_plan(state)
        state["plan"] = plan
        if state["mode"] != "RUSH_MODE":
            progress("Setting each volume's chapter count from its material and confirmed mini-events...", 3)
            sort = state["messSortResult"]
            beat_ids = {b["id"] for b in sort["arcBeats"]}
            counts = calibrate_chapter_counts([{
                "volumeNumber": v["volumeNumber"], "title": v["title"], "summary": v["summary"], "currentTarget": v["targetChapterCount"],
                "beats": sum(1 for i in v["sourceItemIds"] if i in beat_ids), "drafts": sum(1 for i in v["sourceItemIds"] if i not in beat_ids),
                "miniEvents": len(v["miniEventIds"]),
                "preview": volume_material(state, v, store, verbatim=False)[:5000],
            } for v in plan["volumes"]], state["mode"], rng, model)
            for c in counts:
                v = next(x for x in plan["volumes"] if x["volumeNumber"] == c["volumeNumber"])
                if c.get("chapters", 0) >= 3:
                    v["targetChapterCount"] = c["chapters"]
                    v["chapterCountReason"] = c.get("reason", "")
        for v in plan["volumes"]:
            v["targetChapterCount"] = clamp_chapters(v["targetChapterCount"], rng)
        storage.save_state(name, state)

    canon = read_canon(name)
    cards = storage.standing_cards(name)
    style = format_style_prompt(state.get("styleConfig"))
    volumes = plan["volumes"]
    for i, vol in enumerate(volumes):
        if vol.get("chapters"):
            continue
        prev = next((x for x in volumes if x["volumeNumber"] == vol["volumeNumber"] - 1), None)
        prev_end = "\n".join(f"Chapter {c['chapterNumber']}: \"{c['title']}\" - {c['synopsis']}" for c in (prev or {}).get("chapters", [])[-2:])

        def on_batch(b: int, t: int, start: int, end: int, target: int, vol=vol, i=i) -> None:
            progress(f'Volume {vol["volumeNumber"]}/{len(volumes)} "{vol["title"]}" - outlining chapters {start}-{end} of {target}',
                     min(97, round(5 + (i + b / t) / len(volumes) * 92)), volume=vol["volumeNumber"])

        allowed = set(vol["sourceItemIds"]) | set(vol["miniEventIds"])
        vol["chapters"] = outline_volume(vol, plan["universeSummary"], canon, volume_material(state, vol, store, verbatim=False), allowed,
                                         prev_end, cards, style, model, on_batch)
        storage.save_state(name, state)
        progress(f'Volume {vol["volumeNumber"]} "{vol["title"]}" outlined ({len(vol["chapters"])} chapters).', min(97, round(5 + (i + 1) / len(volumes) * 92)))
    progress(f"All {len(volumes)} volumes outlined.", 100)
    return state


def regenerate_volume_outline(name: str, state: dict, n: int, progress: Progress = no_progress) -> dict:
    plan = state.get("plan")
    vol = next((v for v in (plan or {}).get("volumes", []) if v["volumeNumber"] == n), None)
    if not vol:
        raise ValueError(f"Volume {n} is not in the plan.")
    vol["chapters"] = []
    vol["miniEventIds"] = [e["id"] for e in accepted_events(state, n)]
    invalidate_downstream(name, state, "OUTLINE_REVIEW", "reoutline-volume", ("payoffPlan",))
    storage.save_state(name, state)
    return run_outline(name, state, resume=True, progress=progress)


def approve_plan(name: str, state: dict) -> dict:
    plan = state.get("plan")
    if not plan or not plan.get("volumes"):
        raise ValueError("No plan to approve.")
    unfinished = [v["volumeNumber"] for v in plan["volumes"] if not v.get("chapters")]
    if unfinished:
        raise ValueError(f"Volume{'s' if len(unfinished) > 1 else ''} {', '.join(map(str, unfinished))} {'have' if len(unfinished) > 1 else 'has'} "
                         "no chapter outline yet. Let the outline finish (or continue it) before approving.")
    mode = state["mode"]
    store = storage.get_sorted_material(name)
    storage.ensure_volume_folders(name, mode, len(plan["volumes"]))
    for v in plan["volumes"]:
        n = v["volumeNumber"]
        storage.write_memory(name, mode, n, "initial_summary.txt", v["summary"])
        storage.write_memory(name, mode, n, "chapters_outline.txt", format_volume_outline(v))
        storage.write_memory(name, mode, n, "SOURCE-MATERIAL.md",
                             f"# VOLUME {n} SOURCE MATERIAL (the author's sorted notes + confirmed mini-events)\n\n{volume_material(state, v, store, verbatim=True) or '(none)'}")
    state["totalVolumes"] = len(plan["volumes"])
    if not any(v["volumeNumber"] == state.get("currentVolume") for v in plan["volumes"]):
        state["currentVolume"] = 1
    cur = next(v for v in plan["volumes"] if v["volumeNumber"] == state["currentVolume"])
    state["chaptersPerVolume"] = len(cur["chapters"])
    # Chapters saved before this plan may not match its outlines: the creators keep or reset each volume
    state["chaptersBeforePlan"] = [v["volumeNumber"] for v in plan["volumes"] if storage.list_chapters(name, mode, v["volumeNumber"])]
    state["status"] = "FORESHADOWING_MODE"
    storage.save_state(name, state)
    return state
