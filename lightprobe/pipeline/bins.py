"""STAGE 5 — Volume bins: every sorted item goes into the volume where it belongs.

- The creators fix the number of volumes (Settings); the engine never changes it.
- A MESS file pinned to a volume (a finished volume) goes into that volume whole, and is never split.
- A volume number the author wrote in a note ("Volume 1, Eighteen") keeps the item in that volume.
- Everything else is placed by its events, in story order. File names never place material.
- No count-balancing. A thin volume is filled in the next stage by mini-events the creators confirm.
- The creators can move any item to another volume, or edit a volume's title and summary.
"""

from __future__ import annotations

from .. import storage
from ..ai import planning_model
from ..ai.planning import bin_items, generate_roadmap, volume_tag
from ..styles import clamp_chapters, format_style_prompt
from .common import Progress, bin_text, format_arc_map, format_clarifications, invalidate_downstream, no_progress, read_canon, source_file
from .ingest import write_ask_me


def fixed_placements(state: dict, total: int | None) -> dict[str, dict]:
    """Items whose volume is already decided: id -> {"volume": n, "reason": str}."""
    sort = state["messSortResult"]
    pins = {f: int(v) for f, v in (state.get("volumePins") or {}).items() if v}
    out: dict[str, dict] = {}

    def place(item_id: str, source: str, tag_text: str) -> None:
        f = source_file(source)
        if f in pins and (not total or pins[f] <= total):
            out[item_id] = {"volume": pins[f], "reason": f'finished volume "{f}"'}
            return
        tag = volume_tag(tag_text)
        if tag and (not total or 1 <= tag <= total):
            out[item_id] = {"volume": tag, "reason": f'author\'s note says Volume {tag} ("{tag_text[:60]}")'}

    for b in sort["arcBeats"]:
        place(b["id"], b.get("source", ""), b.get("phase", ""))
    for m in sort["chapterMaterial"]:
        place(m["id"], m.get("source", ""), m.get("volumeHint", ""))
    return out


def validate_settings(state: dict) -> None:
    total = state.get("targetVolumes")
    pins = {f: v for f, v in (state.get("volumePins") or {}).items() if v}
    names = set(storage.list_mess_names(state["name"]))
    for f, v in pins.items():
        if f not in names:
            raise ValueError(f'The pinned file "{f}" is no longer in MESS. Update the pins in Settings.')
        if total and int(v) > int(total):
            raise ValueError(f'"{f}" is pinned to Volume {v}, but the universe has {total} volumes.')
    rng = state.get("chapterRange") or {}
    if rng.get("min") and rng.get("max") and int(rng["min"]) > int(rng["max"]):
        raise ValueError("The chapter range minimum is larger than the maximum.")


def write_bin_files(name: str, state: dict) -> None:
    bins = state["bins"]
    storage.ensure_volume_folders(name, state["mode"], len(bins["volumes"]))
    store = storage.get_sorted_material(name)
    for v in bins["volumes"]:
        text = bin_text(state, v["itemIds"], store, verbatim=True)
        storage.write_volume_file(name, state["mode"], v["volumeNumber"], "BIN.md",
                                  f"# VOLUME {v['volumeNumber']}: {v['title']}\n\n## Premise\n{v['premise']}\n\n## Summary\n{v['summary']}\n\n"
                                  f"## The author's material in this volume\n\n{text or '(none - this volume is filled by gap-fill)'}")


def run_bins(name: str, state: dict, progress: Progress = no_progress) -> dict:
    sort = state.get("messSortResult")
    if not sort or not state.get("universeBible"):
        raise ValueError("Build the Universe Bible first.")
    validate_settings(state)
    # Re-binning invalidates the mini-events and outlines built on the old bins (kept in the backup)
    backup = invalidate_downstream(name, state, "BIN_REVIEW", "rebin", ("gapFill", "plan", "payoffPlan"))
    if backup:
        progress(f"Previous gap-fill and outlines saved to _backups/{backup}.", 1)
    storage.save_state(name, state)
    total = int(state["targetVolumes"]) if state.get("targetVolumes") else None
    rng = state.get("chapterRange")
    model = planning_model(state)
    fixed = fixed_placements(state, total)
    fixed_beats = {i: f["volume"] for i, f in fixed.items() if i.startswith("B-")}
    pinned_files = {f: int(v) for f, v in (state.get("volumePins") or {}).items() if v}

    progress(f"Reading the whole arc map ({len(sort['arcBeats'])} beats; {len(fixed_beats)} already fixed to their volume) to lay out the volumes...", 5)
    roadmap = generate_roadmap(read_canon(name), storage.standing_cards(name), format_style_prompt(state.get("styleConfig")),
                               format_arc_map(sort, fixed_beats), pinned_files, state["mode"], total, rng, model)
    volumes = roadmap["volumes"]
    # Every volume a fixed item points to exists (drafts-only pins and notes included)
    need = total or max([1, len(volumes), *(f["volume"] for f in fixed.values())])
    volumes = volumes[:need]
    for n in range(len(volumes) + 1, need + 1):
        volumes.append({"volumeNumber": n, "title": f"Volume {n}", "premise": "", "summary": "", "targetChapterCount": 0, "beatIds": []})

    # Fixed items always win; every other beat goes where the roadmap placed it (first volume that lists it)
    known = {b["id"] for b in sort["arcBeats"]}
    placement: dict[str, int] = {}
    for v in volumes:
        for b in v.get("beatIds") or []:
            if b in known and b not in placement:
                placement[b] = v["volumeNumber"]
    placement.update(fixed_beats)

    items = [{"id": m["id"], "label": f"DRAFT, volume note: {m.get('volumeHint') or 'none'}, from: {m.get('source') or 'unknown'}", "text": m["content"]}
             for m in sort["chapterMaterial"] if m["id"] not in fixed]
    items += [{"id": b["id"], "label": f"ARC-BEAT, phase: {b.get('phase') or 'unstated'}, from: {b.get('source') or 'unknown'}",
               "text": f"{b['event']} -> {b['irreversibleChange']}"} for b in sort["arcBeats"] if b["id"] not in placement]
    beat_text = {b["id"]: f"{b['event']} -> {b['irreversibleChange']}" for b in sort["arcBeats"]}
    for v in volumes:
        v["beatIds"] = [b for b, n in placement.items() if n == v["volumeNumber"]]
    assignments: dict[str, dict] = {}
    if items:
        assignments = bin_items(volumes, items, beat_text, format_clarifications(sort), model,
                                on_batch=lambda b, t: progress(f"Placing the draft passages into the volumes (batch {b}/{t})...", 30 + round(b / max(1, t) * 55)))
    for i, f in fixed.items():
        if i.startswith("M-"):
            assignments[i] = {"volume": f["volume"], "assumed": False}
    for b, n in placement.items():
        assignments[b] = {"volume": n, "assumed": False}

    order = [b["id"] for b in sort["arcBeats"]] + [m["id"] for m in sort["chapterMaterial"]]
    state["bins"] = {
        "universeSummary": roadmap.get("universeSummary", ""),
        "volumes": [{
            "volumeNumber": v["volumeNumber"], "title": v["title"], "premise": v["premise"], "summary": v["summary"],
            "targetChapterCount": clamp_chapters(v.get("targetChapterCount") or (rng or {}).get("min") or 10, rng),
            "itemIds": [i for i in order if (assignments.get(i) or {}).get("volume") == v["volumeNumber"]],
            "pinnedFrom": sorted(f for f, n in pinned_files.items() if n == v["volumeNumber"]),
        } for v in volumes],
        "unplaced": [i for i in order if not (assignments.get(i) or {}).get("volume")],
        "assumed": [i for i in order if (assignments.get(i) or {}).get("assumed")],
        "fixed": {i: f["reason"] for i, f in fixed.items()},
    }
    state["totalVolumes"] = len(volumes)
    write_bin_files(name, state)
    write_ask_me(name, state)
    storage.save_state(name, state)
    counts = ", ".join(f"V{v['volumeNumber']}: {len(v['itemIds'])}" for v in state["bins"]["volumes"])
    progress(f"{len(volumes)} volume bins ready ({counts}). {len(state['bins']['unplaced'])} non-story notes left out.", 100)
    return state


def move_item(name: str, state: dict, item_id: str, to_volume: int | None) -> dict:
    """The creators move one item to another volume (None = take it out of every volume)."""
    bins = state.get("bins")
    if not bins:
        raise ValueError("No volume bins yet.")
    valid = {v["volumeNumber"] for v in bins["volumes"]}
    if to_volume is not None and to_volume not in valid:
        raise ValueError(f"Volume {to_volume} does not exist.")
    sort = state["messSortResult"]
    order = [b["id"] for b in sort["arcBeats"]] + [m["id"] for m in sort["chapterMaterial"]]
    if item_id not in order:
        raise ValueError(f"Item {item_id} not found.")
    for v in bins["volumes"]:
        v["itemIds"] = [i for i in v["itemIds"] if i != item_id]
        if v["volumeNumber"] == to_volume:
            v["itemIds"] = [i for i in order if i in set(v["itemIds"]) | {item_id}]
    bins["unplaced"] = [i for i in bins.get("unplaced", []) if i != item_id] + ([item_id] if to_volume is None else [])
    bins["assumed"] = [i for i in bins.get("assumed", []) if i != item_id]
    bins.setdefault("movedByCreators", {})[item_id] = to_volume
    invalidate_downstream(name, state, "BIN_REVIEW", "bins-changed", ("plan", "payoffPlan"))
    write_bin_files(name, state)
    storage.save_state(name, state)
    return state


def edit_volume(name: str, state: dict, volume_number: int, title: str, premise: str, summary: str) -> dict:
    v = next((x for x in (state.get("bins") or {}).get("volumes", []) if x["volumeNumber"] == volume_number), None)
    if not v:
        raise ValueError(f"Volume {volume_number} not found.")
    v.update(title=title.strip() or v["title"], premise=premise.strip(), summary=summary.strip())
    invalidate_downstream(name, state, "BIN_REVIEW", "bins-changed", ("plan", "payoffPlan"))
    write_bin_files(name, state)
    storage.save_state(name, state)
    return state


def approve_bins(name: str, state: dict) -> dict:
    if not state.get("bins"):
        raise ValueError("Build the volume bins first.")
    write_bin_files(name, state)
    state["status"] = "GAP_REVIEW"
    storage.save_state(name, state)
    return state
