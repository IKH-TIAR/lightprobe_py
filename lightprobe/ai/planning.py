"""STEPS 5-8 — Volume roadmap and bins, gap-fill (mini-events), chapter outlines, payoff planner.

Placement rules (what the creators asked for):
- The creators fix the number of volumes; the engine never changes it.
- A finished volume (a MESS file pinned to a volume) is never split or moved.
- A volume number written in the notes is the author's own numbering and is kept.
- Everything else goes where its events belong, in story order. File names never place material.
- No count-balancing: a thin volume is filled by gap-fill (mini-events the creators confirm),
  never by stretching another volume's events.
"""

from __future__ import annotations

import re

from ..llm import B, CallOptions, I, S, arr, enum, generate_json, obj
from ..styles import RUSH_CHAPTER_RANGE, clamp_chapters, describe_chapter_range

VOLUME_TAG = re.compile(r"\bvol(?:ume)?\.?\s*(\d{1,3})\b", re.I)
# "After Volume 1", "before vol 3", "end of Volume 2" say where something is RELATIVE to a volume, not in it
RELATIVE_TAG = re.compile(r"\b(after|before|since|following|post|pre|until|till|beyond|end\s+of|between)\s*[-\s]?\s*$", re.I)
BIN_BATCH_SIZE = 120
OUTLINE_BATCH_SIZE = 5


def volume_tag(text: str | None) -> int | None:
    """The volume number the author wrote in a note ("Volume 1, Eighteen", "Vol 4 Arc"), if any. A relative
    mention ("After Volume 1") is not a placement and returns None, so the item is placed by its events."""
    text = text or ""
    for m in VOLUME_TAG.finditer(text):
        if not RELATIVE_TAG.search(text[:m.start()]):
            return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Roadmap: the volumes and where every arc beat goes
# ---------------------------------------------------------------------------

ROADMAP_SCHEMA = obj({
    "universeSummary": S,
    "volumes": arr(obj({"volumeNumber": I, "title": S, "premise": S, "summary": S, "targetChapterCount": I, "beatIds": arr(S)})),
})


def generate_roadmap(canon: str, standing_cards: str, style_prompt: str, arc_map: str,
                     pinned_files: dict[str, int], mode: str, target_volumes: int | None, chapter_range: dict | None,
                     model: str, correction: str = "") -> dict:
    """Beats whose volume is already decided (pinned files, the author's volume numbers) are marked
    "FIXED -> Volume N" in `arc_map`; the model places every other beat by its events."""
    system = "You are the Master Light Probe Universe Architect (Capacity 1: UNIVERSE SCAN). You MUST respond ONLY with valid JSON."
    cached = f"=== STANDING CARDS ===\n{standing_cards}\n\n{style_prompt}\n\n=== CANON (UNIVERSE BIBLE + SOUL ROSTER) ===\n{canon}"
    rng = describe_chapter_range(chapter_range)
    if mode == "RUSH_MODE":
        mode_rule = (f"RUSH MODE: compress the whole universe into {RUSH_CHAPTER_RANGE[0]} to {RUSH_CHAPTER_RANGE[1]} chapters TOTAL "
                     "across all volumes, hitting the major events and turning points.")
    else:
        mode_rule = "SLOW BURN MODE: full slice-of-life detail between main events; chapter counts follow the material and the creators' range."
    count_rule = (f"VOLUME COUNT (set by the creators, never change it): output EXACTLY {target_volumes} volumes, numbered 1-{target_volumes}."
                  if target_volumes else "VOLUME COUNT: determine how many volumes the material actually holds.")
    pins = "\n".join(f"- Volume {v}: the creators' finished volume from \"{f}\"" for f, v in sorted(pinned_files.items(), key=lambda x: x[1]))
    pin_block = f"\nFINISHED VOLUMES (pinned by the creators):\n{pins}\n" if pins else ""
    corr = f"\nCORRECTION FROM PREVIOUS ATTEMPT: {correction}\n" if correction else ""
    prompt = f"""
UNIVERSE SCAN & VOLUME ROADMAP (mode: {mode})

Each volume is a TIMESTAMP: its opening is the state of things as the period opens; its end is the irreversible change that closes it.

=== MASTER ARC MAP (every arc beat sorted from the author's notes, in intake order) ===
Beats marked "FIXED -> Volume N" already belong to that volume (a finished volume or the author's own volume number). Keep them there.
{arc_map or '(No arc beats were sorted.)'}
{pin_block}
{count_rule}
{mode_rule}
{f"CHAPTERS PER VOLUME (set by the creators): every volume must have {rng}." if rng else ""}

PLACEMENT RULES:
1. Every FIXED beat stays in its volume. A finished volume is never split, shortened or moved.
2. Place every other beat in the volume where its event happens, in story order. Volumes run chronologically.
3. The arc map is in intake order, not story order; several files may describe the same events. Notes about the same event go into the same volume.
4. A FILE NAME is never a placement rule (unless the creators pinned that file above). A file titled "Part 2 of Volume 3" only marks where its material starts; its events may continue across later volumes.
5. Do NOT balance volumes by spreading one volume's events over several to fill space. When the material has fewer main events than there are volumes, place the established main events across the remaining volumes in story order so each volume builds toward at least one main event or turning point. A volume left thin is filled later by gap-fill (mini-events the creators confirm).
6. Dense material that genuinely covers several arcs (for example one long file spanning several arcs) runs across consecutive volumes, cut at natural turning points.
{corr}
For EACH volume: volumeNumber; title (grounded, specific to this universe); premise (opening timestamp, central conflict, the irreversible change that closes it); summary (2-3 paragraphs of what happens, built ONLY from the arc map and canon - for a thin volume, say which main event it builds toward); targetChapterCount; beatIds (the IDs of every beat whose event happens in this volume, FIXED ones included).
Also give universeSummary. Do NOT output chapter breakdowns."""
    res = generate_json(CallOptions(model=model, system=system, cached_context=cached, schema=ROADMAP_SCHEMA), prompt)
    volumes = res.get("volumes") or []
    for i, v in enumerate(volumes):
        v["volumeNumber"] = i + 1
        v["targetChapterCount"] = max(1, round(v.get("targetChapterCount") or 1))
    if not correction:
        problems = []
        if target_volumes and len(volumes) != target_volumes:
            problems.append(f"Your roadmap had {len(volumes)} volumes; the creators require exactly {target_volumes}.")
        if rng:
            out = [v for v in volumes if clamp_chapters(v["targetChapterCount"], chapter_range) != v["targetChapterCount"]]
            if out:
                problems.append("Volumes " + ", ".join(f"{v['volumeNumber']} ({v['targetChapterCount']})" for v in out) + f" are outside the creators' range of {rng}.")
        if mode == "RUSH_MODE":
            total = sum(v["targetChapterCount"] for v in volumes)
            if not RUSH_CHAPTER_RANGE[0] <= total <= RUSH_CHAPTER_RANGE[1]:
                problems.append(f"Your roadmap totalled {total} chapters. Rush Mode requires {RUSH_CHAPTER_RANGE[0]}-{RUSH_CHAPTER_RANGE[1]} chapters in total.")
        if problems:
            return generate_roadmap(canon, standing_cards, style_prompt, arc_map, pinned_files, mode, target_volumes,
                                    chapter_range, model, " ".join(problems))
    res["volumes"] = volumes
    return res


def bin_items(volumes: list[dict], items: list[dict], beat_text: dict[str, str], clarifications: str, model: str, on_batch=None) -> dict[str, dict]:
    """Places draft passages (and any beats the roadmap missed) into the volume holding the beats whose
    events they show. Returns id -> {"volume": n | None, "assumed": bool}. None = not story content."""
    system = ("You are the MESS Sorter's volume router. You place every piece of sorted material into the volume bin where "
              "it belongs chronologically, using the whole picture of the universe. Respond ONLY with valid JSON.")
    vol_list = "\n\n".join(
        f"Volume {v['volumeNumber']}: \"{v['title']}\"\nPremise: {v['premise']}\nSummary: {v['summary']}" +
        (("\nArc beats in this volume:\n" + "\n".join(f"[{b}] {beat_text.get(b, '')[:160]}" for b in v.get("beatIds") or [] if b in beat_text))
         if v.get("beatIds") else "")
        for v in volumes)
    if clarifications:
        vol_list += f"\n\n=== AUTHOR CLARIFICATIONS (canon - use them for placement) ===\n{clarifications}"
    valid = {v["volumeNumber"] for v in volumes}
    out: dict[str, dict] = {}
    total = (len(items) + BIN_BATCH_SIZE - 1) // BIN_BATCH_SIZE
    for i in range(0, len(items), BIN_BATCH_SIZE):
        if on_batch:
            on_batch(i // BIN_BATCH_SIZE + 1, total)
        batch = items[i:i + BIN_BATCH_SIZE]
        listing = "\n".join(f"[{it['id']}] ({it['label']}) {it['text'][:400]}" for it in batch)
        prompt = f"""
Place each item into the ONE volume where it belongs, using the volumes (with the arc beats already placed in them) given above.
- A draft passage belongs in the volume that holds the arc beats whose events it shows (same characters, same moment). Follow those beats.
- Otherwise use the volume summaries, the characters and events involved, and the author clarifications.
- The source FILE name ("from: ...") is NOT a placement rule: place every item by the chronology of its own event.
- When the item clearly shows the events of beats in that volume, or the notes state its place: "assumed": false.
- When you have to infer the most likely volume from the overall chronology: still choose it, with "assumed": true.
- Use 0 ONLY for items that are not story content at all (meta notes, logistics).

=== ITEMS ===
{listing}"""
        res = generate_json(CallOptions(model=model, system=system, cached_context=vol_list, effort="medium",
                                        schema=obj({"assignments": arr(obj({"id": S, "volume": I, "assumed": B}))})), prompt)
        ids = {it["id"] for it in batch}
        for a in res.get("assignments") or []:
            if a.get("id") in ids:
                vol = a.get("volume") if a.get("volume") in valid else None
                out[a["id"]] = {"volume": vol, "assumed": bool(vol and a.get("assumed"))}
    for it in items:
        out.setdefault(it["id"], {"volume": None, "assumed": False})
    return out


# ---------------------------------------------------------------------------
# Gap-fill: what is missing between the main events, and the mini-events that lead to them
# ---------------------------------------------------------------------------

MINI_EVENT_KINDS = ("KNOWLEDGE", "PRESSURE", "RELATIONSHIP", "WORLD", "TEXTURE")
GAP_SCHEMA = obj({
    "volumeStart": S,
    "mainEvents": arr(obj({"ref": S, "event": S})),
    "miniEvents": arr(obj({
        "title": S, "event": S, "cause": S, "effect": S, "leadsTo": S, "after": S,
        "souls": arr(S), "kind": enum(*MINI_EVENT_KINDS), "needsDecision": B, "decisionNote": S,
    })),
    "questions": arr(obj({"question": S, "why": S, "about": S})),
})


def propose_gap_fill(volume: dict, bin_text: str, previous_context: str, next_context: str, canon: str, gap_card: str,
                     roadmap_brief: str, mode: str, chapter_range: dict | None, creator_notes: str, keep: list[dict], model: str) -> dict:
    system = ("You are the Gap-Fill engine (Card 05 GAP-FILL, LNF-ARC). You know the main events ahead and the most recent "
              "present behind; you find what must compound between them, step by step, by cause and effect. Respond ONLY with valid JSON.")
    cached = f"=== 05-GAP-FILL (law) ===\n{gap_card}\n\n=== CANON ===\n{canon}\n\n=== ALL VOLUMES (roadmap) ===\n{roadmap_brief}"
    rng = describe_chapter_range(chapter_range)
    keep_block = ("\n=== MINI-EVENTS THE CREATORS ALREADY ACCEPTED (keep them; build around them) ===\n" +
                  "\n".join(f"- {k['title']}: {k['event']}" for k in keep) + "\n") if keep else ""
    notes = f"\n=== CREATOR NOTES FOR THIS VOLUME ===\n{creator_notes}\n" if creator_notes.strip() else ""
    slow = ("SLOW BURN: slice-of-life mini-events are welcome, but only ones that change something (knowledge, pressure, a relationship, "
            "the world) on the way to a main event." if mode != "RUSH_MODE" else "RUSH: only the mini-events the main events strictly need.")
    prompt = f"""
GAP-FILL - VOLUME {volume['volumeNumber']}: "{volume['title']}"
Premise: {volume['premise']}
Summary: {volume['summary']}
{f"The creators set {rng}; the mini-events should give this volume enough real material to carry that many chapters." if rng else ""}

=== WHERE THINGS STAND BEFORE THIS VOLUME (most recent present) ===
{previous_context or '(This is the first volume - the opening state comes from the canon.)'}

=== THIS VOLUME'S BIN (the author's material sorted into it; ids in brackets) ===
{bin_text or '(The notes place no material in this volume yet.)'}

=== WHAT THE NEXT VOLUME OPENS WITH (this volume must lead there) ===
{next_context or '(This is the final volume.)'}
{keep_block}{notes}
PROCEDURE (05-GAP-FILL):
1. Fix both ends: "volumeStart" = where we are exactly as the volume opens; "mainEvents" = the author's established main events in this volume, in story order, each with the bin id ("ref") it comes from.
2. For each main event, ask what must be true at that moment that is not true yet - knowledge a soul must gain, pressure that must build, a relationship that must shift, a world change that must land.
3. Each of those is a mini-arc made of MINI-EVENTS. Order them by what compounds: B cannot happen until A has. For each mini-event:
   "event" (what physically happens, concrete), "cause" (the earlier event that makes it happen), "effect" (what it changes or makes possible),
   "leadsTo" (the ref of the main event it builds toward, or "VOLUME_END"), "after" (the ref or mini-event title it directly follows, or "START"),
   "souls", "kind" (KNOWLEDGE / PRESSURE / RELATIONSHIP / WORLD / TEXTURE).
4. {slow}
5. Never invent a new main event, a world rule, or a change to a soul's essence. If a gap cannot be closed without one, do not invent it: ask in "questions" (what you need the creators to decide, why, and which ref it is about).
   Ask ONLY what truly blocks a gap - at most 5 questions, most important first. Anything you can reasonably settle inside the allowed inventions, settle it in a mini-event (and mark it needsDecision if it is a creative call) instead of asking.
6. Any mini-event that changes what a soul knows or how two souls stand with each other is a creative decision: set "needsDecision": true and say in "decisionNote" what the creators are deciding.
7. Never pad: every mini-event must change something. Use "" for fields that do not apply."""
    return generate_json(CallOptions(model=model, system=system, cached_context=cached, schema=GAP_SCHEMA), prompt)


# ---------------------------------------------------------------------------
# Chapter counts and outlines
# ---------------------------------------------------------------------------

def calibrate_chapter_counts(volumes: list[dict], mode: str, chapter_range: dict | None, model: str) -> list[dict]:
    """Sets each volume's chapter count from its bin plus its confirmed mini-events (05 GAP-FILL: count
    what the material needs), inside the creators' range."""
    system = ("You are the Master Light Probe Arc Breakdown planner (LNF-ARC, Card 05 GAP-FILL). You set chapter counts from the "
              "material, never by formula. Respond ONLY with valid JSON.")
    rng = describe_chapter_range(chapter_range)
    listing = "\n\n".join(
        f"=== VOLUME {v['volumeNumber']}: {v['title']} ===\nRoadmap guess: {v['currentTarget']} chapters | Bin: {v['beats']} beats, "
        f"{v['drafts']} draft passages, {v['miniEvents']} confirmed mini-events\nSummary: {v['summary']}\nMaterial preview:\n{v['preview'] or '(empty)'}"
        for v in volumes)
    prompt = f"""
Each volume below holds the author's sorted material plus the mini-events the creators confirmed. Set each volume's chapter count from that material.
- Count what the material needs. Padding to reach a number is slop.
- {'SLOW BURN: slice-of-life chapters are allowed around events the material establishes.' if mode != 'RUSH_MODE' else 'RUSH: compress to the major events and turning points.'}
{f"- CREATORS' LIMIT (overrides the rules above): every volume must have {rng}. Within that range, fit the count to the material." if rng else ''}

{listing}

For every volume give "chapters" (a whole number, at least 3) and a one-sentence "reason" that cites the material."""
    res = generate_json(CallOptions(model=model, system=system, effort="medium",
                                    schema=obj({"volumes": arr(obj({"volumeNumber": I, "chapters": I, "reason": S}))})), prompt)
    nums = {v["volumeNumber"] for v in volumes}
    return [v for v in res.get("volumes") or [] if v.get("volumeNumber") in nums]


OUTLINE_SCHEMA = obj({"chapters": arr(obj({
    "chapterNumber": I, "title": S, "synopsis": S,
    "pacingType": enum("EXTENSIVE_DEEP_DIVE", "KINETIC_TURNING_POINT", "TIGHT_PIVOT"),
    "momentGenre": S, "focalSoul": S, "timeCoordinate": S, "sourceRefs": arr(S),
}))})


def outline_volume(volume: dict, universe_summary: str, canon: str, bin_text: str, allowed_refs: set[str], previous_ending: str,
                   standing_cards: str, style_prompt: str, model: str, on_batch=None) -> list[dict]:
    system = "You are the Master Light Probe Chapter Architect (Capacity 2: ARC DIVE). You MUST respond ONLY with valid JSON."
    cached = (f"=== STANDING CARDS ===\n{standing_cards}\n\n{style_prompt}\n\n=== CANON (UNIVERSE BIBLE + SOUL ROSTER) ===\n{canon}"
              f"\n\n=== UNIVERSE SUMMARY ===\n{universe_summary}\n\n=== VOLUME {volume['volumeNumber']} BIN (the author's material and the "
              f"creator-confirmed mini-events for this volume) ===\n{bin_text or '(No material in this volume.)'}")
    target = volume.get("targetChapterCount") or 10
    batches = (target + OUTLINE_BATCH_SIZE - 1) // OUTLINE_BATCH_SIZE
    chapters: list[dict] = []
    for start in range(1, target + 1, OUTLINE_BATCH_SIZE):
        end = min(start + OUTLINE_BATCH_SIZE - 1, target)
        batch_index = (start - 1) // OUTLINE_BATCH_SIZE + 1
        count = end - start + 1
        if on_batch:
            on_batch(batch_index, batches, start, end, target)
        if chapters:
            recap = f"=== CHAPTERS 1-{len(chapters)} ALREADY OUTLINED ===\n" + "\n\n".join(
                f"Chapter {c['chapterNumber']}: \"{c['title']}\" | {c['pacingType']} | {c['momentGenre']} | Focal: {c['focalSoul']} | {c['timeCoordinate']}\n{c['synopsis']}"
                + (f"\nSources: {', '.join(c['sourceRefs'])}" if c.get("sourceRefs") else "") for c in chapters)
        elif previous_ending:
            recap = f"=== HOW THE PREVIOUS VOLUME ENDED ===\n{previous_ending}"
        else:
            recap = f"(Batch 1: Chapter 1 of Volume {volume['volumeNumber']})"
        opening_end = max(2, int(target * 0.25))
        peak_start, peak_end = max(4, int(target * 0.65)) + 1, max(5, int(target * 0.85))
        flow = (f"Chapter {start} picks up the causal aftermath of Chapter {start - 1}." if chapters else "Chapter 1 opens on pressure already present.")
        flow += (f" Chapter {end} ends with open momentum into Chapter {end + 1}." if end < target else f" Chapter {end} lands the volume's irreversible change.")
        prompt = f"""
CHAPTER OUTLINER - VOLUME {volume['volumeNumber']}: "{volume['title']}" ({target} chapters)
TASK: outline EXACTLY {count} chapters: {start} through {end}.

VOLUME PREMISE: {volume['premise']}
VOLUME SUMMARY: {volume['summary']}

FOUR ARC PHASES across the volume: OPENING (about 1-{opening_end}) -> BUILD -> PEAK (about {peak_start}-{peak_end}) -> TURN AND LAND (to {target}).

{recap}

REQUIREMENTS:
1. Build every chapter from the VOLUME BIN and canon. Each beat, draft scene and confirmed mini-event lands in the chapter where it chronologically belongs; list the ids used in "sourceRefs" (ids from the bin only).
2. Confirmed mini-events (ids starting with "E") are canon the creators approved: use every one of them, in their order.
3. GAP-FILL: beyond the bin you may invent only texture, routes, weather and minor functional souls - never a new main event, world rule, or change to what a soul knows.
4. {flow}
5. Synopsis: 3-4 concrete sentences - setting and what the focal soul is attempting; the friction; the choices under pressure; the irreversible shift that sets up the next chapter.
6. pacingType: EXTENSIVE_DEEP_DIVE | KINETIC_TURNING_POINT | TIGHT_PIVOT. momentGenre: the matching S01-S18 lens. focalSoul and timeCoordinate (time, place, weather/temperature)."""
        res = generate_json(CallOptions(model=model, system=system, cached_context=cached, schema=OUTLINE_SCHEMA), prompt)
        got = (res.get("chapters") or [])[:count]
        if len(got) < count:
            raise ValueError(f"Outliner returned {len(got)} of {count} chapters for Volume {volume['volumeNumber']}, chapters {start}-{end}. Run the outline again.")
        for idx, ch in enumerate(got):
            chapters.append({
                "chapterNumber": start + idx,
                "title": ch.get("title", ""),
                "synopsis": ch.get("synopsis", ""),
                "pacingType": ch.get("pacingType") or "EXTENSIVE_DEEP_DIVE",
                "momentGenre": ch.get("momentGenre", ""),
                "focalSoul": ch.get("focalSoul", ""),
                "timeCoordinate": ch.get("timeCoordinate", ""),
                "sourceRefs": [r for r in ch.get("sourceRefs") or [] if r in allowed_refs],
            })
    return chapters


# ---------------------------------------------------------------------------
# Payoff & foreshadowing (Card 06-MULTI-QUADRANT)
# ---------------------------------------------------------------------------

PAYOFF_SCHEMA = obj({"overallStrategy": S, "payoffs": arr(obj({
    "id": S, "threadName": S, "origin": enum("AUTHOR", "INFERRED"),
    "setupVolume": I, "setupChapterNumber": I, "setupDescription": S,
    "payoffVolume": I, "payoffChapterNumber": I, "payoffDescription": S, "narrativeImpact": S,
}))})


def generate_payoff_plan(universe_summary: str, volumes_context: str, standing_cards: str, chapter_counts: dict[int, int],
                         model: str, correction: str = "", finished: frozenset[int] = frozenset()) -> dict:
    system = "You are the Master Narrative Architect executing the Multi-Quadrant Payoff & Chekhov's Gun Protocol. You MUST respond ONLY with valid JSON."
    corr = f"\nCORRECTION FROM PREVIOUS ATTEMPT: {correction}\n" if correction else ""
    counts = ", ".join(f"V{v}: 1-{n}" for v, n in sorted(chapter_counts.items()))
    prompt = f"""
Design the MASTER PAYOFF ARCHITECTURE for this universe from the volume plans and the author's binned material below.

PRINCIPLES:
1. Author first: every setup/payoff the author's material already implies (clues, objects, promises, secrets) must be included, marked "origin": "AUTHOR".
   Add new threads only where the material leaves a gap, marked "origin": "INFERRED". Aim for one to three threads per volume that the material supports, spread across the whole series.
2. Grounded mechanisms: follow where currency, resources, emotional debt, or institutional stakes flow.
3. Invisible seeds: the setup is an innocent, tangible detail - an object, a hesitation, a casual phrase - that a first-time reader takes as texture.
4. Irreversible payoff: it permanently changes souls or the civilizational balance.
5. setupChapterNumber / payoffChapterNumber must be chapters that exist in that volume's outline (chapters per volume: {counts}). The payoff comes after the setup.
{f"6. Volumes {', '.join(map(str, sorted(finished)))} are FINISHED (already written by the author). A setup there must be something already in that volume's material (origin AUTHOR); never plant a new INFERRED seed in a finished volume." if finished else ""}
{corr}
UNIVERSE SUMMARY:
{universe_summary}

VOLUMES, OUTLINES & BINNED MATERIAL:
{volumes_context}"""
    res = generate_json(CallOptions(model=model, system=system, cached_context=f"=== STANDING CARDS ===\n{standing_cards}", schema=PAYOFF_SCHEMA), prompt)
    payoffs = []
    used_ids: set[str] = set()
    for i, p in enumerate(res.get("payoffs") or []):
        # The id names a file (payoff_seed_<id>.txt): letters, digits, _ and - only, and unique
        tid = re.sub(r"[^A-Za-z0-9_-]", "_", p.get("id") or "")[:40] or f"thread_{i + 1}"
        while tid in used_ids:
            tid = f"{tid}_{i + 1}"
        used_ids.add(tid)
        payoffs.append({
            "id": tid,
            "threadName": p.get("threadName") or f"Thread {i + 1}",
            "origin": "AUTHOR" if p.get("origin") == "AUTHOR" else "INFERRED",
            "setupVolume": int(p.get("setupVolume") or 1),
            "setupChapterNumber": int(p.get("setupChapterNumber") or 1),
            "setupDescription": p.get("setupDescription", ""),
            "payoffVolume": int(p.get("payoffVolume") or 1),
            "payoffChapterNumber": int(p.get("payoffChapterNumber") or 1),
            "payoffDescription": p.get("payoffDescription", ""),
            "narrativeImpact": p.get("narrativeImpact", ""),
        })
    if not correction:
        def exists(v: int, c: int) -> bool:
            return 1 <= c <= chapter_counts.get(v, 0)
        bad = [p for p in payoffs if not exists(p["setupVolume"], p["setupChapterNumber"]) or not exists(p["payoffVolume"], p["payoffChapterNumber"])
               or (p["payoffVolume"], p["payoffChapterNumber"]) <= (p["setupVolume"], p["setupChapterNumber"])]
        if bad:
            listing = "; ".join(f"{p['threadName']} (V{p['setupVolume']} Ch{p['setupChapterNumber']} -> V{p['payoffVolume']} Ch{p['payoffChapterNumber']})" for p in bad)
            return generate_payoff_plan(universe_summary, volumes_context, standing_cards, chapter_counts, model,
                                        f"These threads point at chapters that do not exist or pay off before their setup: {listing}. Use only existing chapters.",
                                        finished)
    # Whatever remains invalid after the correction is dropped rather than silently never planted
    valid = [p for p in payoffs if 1 <= p["setupChapterNumber"] <= chapter_counts.get(p["setupVolume"], 0)
             and 1 <= p["payoffChapterNumber"] <= chapter_counts.get(p["payoffVolume"], 0)
             and (p["payoffVolume"], p["payoffChapterNumber"]) > (p["setupVolume"], p["setupChapterNumber"])
             and not (p["origin"] == "INFERRED" and p["setupVolume"] in finished)]
    return {"overallStrategy": res.get("overallStrategy", ""), "payoffs": valid, "dropped": len(payoffs) - len(valid)}
