"""STAGES 9-10 — The chapter loop and the volume handoff.

ONE chapter per call, from its own context bin. A written chapter is a DRAFT (kept in state so it
survives closing the app) until the creators save it; only saving writes the chapter file, the
ledger entry, the soul updates and the background. After every 3 saved chapters the review gate
opens. When a volume's chapters are saved, the PASS-OUT/PASS-IN handoff carries it forward.
"""

from __future__ import annotations

import re

from .. import storage
from ..ai import planning_model, writing_model
from ..ai.writing import audit_chapter, audit_subtlety, elevate_chapter, soul_index_for_volume, volume_pass_out, write_chapter
from ..jobs import JobStopped
from ..llm import tail
from ..styles import format_style_prompt
from .common import Progress, bin_text, no_progress
from .outline import format_volume_outline
from .payoff import seed_status_report

LEDGER_TAIL_CHARS = 8000
PREVIOUS_CHAPTER_TAIL_CHARS = 3000
BACKGROUND_TAIL_CHARS = 6000
CHAPTER_SOURCE_CAP = 40000
MILESTONE_EVERY = 100
RECONSTRUCTED_PASS_IN_MARK = "> PASS-IN reconstructed"
# Files produced by writing a volume's chapters; a reset moves them to _backups/ with the chapters
VOLUME_WRITING_MEMORY = ["02-SOUL-INDEX.md", "CONTINUITY-LEDGER.md", "05-BACKGROUND.txt", "PASS-OUT.md"]


def volume_plan(state: dict, n: int | None = None) -> dict | None:
    n = n or state["currentVolume"]
    return next((v for v in (state.get("plan") or {}).get("volumes", []) if v["volumeNumber"] == n), None)


def seeds_for_chapter(state: dict, volume: int, chapter: int) -> list[dict]:
    """Seeds whose SETUP is in this exact chapter - setup instructions only, never the payoff."""
    return [p for p in (state.get("payoffPlan") or {}).get("payoffs") or [] if p["setupVolume"] == volume and p["setupChapterNumber"] == chapter]


def payoffs_for_chapter(state: dict, volume: int, chapter: int) -> list[dict]:
    """Threads whose planned payoff is due in this exact chapter."""
    return [p for p in (state.get("payoffPlan") or {}).get("payoffs") or []
            if p["payoffVolume"] == volume and p["payoffChapterNumber"] == chapter]


def chapter_source_material(name: str, state: dict, chapter: dict) -> str:
    """Verbatim author material and confirmed mini-events for one chapter, from its sourceRefs."""
    refs = chapter.get("sourceRefs") or []
    minis = []
    for gv in ((state.get("gapFill") or {}).get("volumes") or {}).values():
        minis += [e for e in gv.get("miniEvents") or [] if e["id"] in refs and e.get("status") == "ACCEPTED"]
    text = bin_text(state, refs, storage.get_sorted_material(name), verbatim=True, mini_events=minis)
    return text[:CHAPTER_SOURCE_CAP] + "\n...(further material truncated - see SOURCE-MATERIAL.md)" if len(text) > CHAPTER_SOURCE_CAP else text


def carry_context(name: str, state: dict, volume: int, chapter: int) -> dict:
    """What a chapter carries in from the chapters before it. Used by the writer AND by the "Carried into
    Chapter N" panel, so the panel always shows exactly what the writer gets."""
    mode = state["mode"]
    if chapter > 1:
        previous = storage.chapter_text(name, mode, volume, chapter - 1)
    elif volume > 1:
        prev_chapters = storage.list_chapters(name, mode, volume - 1)
        previous = prev_chapters[-1]["content"] if prev_chapters else ""
    else:
        previous = ""
    return {
        "ledgerTail": tail(storage.read_memory(name, mode, volume, "CONTINUITY-LEDGER.md"), LEDGER_TAIL_CHARS),
        "previousChapterTail": previous[-PREVIOUS_CHAPTER_TAIL_CHARS:],
        "backgroundRef": tail(storage.read_background(name, mode, volume), BACKGROUND_TAIL_CHARS),
        "seeds": seeds_for_chapter(state, volume, chapter),
        "payoffs": payoffs_for_chapter(state, volume, chapter),
    }


def build_reconstructed_pass_in(name: str, state: dict, volume: int) -> str:
    """Writing starts at Volume N but Volumes 1..N-1 were not written here: their events are fixed by the
    plan, so the opening state is rebuilt from their planned chapters. A real handoff always wins."""
    earlier = [v for v in state["plan"]["volumes"] if v["volumeNumber"] < volume]
    target = volume_plan(state, volume)
    events = "\n\n".join(f"## VOLUME {v['volumeNumber']}: {v['title']}\n{v['premise']}\n" +
                         "\n".join(f"### Chapter {c['chapterNumber']}: {c['title']}\n{c['synopsis']}" for c in v["chapters"]) for v in earlier)
    seeds = "\n".join(f"- [{p['threadName']}] planted Vol {p['setupVolume']} Ch {p['setupChapterNumber']}: {p['setupDescription']} -> payoff Vol {p['payoffVolume']} Ch {p['payoffChapterNumber']}"
                      for p in (state.get("payoffPlan") or {}).get("payoffs") or [] if p["setupVolume"] < volume)
    res = volume_pass_out(volume - 1, f"PLANNED EVENTS OF VOLUMES 1-{volume - 1} (canon - these events are fixed even though the prose is not written in this engine yet):\n\n{events}",
                          storage.read_core(name, "SOUL-ROSTER.md"), seeds, "", format_volume_outline(target) if target else "", planning_model(state))
    doc = f"{RECONSTRUCTED_PASS_IN_MARK} from the planned events of Volumes 1-{volume - 1} (those volumes were not written in this engine).\n\n{res['passOutDoc']}"
    storage.write_memory(name, state["mode"], volume, "PASS-IN.md", doc)
    return doc


def ensure_soul_index(name: str, state: dict, volume: int, progress: Progress = no_progress) -> str:
    mode = state["mode"]
    existing = storage.read_memory(name, mode, volume, "02-SOUL-INDEX.md")
    if existing.strip():
        return existing
    pass_in = storage.read_memory(name, mode, volume, "PASS-IN.md")
    if not pass_in.strip() and volume > 1:
        progress(f"Rebuilding the story so far (Volumes 1-{volume - 1}) from the plan for Volume {volume}'s PASS-IN...", 5)
        pass_in = build_reconstructed_pass_in(name, state, volume)
    progress(f"Building the character index for Volume {volume}...", 15)
    vol = volume_plan(state, volume)
    index = soul_index_for_volume(storage.read_core(name, "SOUL-ROSTER.md"), pass_in, volume, format_volume_outline(vol) if vol else "", planning_model(state))
    storage.write_memory(name, mode, volume, "02-SOUL-INDEX.md", index)
    return index


def _writer_extra_cards(state: dict, chapter: dict) -> list[str]:
    cards = ["LNF-03v2-chapter-writer-probe-active.md"]
    pov = (state.get("styleConfig") or {}).get("povMode")
    if pov == "FIRST_PERSON_SOUL":
        cards.append("LNF-LP1-first-person.md")
    if pov == "TESTIMONY_MEMOIR" or re.search(r"interview|testimony|memoir|podcast", f"{chapter.get('momentGenre', '')} {chapter.get('title', '')}", re.I):
        cards.append("LNF-06-interview-and-testimony.md")
    return cards


def _voice_cards(name: str, state: dict) -> str:
    return "\n\n".join(x for x in (format_style_prompt(state.get("styleConfig")), storage.read_core(name, "03-AUTHOR-VOICE.md"),
                                   storage.read_core(name, "03-AUTHOR-VOICE-DNA.md")) if x)


def generate_chapter(name: str, state: dict, progress: Progress = no_progress) -> dict:
    vol = volume_plan(state)
    n = state["chaptersGeneratedInCurrentVolume"] + 1
    chapter = next((c for c in (vol or {}).get("chapters", []) if c["chapterNumber"] == n), None)
    if not vol or not chapter:
        raise ValueError(f"No chapter outline for Volume {state['currentVolume']}, Chapter {n}.")
    if state["currentVolume"] in (state.get("chaptersBeforePlan") or []):
        raise ValueError(f"Volume {state['currentVolume']} has chapters saved before the current plan was approved. Keep them or reset the volume first.")
    soul_index = ensure_soul_index(name, state, state["currentVolume"], progress)
    carry = carry_context(name, state, state["currentVolume"], n)
    progress(f"Writing Volume {state['currentVolume']}, Chapter {n}: \"{chapter['title']}\"...", 25)
    result = write_chapter({
        "chapter": chapter,
        "volumeNumber": state["currentVolume"],
        "standingCards": storage.standing_cards(name, _writer_extra_cards(state, chapter)),
        "styleLock": format_style_prompt(state.get("styleConfig")),
        "canon": "\n\n".join(x for x in (storage.read_core(name, "UNIVERSE-BIBLE.md"), storage.read_core(name, "AUTHOR-CLARIFICATIONS.md")) if x),
        "soulIndex": soul_index,
        "volumeArcMap": format_volume_outline(vol, n),
        "ledgerTail": carry["ledgerTail"],
        "previousChapterTail": carry["previousChapterTail"],
        "sourceMaterial": chapter_source_material(name, state, chapter),
        "seeds": "\n".join(f"- {s['setupDescription']}" for s in carry["seeds"]),
        "payoffs": "\n".join(f"- {p['payoffDescription']}" for p in carry["payoffs"]),
        "backgroundRef": carry["backgroundRef"],
    }, writing_model(state))
    progress("Running the three checks (voice, continuity, ledger)...", 85)
    result["auditStatus"] = audit_chapter(result["content"], result.get("ledgerEntry", ""), chapter, storage.read_core(name, "04-NO-DRIFT-NO-SLOP.md"),
                                          _voice_cards(name, state), soul_index, carry["ledgerTail"], planning_model(state))
    result["volumeNumber"] = state["currentVolume"]
    state["draft"] = result
    storage.save_state(name, state)
    progress(f"Chapter {n} written. Review it, then save, regenerate or discard.", 100)
    return state


def _upsert_section(doc: str, prefix: str, n: int, body: str) -> str:
    """Replaces (or inserts, in numeric order) the "<prefix>N" section of a markdown document."""
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)\s*$", re.M)
    matches = list(pattern.finditer(doc))
    head = doc[:matches[0].start()] if matches else doc
    sections: dict[int, str] = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(doc)
        sections[int(m.group(1))] = doc[m.start():end].rstrip()
    sections[n] = f"{prefix}{n}\n{body.strip()}"
    ordered = "\n\n".join(sections[k] for k in sorted(sections))
    return f"{head.rstrip()}{chr(10) * 2 if head.strip() else ''}{ordered}\n"


def save_draft(name: str, state: dict, title: str | None = None, content: str | None = None) -> dict:
    draft = state.get("draft")
    if not draft:
        raise ValueError("No chapter draft to save.")
    n = state["chaptersGeneratedInCurrentVolume"] + 1
    if draft.get("chapterNumber") != n or draft.get("volumeNumber") != state["currentVolume"]:
        raise ValueError(f"The draft is Volume {draft.get('volumeNumber')} Chapter {draft.get('chapterNumber')}, but the next chapter is "
                         f"Volume {state['currentVolume']} Chapter {n}. Discard it and write the chapter again.")
    mode, vol = state["mode"], state["currentVolume"]
    title = title if title is not None else draft["title"]
    content = content if content is not None else draft["content"]
    storage.save_chapter(name, mode, vol, n, title, content)
    if (draft.get("ledgerEntry") or "").strip():
        ledger = storage.read_memory(name, mode, vol, "CONTINUITY-LEDGER.md") or f"# CONTINUITY LEDGER - VOLUME {vol}\n"
        storage.write_memory(name, mode, vol, "CONTINUITY-LEDGER.md", _upsert_section(ledger, "### Chapter ", n, draft["ledgerEntry"]))
    if (draft.get("soulUpdates") or "").strip():
        index = storage.read_memory(name, mode, vol, "02-SOUL-INDEX.md")
        storage.write_memory(name, mode, vol, "02-SOUL-INDEX.md", _upsert_section(index, "## UPDATES AFTER CHAPTER ", n, draft["soulUpdates"]))
    if (draft.get("backgroundOverflow") or "").strip():
        storage.append_background(name, mode, vol, f"[From Chapter {n}: {title}]\n{draft['backgroundOverflow']}")
    state["draft"] = None
    state["chaptersGeneratedInCurrentVolume"] = n
    state["chaptersInCurrentPass"] = (state.get("chaptersInCurrentPass") or 0) + 1
    state["totalChaptersWritten"] = (state.get("totalChaptersWritten") or 0) + 1
    target = len((volume_plan(state) or {}).get("chapters") or []) or state["chaptersPerVolume"]
    state["chaptersPerVolume"] = target
    if n >= target:
        state["status"] = "HANDOFF_MODE"
    elif state["totalChaptersWritten"] % MILESTONE_EVERY == 0:
        state["status"] = "CHAPTER_REVIEW"
        state["milestoneNotice"] = f"{state['totalChaptersWritten']}-chapter milestone reached. Confirm before continuing."
    elif state["chaptersInCurrentPass"] >= 3:
        state["status"] = "CHAPTER_REVIEW"
    storage.save_state(name, state)
    return state


def discard_draft(name: str, state: dict) -> dict:
    state["draft"] = None
    storage.save_state(name, state)
    return state


def elevate_draft(name: str, state: dict, title: str, content: str, progress: Progress = no_progress) -> dict:
    mode, vol = state["mode"], state["currentVolume"]
    context = "\n\n".join(x for x in (storage.read_memory(name, mode, vol, "02-SOUL-INDEX.md"),
                                      tail(storage.read_memory(name, mode, vol, "CONTINUITY-LEDGER.md"), LEDGER_TAIL_CHARS)) if x)
    progress("Elevating the prose (same events, same canon)...", 20)
    res = elevate_chapter(title, content, storage.standing_cards(name, ["LNF-LPE-chapter-elevation.md"]), context, writing_model(state))
    if state.get("draft"):
        state["draft"].update(title=title, content=res["content"], elevationNotes=res["elevationNotes"])
        storage.save_state(name, state)
    progress("Elevated. Review the new text before saving.", 100)
    return state


def approve_pass(name: str, state: dict) -> dict:
    state["chaptersInCurrentPass"] = 0
    state["milestoneNotice"] = None
    state["status"] = "WRITING_MODE"
    storage.save_state(name, state)
    return state


def set_start_volume(name: str, state: dict, n: int) -> dict:
    vol = volume_plan(state, n)
    if not vol:
        raise ValueError(f"Volume {n} is not in the plan.")
    written = len(storage.list_chapters(name, state["mode"], n))
    if written >= len(vol["chapters"]):
        raise ValueError(f"Volume {n} is already fully written ({written}/{len(vol['chapters'])} chapters).")
    state.update(currentVolume=n, chaptersPerVolume=len(vol["chapters"]), chaptersGeneratedInCurrentVolume=written, chaptersInCurrentPass=0, draft=None)
    storage.save_state(name, state)
    return state


def reset_volume(name: str, state: dict, n: int) -> dict:
    """Clears a volume's writing so it can be rewritten from the current plan. Nothing is deleted: the
    chapters, the files written with them, a reconstructed PASS-IN and the volume summary move to
    _backups/<time>-reset-volume-N/. A real PASS-IN (handed off from a written volume) is kept."""
    if not volume_plan(state, n):
        raise ValueError(f"Volume {n} is not in the plan.")
    mode = state["mode"]
    backup = storage.new_backup_dir(name, f"reset-volume-{n}")
    (backup / "Chapters").mkdir()
    (backup / "Memory").mkdir()
    chapters = storage.list_chapters(name, mode, n)
    for c in chapters:
        (storage.chapters_dir(name, mode, n) / c["file"]).replace(backup / "Chapters" / c["file"])
    files = list(VOLUME_WRITING_MEMORY)
    if storage.read_memory(name, mode, n, "PASS-IN.md").startswith(RECONSTRUCTED_PASS_IN_MARK):
        files.append("PASS-IN.md")
    for f in files:
        p = storage.memory_path(name, mode, n, f)
        if p.exists():
            p.replace(backup / "Memory" / f)
    summary = storage.summary_path(name, mode, n)
    if summary.exists():
        summary.replace(backup / summary.name)
    state["totalChaptersWritten"] = max(0, (state.get("totalChaptersWritten") or 0) - len(chapters))
    state["chaptersBeforePlan"] = [v for v in state.get("chaptersBeforePlan") or [] if v != n]
    if state["currentVolume"] == n:
        state.update(chaptersGeneratedInCurrentVolume=0, chaptersInCurrentPass=0, draft=None)
        if state["status"] in ("CHAPTER_REVIEW", "HANDOFF_MODE"):
            state["status"] = "WRITING_MODE"
    state["lastReset"] = {"volume": n, "chapters": len(chapters), "backup": backup.name}
    storage.save_state(name, state)
    return state


def keep_volume_chapters(name: str, state: dict, n: int) -> dict:
    """The creators confirm a volume's earlier chapters still fit the current plan. The chapter counter follows
    the files on disk and the new outline (a volume that is already complete goes to the handoff)."""
    state["chaptersBeforePlan"] = [v for v in state.get("chaptersBeforePlan") or [] if v != n]
    if state["currentVolume"] == n:
        outline_len = len((volume_plan(state, n) or {}).get("chapters") or [])
        state["chaptersPerVolume"] = outline_len
        state["chaptersGeneratedInCurrentVolume"] = min(len(storage.list_chapters(name, state["mode"], n)), outline_len)
        state["draft"] = None
        if state["status"] == "WRITING_MODE" and outline_len and state["chaptersGeneratedInCurrentVolume"] >= outline_len:
            state["status"] = "HANDOFF_MODE"
    storage.save_state(name, state)
    return state


def handoff(name: str, state: dict, progress: Progress = no_progress) -> dict:
    """PASS-OUT from the full ledger, soul index, seed status and the final passage; PASS-IN and a fresh soul
    index for the next volume. A volume already written (e.g. tested early) keeps its chapters and index."""
    mode, vol = state["mode"], state["currentVolume"]
    ledger = storage.read_memory(name, mode, vol, "CONTINUITY-LEDGER.md")
    chapters = storage.list_chapters(name, mode, vol)
    nxt = volume_plan(state, vol + 1)
    progress(f"Building the Volume {vol} PASS-OUT from its ledger, character index and seeds...", 10)
    res = volume_pass_out(vol, ledger, storage.read_memory(name, mode, vol, "02-SOUL-INDEX.md"), seed_status_report(state),
                          (chapters[-1]["content"] if chapters else "")[-6000:], format_volume_outline(nxt) if nxt else "", planning_model(state))
    storage.write_memory(name, mode, vol, "PASS-OUT.md", res["passOutDoc"])
    chapter_blocks = re.sub(r"^# .*\n", "", ledger).strip()
    storage.save_summary(name, mode, vol, f"# Volume {vol} Summary\n\n{res['volumeSummary']}\n\n## Chapter Blocks\n\n{chapter_blocks}")
    state["lastHandoff"] = {"volume": vol, "passOut": res["passOutDoc"]}
    if not nxt:
        state["status"] = "COMPLETED"
        storage.save_state(name, state)
        progress("Final volume complete.", 100)
        return state
    n2 = vol + 1
    storage.write_memory(name, mode, n2, "PASS-IN.md", res["passOutDoc"])
    written = len(storage.list_chapters(name, mode, n2))
    if written == 0:
        storage.delete_memory(name, mode, n2, "02-SOUL-INDEX.md")
    state["currentVolume"] = n2
    state["chaptersPerVolume"] = len(nxt["chapters"])
    state["chaptersGeneratedInCurrentVolume"] = min(written, state["chaptersPerVolume"])
    state["chaptersInCurrentPass"] = 0
    state["status"] = "HANDOFF_MODE" if state["chaptersGeneratedInCurrentVolume"] >= state["chaptersPerVolume"] else "WRITING_MODE"
    # The handoff itself is saved before the next index is built, so a stop or failure there loses nothing
    storage.save_state(name, state)
    try:
        ensure_soul_index(name, state, n2, progress)
    except JobStopped:
        raise
    except Exception as err:  # noqa: BLE001 - not fatal: the next chapter rebuilds a missing index
        progress(f"Character index for Volume {n2} not built yet ({err}); it is built before the first chapter.", 90)
    progress("Handoff complete.", 100)
    return state


def subtlety_audit(name: str, state: dict, progress: Progress = no_progress) -> dict:
    vol = state["currentVolume"]
    seeds = [p for p in (state.get("payoffPlan") or {}).get("payoffs") or [] if p["setupVolume"] == vol]
    by_chapter: dict[int, list[dict]] = {}
    for s in seeds:
        by_chapter.setdefault(s["setupChapterNumber"], []).append(s)
    results = []
    for i, (n, chapter_seeds) in enumerate(sorted(by_chapter.items())):
        text = storage.chapter_text(name, state["mode"], vol, n)
        if not text:
            results += [{"chapterNumber": n, "threadName": s["threadName"], "found": False, "location": f"Chapter {n} not written yet",
                         "subtletyScore": 0, "firstTimeReaderNotice": "Pending", "revision": ""} for s in chapter_seeds]
            continue
        progress(f"Auditing the seeds planted in Chapter {n}...", round(i / max(1, len(by_chapter)) * 95))
        results += [{**a, "chapterNumber": n, "location": f"Chapter {n}: {a.get('location', '')}"} for a in audit_subtlety(n, text, chapter_seeds, planning_model(state))]
    scored = [r for r in results if r.get("found") and r.get("subtletyScore", 0) > 0]
    avg = round(sum(r["subtletyScore"] for r in scored) / len(scored), 1) if scored else 0
    state["subtletyAudit"] = {"overallVerdict": "PASS" if scored and all(r["subtletyScore"] >= 7 for r in scored) else ("NO_SEEDS" if not seeds else "NEEDS_REVISION"),
                              "averageSubtlety": avg, "seeds": results}
    storage.save_state(name, state)
    progress("Subtlety audit done.", 100)
    return state
