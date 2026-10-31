"""One panel per pipeline stage."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import events, ui

from .. import jobs, storage
from ..pipeline import common, ingest, writing
from ..pipeline.gaps import volume_gap
from ..styles import describe_chapter_range
from . import theme

if TYPE_CHECKING:
    from .universe import UniverseView


def render(view: "UniverseView") -> None:
    {
        "SORTING_MODE": sorting,
        "INGESTION_REVIEW": intake_review,
        "BIBLE_REVIEW": bible,
        "STYLE_LAB": style_lab,
        "BIN_REVIEW": bins_stage,
        "GAP_REVIEW": gap_fill,
        "OUTLINE_REVIEW": outline,
        "FORESHADOWING_MODE": payoff,
        "WRITING_MODE": writing_stage,
        "CHAPTER_REVIEW": review_pass,
        "HANDOFF_MODE": handoff,
        "COMPLETED": completed,
    }[view.state["status"]](view)


def _busy(view: "UniverseView") -> bool:
    return jobs.running(view.name)


# =====================================================================================
# 1. Ingestion
# =====================================================================================

def mess_manager(view: "UniverseView") -> None:
    st = view.state
    files = storage.get_mess_files(view.name)
    processed = {p["name"]: p for p in ((st.get("messSortResult") or {}).get("processedFiles") or [])}
    with ui.column().classes(f"{theme.PANEL} w-full gap-4"):
        with ui.row().classes("w-full items-center justify-between"):
            with ui.column().classes("gap-1"):
                ui.label("MESS folder").classes("text-lg font-bold text-white")
                ui.label("Drop the author's raw files here: notes, outlines, old drafts, finished volumes. .txt .md .json .docx .pdf "
                         "(.docx and .pdf are converted to text). Every file is sorted, one by one; nothing is sampled or skipped.").classes("text-xs text-slate-400 max-w-3xl")
            theme.badge(f"{len(files)} files", "slate")

        async def upload(e: events.UploadEventArguments) -> None:
            try:
                stored = storage.add_mess_file(view.name, e.file.name, await e.file.read())
                ui.notify(f"Added {stored}", type="positive")
            except ValueError as err:
                ui.notify(str(err), type="negative")

        with ui.row().classes("w-full items-center gap-3"):
            ui.upload(multiple=True, auto_upload=True, on_upload=upload, label="Add files to MESS (click + or drop files here)") \
                .props("dark bordered flat color=deep-purple-10").classes("grow")
            theme.button("Refresh file list", view.refresh_content, "secondary", icon="refresh", size="sm")
        with ui.column().classes("w-full gap-1"):
            for f in files:
                done = processed.get(f["name"])
                sorted_now = bool(done and done["size"] == len(f["content"]))
                with ui.row().classes("w-full items-center justify-between no-wrap bg-black/20 rounded-lg px-3 py-2 gap-3"):
                    with ui.row().classes("items-center gap-2 no-wrap"):
                        ui.icon("description").classes("text-purple-300")
                        ui.label(f["name"]).classes("text-sm text-slate-200 break-all")
                        ui.label(f"{len(f['content']):,} chars").classes("text-[11px] text-slate-500 whitespace-nowrap")
                    with ui.row().classes("items-center gap-2 no-wrap"):
                        pin = (st.get("volumePins") or {}).get(f["name"])
                        if pin:
                            theme.badge(f"Finished Volume {pin}", "teal")
                        if common.is_events_only(st, f["name"]):
                            theme.badge("events only", "amber")
                        theme.badge("sorted" if sorted_now else ("changed - will re-sort" if done else "not sorted yet"), "emerald" if sorted_now else "slate")
                        theme.button("", lambda _, n=f["name"]: (storage.delete_mess_file(view.name, n), view.refresh_content()), "ghost", icon="delete", size="sm") \
                            .tooltip("Remove from MESS")
        ui.label("Set a file as a finished volume or as events-only in Settings (top right).").classes("text-xs text-slate-500")


def sorting(view: "UniverseView") -> None:
    st = view.state
    partial = (st.get("messSortResult") or {}).get("processedFiles")
    with ui.column().classes(f"{theme.HERO} w-full gap-2"):
        theme.step_tag("Stage 1 • MESS Sorter (Card 08)")
        theme.heading("Ingest the author's notes", "Every MESS file is read page by page and sorted into characters (souls), world rules, arc beats, draft scenes "
                      "(copied word for word), voice samples and themes. Contradictions become questions for you.")
    mess_manager(view)
    with ui.row().classes("gap-3"):
        if partial:
            theme.button("Resume MESS Sort", lambda: view.act("INGEST"), "primary", icon="play_arrow", size="lg")
            theme.button("Start over (sort every file again)", lambda: view.confirm(
                "Sort every file again?", "This re-reads every MESS file from the start and replaces the current sort.", lambda: view.act("INGEST", {"fresh": True})), "secondary")
        else:
            theme.button("Start MESS Sort", lambda: view.act("INGEST"), "primary", icon="play_arrow", size="lg")


def intake_review(view: "UniverseView") -> None:
    sort = view.state.get("messSortResult") or {}
    counts = ingest.count_unclear(sort)
    with ui.column().classes(f"{theme.HERO} w-full gap-3"):
        theme.step_tag("Stage 2 • Review Intake")
        theme.heading("What the sorter found", "Check the sorted material. Questions are optional: answers become canon (AUTHOR-CLARIFICATIONS.md) for every later step.")
        with ui.row().classes("gap-8 mt-2"):
            for label, value in (("characters", len(sort.get("souls", []))), ("world rules", len(sort.get("worldRules", []))),
                                 ("arc beats", len(sort.get("arcBeats", []))), ("draft passages", len(sort.get("chapterMaterial", []))),
                                 ("voice samples", len(sort.get("voiceSamples", []))), ("open questions", counts["OPEN"])):
                theme.stat(label, value)
        with ui.row().classes("gap-3 mt-2"):
            theme.button("Approve Intake → Universe Bible", lambda: view.act("APPROVE_INGESTION"), "approve", icon="check_circle", size="lg")
            theme.button("Sort new or changed files", lambda: view.act("INGEST"), "secondary", icon="refresh")
            theme.button("Check open questions against all notes", lambda: view.act("RESOLVE_UNCLEAR"), "secondary", icon="fact_check")
    intake_tabs(view, sort)
    mess_manager(view)


def intake_tabs(view: "UniverseView", sort: dict) -> None:
    store = storage.get_sorted_material(view.name)
    with ui.column().classes(f"{theme.PANEL} w-full gap-2"):
        with ui.tabs().props("dense no-caps active-color=purple-4 indicator-color=purple-4").classes("text-slate-300") as tabs:
            t_q = ui.tab("Questions")
            t_s = ui.tab("Characters")
            t_r = ui.tab("World rules")
            t_b = ui.tab("Arc beats")
            t_d = ui.tab("Draft material")
        with ui.tab_panels(tabs, value=t_q).classes("w-full bg-transparent"):
            with ui.tab_panel(t_q):
                questions_panel(view, sort)
            with ui.tab_panel(t_s):
                for s in sort.get("souls", []):
                    with ui.expansion(s["name"] + (f"  (aka {', '.join(s['aliases'])})" if s.get("aliases") else "")).classes("w-full text-slate-200"):
                        theme.long_text("\n\n".join(f"{k}: {s.get(k, '')}" for k in common.SOUL_FIELDS) + f"\n\nSources: {'; '.join(s.get('sources') or [])}", mono=True)
            with ui.tab_panel(t_r):
                for r in sort.get("worldRules", []):
                    with ui.expansion(r["ruleName"]).classes("w-full text-slate-200"):
                        theme.long_text(f"{r['description']}\n\nConstraint: {r['constraint']}\n\nSources: {'; '.join(r.get('sources') or [])}", mono=True)
            with ui.tab_panel(t_b):
                with ui.column().classes("w-full gap-1 max-h-[60vh] overflow-y-auto"):
                    for b in sort.get("arcBeats", []):
                        with ui.row().classes("w-full gap-2 no-wrap text-xs"):
                            ui.label(b["id"]).classes("text-purple-300 font-mono w-14 shrink-0")
                            ui.label(f"({b.get('phase') or '-'}) {b['event']} → {b['irreversibleChange']}").classes("text-slate-200")
                            ui.label(b.get("source", "")).classes("text-slate-500 whitespace-nowrap")
            with ui.tab_panel(t_d):
                for m in sort.get("chapterMaterial", []):
                    item = store["items"].get(m["id"], {})
                    with ui.expansion(f"{m['id']}  {m['content'][:110]}").classes("w-full text-slate-200"):
                        anchor = item.get("anchor") or ("exact" if item.get("verbatim") else "missing")
                        note = {"exact": "verbatim", "open-end": "verbatim from its start to the end of the page (its end quote did not match - check where it ends)",
                                "missing": "only the sorter's quotes (its start quote did not match the page)"}[anchor]
                        ui.label(f"{m.get('source', '')} • {note}").classes(f"text-[11px] {'text-slate-500' if anchor == 'exact' else 'text-amber-300'}")
                        theme.long_text(item.get("text", ""))


def questions_panel(view: "UniverseView", sort: dict) -> None:
    open_items = [u for u in sort.get("unclear", []) if u.get("status", "OPEN") in ("OPEN", "ANSWERED")]
    resolved = [u for u in sort.get("unclear", []) if u.get("status") == "RESOLVED"]
    if not open_items:
        ui.label("No open questions.").classes("text-sm text-slate-400")
    inputs = {}
    for u in open_items:
        with ui.column().classes(f"{theme.SUBPANEL} w-full gap-1"):
            ui.label(f"[{u['id']}] {u['question']}").classes("text-sm text-white font-semibold")
            ui.label(f"“{u['quote']}” — {u.get('source', '')}").classes("text-xs text-slate-400 italic")
            inputs[u["id"]] = theme.text_area("Your answer (optional)", u.get("answer") or "", rows=2)
    if open_items:
        theme.button("Save answers", lambda: view.act("ANSWER_UNCLEAR", {"answers": {k: v.value for k, v in inputs.items()}}), "primary", size="sm")
    if resolved:
        with ui.expansion(f"{len(resolved)} answered from the notes automatically").classes("w-full text-slate-300"):
            for u in resolved:
                ui.label(f"[{u['id']}] {u['question']} → {u.get('answer', '')}").classes("text-xs text-slate-400")


# =====================================================================================
# 3. Bible
# =====================================================================================

def bible(view: "UniverseView") -> None:
    st = view.state
    with ui.column().classes(f"{theme.HERO} w-full gap-3"):
        theme.step_tag("Stage 3 • Universe Bible & Soul Roster")
        theme.heading("Canon", "The identity check merges entries for the same person and separates notes that mix two people, then the Universe Bible, "
                      "Soul Roster and Arc Map are written to SHARED_CORE_KNOWLEDGE.")
        with ui.row().classes("gap-3"):
            if st.get("soulRoster"):
                theme.button("Approve Bible → Style Lab", lambda: view.act("APPROVE_BIBLE"), "approve", icon="check_circle", size="lg")
                theme.button("Rebuild Bible & Roster", lambda: view.act("GENERATE_BIBLE"), "secondary", icon="refresh")
            else:
                theme.button("Build Universe Bible", lambda: view.act("GENERATE_BIBLE"), "primary", icon="auto_stories", size="lg")
    if not st.get("universeBible"):
        return
    b = st["universeBible"]
    with ui.column().classes(f"{theme.PANEL} w-full gap-2"):
        ui.label("Core premise").classes("text-xs uppercase tracking-wider text-slate-400")
        ui.label(b.get("corePremise", "")).classes("text-slate-200")
        ui.label("Civilizational model").classes("text-xs uppercase tracking-wider text-slate-400 mt-2")
        ui.label(b.get("civilizationalModel", "")).classes("text-slate-200")
        with ui.expansion(f"World rules ({len(b.get('worldRules') or [])})").classes("w-full text-slate-200"):
            for r in b.get("worldRules") or []:
                ui.label(r["ruleName"]).classes("font-semibold text-purple-300 text-sm")
                ui.label(f"{r['description']} Constraint: {r['constraint']}").classes("text-xs text-slate-300 mb-2")
    roster = (st.get("soulRoster") or {}).get("souls") or []
    with ui.column().classes(f"{theme.PANEL} w-full gap-2"):
        ui.label(f"Soul Roster ({len(roster)} characters)").classes("text-lg font-bold text-white")
        for s in roster:
            with ui.expansion(s["name"] + (f"  (aka {', '.join(s['aliases'])})" if s.get("aliases") else "")).classes("w-full text-slate-200"):
                for k, label in (("essence", "Essence"), ("woundsAndDesires", "Wounds / desires"), ("relationships", "Relationships"),
                                 ("speechHabits", "Speech"), ("continuityTripwire", "Continuity tripwire")):
                    ui.label(f"{label}: {s.get(k, '')}").classes("text-xs text-slate-300")
        with ui.row().classes("items-end gap-2 w-full mt-2"):
            entries = theme.text_input("Repair characters: names whose notes mix two people (comma-separated; empty = automatic)")
            theme.button("Repair", lambda: view.act("REPAIR_SOULS", {"entries": [e.strip() for e in (entries.value or "").split(",") if e.strip()] or None}),
                         "secondary", icon="healing", size="sm")


# =====================================================================================
# 4. Style Lab
# =====================================================================================

def style_lab(view: "UniverseView") -> None:
    st = view.state
    lab = st.get("styleLab") or {}
    cands = lab.get("candidates") or []
    with ui.column().classes(f"{theme.HERO} w-full gap-3"):
        theme.step_tag("Stage 4 • Style Lab (LNF-VOICE / LNF-FORGE)")
        theme.heading("Find the author style", "Generate candidate styles, compare their test passages of the same scene, refine them with your feedback "
                      "until one is right, then lock it. The locked voice is used for every chapter of every volume.")
        scene = theme.text_area("Test scene (every candidate writes this same scene)", lab.get("sceneBrief") or "", rows=2)
        notes = theme.text_area("Notes for every new candidate (e.g. less telling, more physical, shorter sentences)", lab.get("creatorNotes") or "", rows=2)
        with ui.row().classes("gap-3"):
            theme.button("Generate style candidates" if not cands else "Generate new candidates",
                         lambda: view.act("STYLE_GENERATE", {"sceneBrief": scene.value or "", "notes": notes.value or ""}), "primary", icon="auto_awesome", size="lg")
            theme.button("Save notes", lambda: view.act("STYLE_SET_NOTES", {"notes": notes.value or ""}),
                         "secondary", icon="save", size="lg")
            if cands:
                theme.button("Rewrite all test passages on this scene", lambda: view.act("STYLE_RESAMPLE", {"sceneBrief": scene.value or ""}), "secondary", icon="refresh")
    if not cands:
        ui.label("Events-only files never teach the voice. If the author's own prose is in MESS, the first candidate is their extracted Voice DNA.").classes("text-xs text-slate-500")
        return
    origin = {"AUTHOR": ("Author's own voice", "teal"), "POLISHED": ("Polished author voice", "purple"), "UNIQUE": ("Unique voice", "blue")}
    with ui.element("div").classes("grid grid-cols-1 xl:grid-cols-3 gap-5 w-full"):
        for c in cands:
            locked = lab.get("lockedId") == c["id"]
            with ui.column().classes(f"{theme.PANEL} gap-3 {'border-emerald-500/50' if locked else ''}"):
                with ui.row().classes("w-full items-center justify-between no-wrap"):
                    ui.label(c["name"]).classes("text-lg font-bold text-white")
                    label, tone = origin.get(c.get("origin"), ("Candidate", "slate"))
                    theme.badge("LOCKED" if locked else label, "emerald" if locked else tone)
                ui.label(c.get("pitch", "")).classes("text-xs text-slate-300 italic")
                ui.label(c.get("overallVoiceSummary", "")).classes("text-xs text-slate-300")
                with ui.expansion("Voice DNA (9 dimensions)").classes("w-full text-slate-300 text-xs"):
                    for key, title in (("sentenceRhythm", "Rhythm"), ("diction", "Diction"), ("paragraphShape", "Paragraphs"), ("dialogueAttribution", "Dialogue"),
                                       ("interiorityDepth", "Interiority"), ("sensoryPriority", "Senses"), ("timeHandling", "Time"),
                                       ("chapterOpeningClosing", "Openings/closings"), ("signatureMoves", "Signature moves"), ("neverDoes", "Never does")):
                        ui.label(f"{title}: {c.get(key, '')}").classes("text-[11px] text-slate-400")
                ui.label("Test passage").classes("text-[11px] uppercase tracking-wider text-slate-400")
                theme.long_text(c.get("sample", ""), max_h="max-h-[28rem]")
                fb = theme.text_area("What should change?", rows=2)
                with ui.row().classes("gap-2"):
                    theme.button("Refine", lambda _, cid=c["id"], w=fb: view.act("STYLE_REFINE", {"id": cid, "feedback": w.value or ""}), "secondary", icon="edit", size="sm")
                    theme.button("Lock this style → Volume Bins", lambda _, cid=c["id"], n=c["name"]: view.confirm(
                        "Lock this style?", f'"{n}" becomes the author voice for every chapter (03-AUTHOR-VOICE-DNA.md). You can come back and change it later.',
                        lambda: view.act("STYLE_LOCK", {"id": cid}), "Lock style"), "approve", icon="lock", size="sm")


# =====================================================================================
# 5. Volume bins
# =====================================================================================

def settings_summary(view: "UniverseView") -> None:
    st = view.state
    pins = st.get("volumePins") or {}
    with ui.row().classes(f"{theme.SUBPANEL} w-full items-center justify-between"):
        with ui.column().classes("gap-1 text-xs text-slate-300"):
            ui.label(f"Volumes: {st.get('targetVolumes') or 'decided by the engine'} • Chapters per volume: "
                     f"{describe_chapter_range(st.get('chapterRange')) or 'decided by the material'}")
            ui.label("Finished volumes: " + (", ".join(f"V{v} = {f}" for f, v in sorted(pins.items(), key=lambda x: x[1])) or "none"))
        theme.button("Edit settings", view.settings_dialog, "purple", icon="tune", size="sm")


def bins_overview(view: "UniverseView", editable: bool) -> None:
    st = view.state
    bins = st.get("bins") or {}
    idx = common.item_index(st, storage.get_sorted_material(view.name))
    fixed = bins.get("fixed") or {}
    assumed = set(bins.get("assumed") or [])
    options = {0: "Out of the volumes", **{v["volumeNumber"]: f"Volume {v['volumeNumber']}" for v in bins.get("volumes", [])}}
    for v in bins.get("volumes", []):
        n = v["volumeNumber"]
        beats = sum(1 for i in v["itemIds"] if i.startswith("B-"))
        drafts = len(v["itemIds"]) - beats
        title = f"Volume {n}: {v['title']}  •  {beats} beat{'' if beats == 1 else 's'}, {drafts} draft{'' if drafts == 1 else 's'}" + (f"  •  FINISHED ({', '.join(v['pinnedFrom'])})" if v.get("pinnedFrom") else "")
        with ui.expansion(title, value=editable and n == 1).classes(f"w-full {theme.SUBPANEL} text-slate-100"):
            if editable:
                t = theme.text_input("Title", v["title"])
                p = theme.text_area("Premise", v["premise"], rows=2)
                s = theme.text_area("Summary", v["summary"], rows=4)
                theme.button("Save volume text", lambda _, n=n, t=t, p=p, s=s: view.act("EDIT_VOLUME", {"volume": n, "title": t.value, "premise": p.value, "summary": s.value}),
                             "secondary", size="sm")
            else:
                ui.label(v["premise"]).classes("text-xs text-slate-300")
                ui.label(v["summary"]).classes("text-xs text-slate-400 whitespace-pre-wrap")
            if not v["itemIds"]:
                ui.label("No author material in this volume yet - it will be filled by gap-fill.").classes("text-xs text-amber-300")
            for i in v["itemIds"]:
                it = idx.get(i, {})
                with ui.row().classes("w-full items-center gap-2 no-wrap text-xs border-t border-white/5 py-1"):
                    ui.label(i).classes("text-purple-300 font-mono w-14 shrink-0")
                    theme.badge("beat" if it.get("kind") == "BEAT" else "draft", "purple" if it.get("kind") == "BEAT" else "blue")
                    ui.label(it.get("summary", "")[:220]).classes("text-slate-200 flex-1")
                    if i in fixed:
                        theme.badge("fixed", "teal").tooltip(fixed[i])
                    elif i in assumed:
                        theme.badge("placed by inference", "amber")
                    ui.label(it.get("source", "")).classes("text-slate-500 whitespace-nowrap")
                    if editable:
                        theme.select(options, value=n, width="w-44").on_value_change(
                            lambda e, i=i: view.act("MOVE_ITEM", {"id": i, "toVolume": e.value or None}))
    if bins.get("unplaced"):
        with ui.expansion(f"Not story content / not placed ({len(bins['unplaced'])})").classes(f"w-full {theme.SUBPANEL} text-slate-300"):
            for i in bins["unplaced"]:
                it = idx.get(i, {})
                with ui.row().classes("w-full items-center gap-2 no-wrap text-xs"):
                    ui.label(i).classes("text-purple-300 font-mono w-14")
                    ui.label(it.get("summary", "")[:220]).classes("text-slate-300 flex-1")
                    if editable:
                        theme.select(options, value=0, width="w-44").on_value_change(lambda e, i=i: view.act("MOVE_ITEM", {"id": i, "toVolume": e.value or None}))


def bins_stage(view: "UniverseView") -> None:
    st = view.state
    has = bool(st.get("bins"))
    with ui.column().classes(f"{theme.HERO} w-full gap-3"):
        theme.step_tag("Stage 5 • Volume Bins")
        theme.heading("Place every item in its volume", "The number of volumes is yours and never changes. A finished volume stays whole. Volume numbers the author "
                      "wrote in the notes are kept. Everything else goes where its events belong - no balancing: a thin volume is filled in the next "
                      "stage with mini-events you confirm. Move any item by hand if it belongs elsewhere.")
        settings_summary(view)
        with ui.row().classes("gap-3"):
            if has:
                theme.button("Approve Bins → Gap-Fill", lambda: view.act("APPROVE_BINS"), "approve", icon="check_circle", size="lg")
                theme.button("Rebuild bins", lambda: view.confirm(
                    "Rebuild the volume bins?", "This places every item again from the current settings. Any gap-fill and outlines built on the old bins are "
                    "saved to _backups and cleared.", lambda: view.act("BUILD_BINS")), "secondary", icon="refresh")
            else:
                theme.button("Build volume bins", lambda: view.act("BUILD_BINS"), "primary", icon="layers", size="lg")
    if has:
        with ui.column().classes(f"{theme.PANEL} w-full gap-2"):
            bins_overview(view, editable=True)


# =====================================================================================
# 6. Gap-fill
# =====================================================================================

GAP_STATUS = {"PENDING": ("not run", "slate"), "PROPOSED": ("needs your review", "amber"), "CONFIRMED": ("confirmed", "emerald"),
              "FINISHED": ("finished volume", "teal")}


def gap_fill(view: "UniverseView") -> None:
    st = view.state
    vols = (st.get("bins") or {}).get("volumes", [])
    statuses = [volume_gap(st, v["volumeNumber"])["status"] for v in vols]
    with ui.column().classes(f"{theme.HERO} w-full gap-3"):
        theme.step_tag("Stage 6 • Gap-Fill (Card 05)")
        theme.heading("Fill what is missing, with your confirmation", "For each volume the assistant fixes where the story stands as it opens and the "
                      "author's main events in it, then proposes the mini-events that compound toward them by cause and effect. It never invents a new main "
                      "event or world rule - it asks you instead. Accept, edit, reject or add mini-events, answer its questions, then confirm each volume.")
        with ui.row().classes("gap-6"):
            for key, (label, _) in GAP_STATUS.items():
                theme.stat(label, statuses.count(key))
        with ui.row().classes("gap-3"):
            if any(s == "PENDING" for s in statuses):
                theme.button("Run gap-fill for all volumes", lambda: view.act("GAP_RUN"), "primary", icon="auto_fix_high", size="lg")
            if statuses and all(s in ("CONFIRMED", "FINISHED") for s in statuses):
                theme.button("Approve Gap-Fill → Volume Outline", lambda: view.act("APPROVE_GAPS"), "approve", icon="check_circle", size="lg")
    store = storage.get_sorted_material(view.name)
    idx = common.item_index(st, store)
    for v in vols:
        n = v["volumeNumber"]
        gv = volume_gap(st, n)
        label, tone = GAP_STATUS[gv["status"]]
        accepted = sum(1 for e in gv["miniEvents"] if e["status"] == "ACCEPTED")
        with ui.expansion(f"Volume {n}: {v['title']}  •  {label}  •  {accepted} mini-events accepted",
                          value=gv["status"] == "PROPOSED").classes(f"w-full {theme.PANEL} text-slate-100"):
            gap_volume(view, n, v, gv, idx)


def gap_volume(view: "UniverseView", n: int, v: dict, gv: dict, idx: dict) -> None:
    if gv["status"] == "FINISHED":
        ui.label("This is a finished volume (its file is pinned in Settings), so it needs no gap-fill.").classes("text-sm text-teal-300")
        theme.button("Run gap-fill for this volume anyway", lambda: view.act("GAP_RUN", {"volumes": [n], "includeFinished": True}), "secondary", size="sm")
        return
    if gv["status"] == "PENDING":
        theme.button(f"Run gap-fill for Volume {n}", lambda: view.act("GAP_RUN", {"volumes": [n]}), "primary", size="sm")
        return
    if gv.get("volumeStart"):
        ui.label(f"Where the volume opens: {gv['volumeStart']}").classes("text-xs text-slate-300")
    if gv.get("mainEvents"):
        ui.label("Main events (the author's)").classes("text-[11px] uppercase tracking-wider text-slate-400 mt-1")
        for m in gv["mainEvents"]:
            ui.label(f"• [{m.get('ref', '')}] {m.get('event', '')}").classes("text-xs text-slate-200")
    ui.label("Mini-events (proposed in story order)").classes("text-[11px] uppercase tracking-wider text-slate-400 mt-2")
    tones = {"ACCEPTED": "emerald", "REJECTED": "red", "PROPOSED": "amber"}
    for e in gv["miniEvents"]:
        with ui.column().classes(f"{theme.SUBPANEL} w-full gap-1 {'opacity-50' if e['status'] == 'REJECTED' else ''}"):
            with ui.row().classes("w-full items-center justify-between no-wrap"):
                with ui.row().classes("items-center gap-2"):
                    ui.label(e["id"]).classes("font-mono text-purple-300 text-xs")
                    ui.label(e["title"]).classes("text-sm font-semibold text-white")
                    theme.badge(e["status"].lower(), tones[e["status"]])
                    theme.badge(e.get("kind", "").lower(), "slate")
                    if e.get("origin") == "CREATORS":
                        theme.badge("yours", "teal")
                    if e.get("needsDecision"):
                        theme.badge("creative decision", "amber").tooltip(e.get("decisionNote", ""))
                with ui.row().classes("gap-1 no-wrap"):
                    theme.button("Accept", lambda _, i=e["id"]: view.act("GAP_SET_STATUS", {"volume": n, "id": i, "status": "ACCEPTED"}), "secondary", size="sm")
                    theme.button("Reject", lambda _, i=e["id"]: view.act("GAP_SET_STATUS", {"volume": n, "id": i, "status": "REJECTED"}), "secondary", size="sm")
                    theme.button("Edit", lambda _, ev=e: edit_event_dialog(view, n, ev), "secondary", size="sm")
            ui.label(e["event"]).classes("text-xs text-slate-200")
            ui.label(f"Cause: {e.get('cause', '')}  •  Effect: {e.get('effect', '')}  •  Leads to: {e.get('leadsTo', '')} "
                     f"{('(' + idx[e['leadsTo']]['summary'][:80] + ')') if e.get('leadsTo') in idx else ''}").classes("text-[11px] text-slate-400")
            if e.get("needsDecision") and e.get("decisionNote"):
                ui.label(f"Your decision: {e['decisionNote']}").classes("text-[11px] text-amber-300")
    with ui.expansion("Add your own mini-event").classes("w-full text-slate-300"):
        t = theme.text_input("Title")
        ev = theme.text_area("What happens", rows=2)
        with ui.grid(columns=3).classes("w-full gap-2"):
            cause = theme.text_input("Cause")
            effect = theme.text_input("Effect")
            leads = theme.text_input("Leads to (main event id)")
        theme.button("Add mini-event", lambda: view.act("GAP_ADD", {"volume": n, "fields": {"title": t.value, "event": ev.value, "cause": cause.value,
                                                                                           "effect": effect.value, "leadsTo": leads.value}}), "secondary", size="sm")
    if gv["questions"]:
        ui.label("Questions for you").classes("text-[11px] uppercase tracking-wider text-slate-400 mt-2")
        for q in gv["questions"]:
            with ui.column().classes(f"{theme.SUBPANEL} w-full gap-1"):
                ui.label(f"[{q['id']}] {q['question']}").classes("text-sm text-white")
                if q.get("why"):
                    ui.label(q["why"]).classes("text-[11px] text-slate-400")
                a = theme.text_area("Your answer", q.get("answer") or "", rows=2)
                theme.button("Save answer", lambda _, qid=q["id"], a=a: view.act("GAP_ANSWER", {"volume": n, "id": qid, "answer": a.value or ""}), "secondary", size="sm")
    notes = theme.text_area("Notes for regenerating this volume's proposals (kept mini-events stay)", gv.get("notes") or "", rows=2)
    with ui.row().classes("gap-2 mt-2"):
        theme.button("Regenerate proposals", lambda: (view.act("GAP_NOTES", {"volume": n, "notes": notes.value or ""}), view.act("GAP_RUN", {"volumes": [n]})),
                     "secondary", icon="refresh", size="sm")
        if gv["status"] == "CONFIRMED":
            theme.button("Reopen", lambda: view.act("GAP_REOPEN", {"volume": n}), "secondary", size="sm")
        else:
            pending = sum(1 for e in gv["miniEvents"] if e["status"] == "PROPOSED")
            if pending:
                theme.button(f"Accept the {pending} remaining & confirm Volume {n}", lambda: view.act("GAP_CONFIRM", {"volume": n, "acceptRemaining": True}), "approve", size="sm")
            else:
                theme.button(f"Confirm Volume {n}", lambda: view.act("GAP_CONFIRM", {"volume": n}), "approve", size="sm")


def edit_event_dialog(view: "UniverseView", n: int, e: dict) -> None:
    with ui.dialog() as dlg, ui.card().classes("w-[680px] p-6 gap-3"):
        ui.label(f"Edit {e['id']}").classes("text-lg font-bold text-white")
        t = theme.text_input("Title", e.get("title", ""))
        ev = theme.text_area("What happens", e.get("event", ""), rows=3)
        cause = theme.text_input("Cause", e.get("cause", ""))
        effect = theme.text_input("Effect", e.get("effect", ""))
        leads = theme.text_input("Leads to", e.get("leadsTo", ""))
        with ui.row().classes("justify-end w-full gap-2"):
            theme.button("Cancel", dlg.close, "ghost")
            theme.button("Save", lambda: (dlg.close(), view.act("GAP_EDIT", {"volume": n, "id": e["id"], "fields": {
                "title": t.value, "event": ev.value, "cause": cause.value, "effect": effect.value, "leadsTo": leads.value}})), "primary")
    dlg.open()


# =====================================================================================
# 7. Outline
# =====================================================================================

def outline(view: "UniverseView") -> None:
    st = view.state
    plan = st.get("plan")
    vols = (plan or {}).get("volumes", [])
    done = [v for v in vols if v.get("chapters")]
    with ui.column().classes(f"{theme.HERO} w-full gap-3"):
        theme.step_tag("Stage 7 • Volume Outline")
        theme.heading("Chapter outlines", "Each volume is outlined from its bin and its confirmed mini-events, inside your chapters-per-volume range "
                      f"({describe_chapter_range(st.get('chapterRange')) or 'set by the material'}). Every chapter lists the sources it draws from.")
        with ui.row().classes("gap-3"):
            if vols and len(done) == len(vols):
                theme.button("Approve Plan → Payoff Planner", lambda: view.act("APPROVE_PLAN"), "approve", icon="check_circle", size="lg")
                theme.button("Outline everything again", lambda: view.confirm("Outline every volume again?", "All current outlines are replaced.",
                                                                              lambda: view.act("OUTLINE_RUN")), "secondary", icon="refresh")
            elif vols:
                theme.button(f"Continue outlining ({len(done)}/{len(vols)} volumes done)", lambda: view.act("OUTLINE_RUN", {"resume": True}), "primary", icon="play_arrow", size="lg")
            else:
                theme.button("Generate chapter outlines", lambda: view.act("OUTLINE_RUN"), "primary", icon="list_alt", size="lg")
    for v in vols:
        with ui.expansion(f"Volume {v['volumeNumber']}: {v['title']}  •  {len(v.get('chapters') or [])} chapters").classes(f"w-full {theme.PANEL} text-slate-100"):
            if v.get("chapterCountReason"):
                ui.label(f"Chapter count: {v['chapterCountReason']}").classes("text-[11px] text-slate-400")
            for c in v.get("chapters") or []:
                with ui.column().classes(f"{theme.SUBPANEL} w-full gap-1"):
                    ui.label(f"Chapter {c['chapterNumber']}: {c['title']}").classes("text-sm font-semibold text-white")
                    ui.label(c["synopsis"]).classes("text-xs text-slate-300")
                    ui.label(f"{c.get('pacingType', '')} • {c.get('momentGenre', '')} • Focal: {c.get('focalSoul', '')} • {c.get('timeCoordinate', '')}"
                             + (f" • Sources: {', '.join(c['sourceRefs'])}" if c.get("sourceRefs") else "")).classes("text-[11px] text-slate-500")
            theme.button(f"Outline Volume {v['volumeNumber']} again", lambda _, n=v["volumeNumber"]: view.act("OUTLINE_VOLUME", {"volume": n}), "secondary", size="sm")


# =====================================================================================
# 8. Payoff
# =====================================================================================

def payoff(view: "UniverseView") -> None:
    st = view.state
    plan = st.get("payoffPlan")
    with ui.column().classes(f"{theme.HERO} w-full gap-3"):
        theme.step_tag("Stage 8 • Payoff & Foreshadowing (Card 06)")
        theme.heading("Setups and payoffs", "Threads the author's material implies are marked AUTHOR; additions by the planner are INFERRED. Each seed is "
                      "planted, as innocent texture, in the exact chapter it names.")
        with ui.row().classes("gap-3"):
            if plan:
                theme.button("Approve Payoff Plan → Writing", lambda: view.act("APPROVE_PAYOFF"), "approve", icon="check_circle", size="lg")
                theme.button("Plan again", lambda: view.act("PAYOFF_RUN"), "secondary", icon="refresh")
            else:
                theme.button("Generate payoff plan", lambda: view.act("PAYOFF_RUN"), "primary", icon="hub", size="lg")
        start_volume_picker(view)
    if not plan:
        return
    threads = plan["payoffs"]
    total = st.get("totalVolumes") or 0
    with ui.column().classes(f"{theme.PANEL} w-full gap-2"):
        ui.label(f"{len(threads)} threads • {sum(1 for p in threads if p['origin'] == 'AUTHOR')} from the author's material"
                 + (f" • {plan['dropped']} dropped (pointed at chapters that do not exist)" if plan.get("dropped") else "")).classes("text-sm text-slate-300")
        spread = "   ".join(f"V{v}: {sum(1 for p in threads if p['setupVolume'] == v)}/{sum(1 for p in threads if p['payoffVolume'] == v)}" for v in range(1, total + 1))
        ui.label(f"Setups / payoffs per volume:  {spread}").classes("lp-mono text-[11px] text-slate-400")
        ui.label(plan.get("overallStrategy", "")).classes("text-xs text-slate-300 mt-1")
        for p in threads:
            with ui.column().classes(f"{theme.SUBPANEL} w-full gap-1"):
                with ui.row().classes("items-center gap-2"):
                    ui.label(p["threadName"]).classes("text-sm font-semibold text-white")
                    theme.badge(p["origin"], "teal" if p["origin"] == "AUTHOR" else "slate")
                ui.label(f"Plant V{p['setupVolume']} Ch{p['setupChapterNumber']}: {p['setupDescription']}").classes("text-xs text-slate-300")
                ui.label(f"Payoff V{p['payoffVolume']} Ch{p['payoffChapterNumber']}: {p['payoffDescription']}").classes("text-xs text-slate-400")


def start_volume_picker(view: "UniverseView") -> None:
    st = view.state
    vols = (st.get("plan") or {}).get("volumes", [])
    if len(vols) < 2:
        return
    with ui.row().classes(f"{theme.SUBPANEL} w-full items-center justify-between gap-3"):
        with ui.column().classes("gap-0"):
            ui.label(f"Writing volume: Volume {st['currentVolume']} ({st['chaptersGeneratedInCurrentVolume']}/{st['chaptersPerVolume']} chapters saved)").classes("text-xs text-white font-semibold")
            ui.label("Start at any volume. If earlier volumes were not written here, their planned events are used as the story so far.").classes("text-[11px] text-slate-500")
        theme.select({v["volumeNumber"]: f"Volume {v['volumeNumber']}: {v['title']}" for v in vols}, value=st["currentVolume"], width="w-96") \
            .on_value_change(lambda e: view.act("SET_START_VOLUME", {"volume": e.value}) if e.value != view.state["currentVolume"] else None)


# =====================================================================================
# 9-10. Writing loop
# =====================================================================================

def volume_panels(view: "UniverseView") -> None:
    """Saved chapters of the current volume, and what the next chapter carries in (exactly what the writer gets)."""
    st = view.state
    vol_n = st["currentVolume"]
    vol = writing.volume_plan(st, vol_n) or {}
    chapters = storage.list_chapters(view.name, st["mode"], vol_n)
    nxt = st["chaptersGeneratedInCurrentVolume"] + 1
    outline_ch = next((c for c in vol.get("chapters", []) if c["chapterNumber"] == nxt), None)
    with ui.element("div").classes("grid grid-cols-1 xl:grid-cols-2 gap-6 w-full"):
        with ui.column().classes(f"{theme.PANEL} gap-2"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(f"Chapters in Volume {vol_n}").classes("text-sm font-bold text-white")
                ui.label(f"{len(chapters)} / {len(vol.get('chapters', []))} saved").classes("text-xs text-slate-400")
            if not chapters:
                ui.label("No chapters saved in this volume yet.").classes("text-xs text-slate-400")
            for c in chapters:
                words = len(c["content"].split())
                with ui.expansion(f"{c['file'].removesuffix('.txt')}  •  {words:,} words").classes("w-full text-slate-200"):
                    theme.long_text(c["content"], max_h="max-h-[32rem]")
        with ui.column().classes(f"{theme.PANEL} gap-2"):
            if not outline_ch:
                ui.label("Carried forward").classes("text-sm font-bold text-white")
                ui.label("Every chapter of this volume is saved. The memory handoff carries it into the next volume.").classes("text-xs text-slate-400")
                return
            carry = writing.carry_context(view.name, st, vol_n, nxt)
            ui.label(f"Carried into Chapter {nxt}: {outline_ch['title']}").classes("text-sm font-bold text-white")
            ui.label("Exactly what the writer receives from the earlier chapters, with the standing cards and the Universe Bible.").classes("text-[11px] text-slate-400")
            with ui.column().classes(f"{theme.SUBPANEL} w-full gap-1"):
                ui.label(f"Outline: {outline_ch['synopsis']}").classes("text-xs text-slate-200")
                ui.label(f"Focal: {outline_ch.get('focalSoul', '')} • {outline_ch.get('timeCoordinate', '')} • Sources: {len(outline_ch.get('sourceRefs') or [])}").classes("text-[11px] text-slate-500")
            with ui.column().classes(f"{theme.SUBPANEL} w-full gap-1"):
                ui.label(f"Foreshadowing seeds to plant ({len(carry['seeds'])})").classes("text-xs font-semibold text-slate-200")
                for s in carry["seeds"]:
                    ui.label(f"{s['threadName']}: {s['setupDescription']}").classes("text-xs text-purple-200")
            soul_index = storage.read_memory(view.name, st["mode"], vol_n, "02-SOUL-INDEX.md")
            at = soul_index.find("## UPDATES AFTER CHAPTER ")
            for title, body, note in ((f"End of Chapter {nxt - 1}" if nxt > 1 else "End of the previous volume", carry["previousChapterTail"], "last ~3,000 chars"),
                                      ("Continuity ledger", carry["ledgerTail"], "last ~8,000 chars"),
                                      ("Character updates from saved chapters", soul_index[at:] if at >= 0 else "", ""),
                                      ("Full character index (sent whole)", soul_index, ""),
                                      ("Background details", carry["backgroundRef"], "last ~6,000 chars"),
                                      ("Author source material + confirmed mini-events", writing.chapter_source_material(view.name, st, outline_ch), "")):
                with ui.expansion(f"{title}  •  {len(body):,} chars" + (f" • {note}" if note else "")).classes("w-full text-slate-200 text-xs"):
                    theme.long_text(body, mono=True)
            pass_in = storage.read_memory(view.name, st["mode"], vol_n, "PASS-IN.md")
            ui.label("PASS-IN: " + (f"{len(pass_in):,} chars, " + ("rebuilt from the planned events of earlier volumes" if pass_in.startswith(writing.RECONSTRUCTED_PASS_IN_MARK)
                                                                  else "handed off from the previous volume") + " - folded into the character index." if pass_in else
                                    "none yet (Volume 1, or built before the first chapter).")).classes("text-[11px] text-slate-500")


def stale_banner(view: "UniverseView") -> None:
    st = view.state
    n = st["currentVolume"]
    if n not in (st.get("chaptersBeforePlan") or []):
        return
    with ui.column().classes("w-full bg-amber-500/10 border border-amber-500/40 rounded-xl p-4 gap-3"):
        ui.label(f"Volume {n} has chapters saved before this plan was approved. They, and the volume's ledger, character index and PASS-IN, may follow "
                 "the old outline. Reset the volume to write it from the current plan (old files move to _backups/), or keep them if they still fit.").classes("text-sm text-amber-200")
        with ui.row().classes("gap-2"):
            theme.button(f"Reset Volume {n}", lambda: view.act("RESET_VOLUME", {"volume": n}), "amber", size="sm")
            theme.button("Keep them", lambda: view.act("KEEP_VOLUME_CHAPTERS", {"volume": n}), "secondary", size="sm")


def writing_stage(view: "UniverseView") -> None:
    st = view.state
    vol = writing.volume_plan(st) or {}
    nxt = st["chaptersGeneratedInCurrentVolume"] + 1
    chapter = next((c for c in vol.get("chapters", []) if c["chapterNumber"] == nxt), None)
    draft = st.get("draft")
    start_volume_picker(view)
    stale_banner(view)
    with ui.column().classes(f"{theme.PANEL} w-full gap-4"):
        with ui.row().classes("w-full items-start justify-between gap-4"):
            with ui.column().classes("gap-1"):
                theme.badge("Phase 3 • Novel Writing", "emerald")
                ui.label(f"Volume {st['currentVolume']} of {st['totalVolumes']}: {vol.get('title', '')}").classes("text-2xl font-bold text-white")
                ui.label("One chapter at a time from its own context bin. Review it, then save, regenerate or discard. The review gate opens every 3 saved chapters.").classes("text-slate-300 text-sm")
            with ui.column().classes("items-end gap-2"):
                theme.stat("chapters saved", f"{st['chaptersGeneratedInCurrentVolume']} / {st['chaptersPerVolume']}")
                if view.auto_writing:
                    theme.button("■ Stop auto-writing", lambda: (setattr(view, "auto_writing", False), view.refresh_content()), "danger", size="sm")
                else:
                    theme.button("▶ Start auto-writing", lambda: view.confirm(
                        "Start auto-writing?", "Chapters are written AND saved one after another without your review, until the review gate after 3 saved "
                        "chapters. You can stop at any time.", lambda: (setattr(view, "auto_writing", True), view.refresh_content()), "Start"), "secondary", size="sm")
        if chapter and not draft:
            with ui.column().classes(f"{theme.SUBPANEL} w-full gap-1"):
                ui.label(f"Next: Chapter {nxt}: {chapter['title']}").classes("text-sm font-semibold text-white")
                ui.label(chapter["synopsis"]).classes("text-xs text-slate-300")
            theme.button(f"Write Chapter {nxt}", lambda: view.act("WRITE_CHAPTER"), "primary", icon="edit_note", size="lg")
        if draft:
            draft_editor(view, draft)
        if st["chaptersGeneratedInCurrentVolume"] > 0 and not draft:
            theme.button(f"Reset Volume {st['currentVolume']} and rewrite it from Chapter 1", lambda: view.confirm(
                f"Reset Volume {st['currentVolume']}?", "Its saved chapters, ledger and character index move to _backups/ and the volume is written again from Chapter 1.",
                lambda: view.act("RESET_VOLUME", {"volume": st["currentVolume"]}), "Reset"), "ghost", size="sm")
    volume_panels(view)


def draft_editor(view: "UniverseView", draft: dict) -> None:
    audit = draft.get("auditStatus") or {}
    with ui.column().classes("w-full gap-3 bg-white/5 p-6 rounded-2xl border border-white/10"):
        with ui.row().classes("w-full items-center justify-between gap-3"):
            title = ui.input(value=draft["title"]).props("dark dense borderless").classes("text-lg font-bold text-white flex-1 min-w-[300px]")
            if audit:
                theme.badge("Audit: pass" if audit.get("overall") == "APPROVED" else "Audit: review", "emerald" if audit.get("overall") == "APPROVED" else "amber")
        if audit and audit.get("overall") != "APPROVED":
            with ui.column().classes(f"{theme.SUBPANEL} w-full gap-1"):
                for k in ("voice", "continuity", "noSlop"):
                    if audit.get(k) and audit[k] != "PASS":
                        ui.label(f"{k}: {audit[k]}").classes("text-xs text-amber-200")
                if audit.get("notes"):
                    ui.label(audit["notes"]).classes("text-xs text-slate-400")
        text = ui.textarea(value=draft["content"]).props("dark outlined rows=22").classes("w-full lp-prose")
        ui.label(f"{len((text.value or '').split()):,} words").classes("text-[11px] text-slate-500")
        for label, key in (("Ledger entry", "ledgerEntry"), ("Character updates", "soulUpdates"), ("Background overflow", "backgroundOverflow"), ("Elevation notes", "elevationNotes")):
            if draft.get(key):
                with ui.expansion(label).classes("w-full text-slate-300 text-xs"):
                    theme.long_text(draft[key], mono=True)
        with ui.row().classes("gap-2"):
            theme.button(f"Approve & Save Chapter {draft['chapterNumber']}", lambda: view.act("SAVE_DRAFT", {"title": title.value, "content": text.value}), "approve", icon="check_circle", size="lg")
            theme.button("Regenerate", lambda: view.act("WRITE_CHAPTER"), "secondary", icon="refresh")
            theme.button("Elevate prose", lambda: view.act("ELEVATE_DRAFT", {"title": title.value, "content": text.value}), "purple", icon="auto_awesome")
            theme.button("Discard", lambda: view.act("DISCARD_DRAFT"), "danger", icon="delete")


def review_pass(view: "UniverseView") -> None:
    st = view.state
    with ui.column().classes(f"{theme.HERO} w-full gap-3"):
        theme.step_tag("Step 9b Gate • 3-Chapter Quality Checkpoint")
        theme.heading(f"Chapter Pass Review • Volume {st['currentVolume']}", "The engine pauses every 3 chapters for your review (Card 09). Read the chapters "
                      "below and what carries into the next one, then approve to continue.")
        if st.get("milestoneNotice"):
            ui.label(st["milestoneNotice"]).classes("text-sm text-amber-300 font-semibold")
        with ui.row().classes("gap-3"):
            theme.button("Approve Pass & Resume Writing →", lambda: view.act("APPROVE_PASS"), "approve", icon="check_circle", size="lg")
            theme.button("Run Foreshadowing Subtlety Audit", lambda: view.act("SUBTLETY_AUDIT"), "purple", icon="visibility")
    audit = st.get("subtletyAudit")
    if audit:
        with ui.column().classes(f"{theme.PANEL} w-full gap-2"):
            ui.label(f"Subtlety audit: {audit['overallVerdict']} • average {audit['averageSubtlety']}/10").classes("text-sm font-bold text-white")
            for s in audit["seeds"]:
                ui.label(f"Ch {s['chapterNumber']} • {s['threadName']} • {s['subtletyScore']}/10 • {s['location']}"
                         + (f" • Revision: {s['revision']}" if s.get("revision") else "")).classes("text-xs text-slate-300")
    volume_panels(view)


def handoff(view: "UniverseView") -> None:
    st = view.state
    with ui.column().classes(f"{theme.PANEL} w-full gap-3"):
        ui.label(f"Volume {st['currentVolume']} Writing Complete").classes("text-2xl font-bold text-white")
        ui.label("The memory handoff builds the PASS-OUT (state changes, soul codex, open threads, Chekhov's guns) from the full ledger and character index, "
                 "and hands it to the next volume as its PASS-IN.").classes("text-slate-300 text-sm")
        theme.button("Generate Memory Handoff", lambda: view.act("HANDOFF"), "primary", icon="sync_alt", size="lg")
    volume_panels(view)


def completed(view: "UniverseView") -> None:
    st = view.state
    with ui.column().classes(f"{theme.PANEL} w-full gap-3 items-center text-center py-12"):
        ui.icon("auto_awesome").classes("text-6xl text-purple-400")
        ui.label("Epic Narrative Completed").classes("text-4xl font-extrabold text-white")
        ui.label(f"All {st['totalVolumes']} volumes are written.").classes("text-slate-300")
        theme.button("Export manuscript (.docx)", lambda: export_manuscript(view), "primary", icon="download", size="lg")
    if st.get("lastHandoff"):
        with ui.expansion("Final PASS-OUT").classes(f"w-full {theme.PANEL} text-slate-200"):
            theme.long_text(st["lastHandoff"]["passOut"], mono=True)


def export_manuscript(view: "UniverseView") -> None:
    import docx
    st = view.state
    doc = docx.Document()
    doc.add_heading(st["name"].replace("_", " "), 0)
    for v in (st.get("plan") or {}).get("volumes", []):
        doc.add_heading(f"Volume {v['volumeNumber']}: {v['title']}", 1)
        for c in storage.list_chapters(view.name, st["mode"], v["volumeNumber"]):
            doc.add_heading(c["file"].removesuffix(".txt").split(" - ", 1)[-1], 2)
            for para in c["content"].split("\n\n"):
                doc.add_paragraph(para.strip())
    out = storage.universe_dir(view.name) / "EXPORTS"
    out.mkdir(exist_ok=True)
    path = out / f"{view.name}-manuscript.docx"
    doc.save(path)
    ui.notify(f"Saved {path}", type="positive", multi_line=True)
