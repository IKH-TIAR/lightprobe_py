"""STAGE 6 — Gap-fill (Card 05 GAP-FILL).

For each volume the assistant fixes both ends (where the story stands as the volume opens, and the
author's main events in it), works out what must become true before each main event, and proposes
the MINI-EVENTS that compound toward it by cause and effect. Anything that would need a new main
event, a world rule or a change to a soul's essence becomes a QUESTION for the creators instead.

The creators accept, edit, reject or add mini-events, answer the questions, and confirm the volume.
Only confirmed mini-events reach the outline. A finished (pinned) volume needs no gap-fill.
"""

from __future__ import annotations

from .. import storage
from ..ai import planning_model
from ..ai.planning import propose_gap_fill
from .common import Progress, bin_text, invalidate_downstream, next_id, no_progress, read_canon
from .ingest import write_ask_me

EDITABLE_FIELDS = ("title", "event", "cause", "effect", "leadsTo", "after", "souls", "kind")


def _changed(name: str, state: dict) -> None:
    """A gap-fill change after outlines exist makes them stale (the outline must use the confirmed mini-events)."""
    invalidate_downstream(name, state, "GAP_REVIEW", "gapfill-changed", ("plan", "payoffPlan"))


def _new_event_id(gv: dict, n: int) -> str:
    """Per-volume counter, so an id is never reused for a different mini-event."""
    prefix = f"E{n:02d}-"
    gv["nextEventId"] = max(gv.get("nextEventId") or 0, next_id([e["id"] for e in gv["miniEvents"]], prefix))
    eid = f"{prefix}{gv['nextEventId']}"
    gv["nextEventId"] += 1
    return eid


def _new_question_id(gv: dict, n: int) -> str:
    prefix = f"Q{n:02d}-"
    gv["nextQuestionId"] = max(gv.get("nextQuestionId") or 0, next_id([q["id"] for q in gv["questions"]], prefix))
    qid = f"{prefix}{gv['nextQuestionId']}"
    gv["nextQuestionId"] += 1
    return qid


def _gap(state: dict) -> dict:
    if not state.get("gapFill"):
        state["gapFill"] = {"volumes": {}}
    return state["gapFill"]


def volume_gap(state: dict, n: int) -> dict:
    vols = _gap(state)["volumes"]
    vols.setdefault(str(n), {"status": "PENDING", "volumeStart": "", "mainEvents": [], "miniEvents": [], "questions": [], "notes": ""})
    return vols[str(n)]


def accepted_events(state: dict, n: int) -> list[dict]:
    return [e for e in volume_gap(state, n)["miniEvents"] if e.get("status") == "ACCEPTED"]


def _bin_volume(state: dict, n: int) -> dict:
    v = next((x for x in (state.get("bins") or {}).get("volumes", []) if x["volumeNumber"] == n), None)
    if not v:
        raise ValueError(f"Volume {n} is not in the bins.")
    return v


def _previous_context(state: dict, n: int) -> str:
    if n <= 1:
        return ""
    prev = _bin_volume(state, n - 1)
    gv = volume_gap(state, n - 1)
    main = "\n".join(f"- {m['event']}" for m in gv.get("mainEvents") or [])
    minis = [e for e in gv["miniEvents"] if e.get("status") != "REJECTED"][-6:]
    lines = [f"Volume {n - 1} \"{prev['title']}\": {prev['summary']}", f"It closes on: {prev['premise']}"]
    if main:
        lines.append(f"Its main events:\n{main}")
    if minis:
        lines.append("Its last mini-events:\n" + "\n".join(f"- {e['title']}: {e['event']}" for e in minis))
    return "\n".join(lines)


def _next_context(state: dict, n: int) -> str:
    vols = (state.get("bins") or {}).get("volumes", [])
    nxt = next((x for x in vols if x["volumeNumber"] == n + 1), None)
    if not nxt:
        return ""
    sort = state["messSortResult"]
    first_beats = [b for b in sort["arcBeats"] if b["id"] in set(nxt["itemIds"])][:5]
    return f"Volume {n + 1} \"{nxt['title']}\": {nxt['premise']}\n" + "\n".join(f"- [{b['id']}] {b['event']}" for b in first_beats)


def _roadmap_brief(state: dict) -> str:
    return "\n".join(f"Volume {v['volumeNumber']}: {v['title']} - {v['premise']}" + (" (FINISHED volume)" if v.get("pinnedFrom") else "")
                     for v in (state.get("bins") or {}).get("volumes", []))


def _creator_notes(gv: dict) -> str:
    answered = [q for q in gv.get("questions") or [] if (q.get("answer") or "").strip()]
    parts = [gv.get("notes") or ""]
    if answered:
        parts.append("Creators' answers:\n" + "\n".join(f"- Q: {q['question']}\n  A: {q['answer']}" for q in answered))
    return "\n\n".join(p for p in parts if p.strip())


def run_gap_fill(name: str, state: dict, volumes: list[int] | None = None, include_finished: bool = False, progress: Progress = no_progress) -> dict:
    bins = state.get("bins")
    if not bins:
        raise ValueError("Build the volume bins first.")
    targets = volumes or [v["volumeNumber"] for v in bins["volumes"]]
    store = storage.get_sorted_material(name)
    canon = read_canon(name)
    gap_card = storage.read_core(name, "05-GAP-FILL.md")
    model = planning_model(state)
    for i, n in enumerate(targets):
        v = _bin_volume(state, n)
        gv = volume_gap(state, n)
        if gv["status"] == "CONFIRMED" and not volumes:
            continue  # a confirmed volume is only redone when the creators ask for it by number
        if v.get("pinnedFrom") and not include_finished and not volumes:
            if gv["status"] == "PENDING":
                gv["status"] = "FINISHED"
                storage.save_state(name, state)
            continue
        progress(f'Gap-fill Volume {n} "{v["title"]}": finding what must happen before its main events ({i + 1}/{len(targets)})...',
                 round(i / len(targets) * 95), volume=n)
        keep = accepted_events(state, n)
        res = propose_gap_fill(v, bin_text(state, v["itemIds"], store), _previous_context(state, n), _next_context(state, n), canon, gap_card,
                               _roadmap_brief(state), state["mode"], state.get("chapterRange"), _creator_notes(gv), keep, model)
        fresh = []
        for e in res.get("miniEvents") or []:
            fresh.append({**{k: e.get(k, "") for k in ("title", "event", "cause", "effect", "leadsTo", "after", "kind", "decisionNote")},
                          "souls": e.get("souls") or [], "needsDecision": bool(e.get("needsDecision")),
                          "id": _new_event_id(gv, n), "status": "PROPOSED", "origin": "ASSISTANT"})
        kept_q = [q for q in gv["questions"] if (q.get("answer") or "").strip()]
        new_q = [{"id": _new_question_id(gv, n), "question": q.get("question", ""), "why": q.get("why", ""), "about": q.get("about", ""), "answer": ""}
                 for q in res.get("questions") or []]
        gv.update(status="PROPOSED", volumeStart=res.get("volumeStart", ""), mainEvents=res.get("mainEvents") or [],
                  miniEvents=keep + fresh, questions=kept_q + new_q)
        _changed(name, state)
        storage.save_state(name, state)
    write_ask_me(name, state)
    storage.save_state(name, state)
    progress("Gap-fill proposals ready. Review each volume: accept, edit or reject the mini-events, answer the questions, then confirm the volume.", 100)
    return state


def _event(state: dict, n: int, event_id: str) -> dict:
    e = next((x for x in volume_gap(state, n)["miniEvents"] if x["id"] == event_id), None)
    if not e:
        raise ValueError(f"Mini-event {event_id} not found in Volume {n}.")
    return e


def _reopen(gv: dict) -> None:
    if gv["status"] == "CONFIRMED":
        gv["status"] = "PROPOSED"


def set_event_status(name: str, state: dict, n: int, event_id: str, status: str) -> dict:
    if status not in ("ACCEPTED", "REJECTED", "PROPOSED"):
        raise ValueError(f"Unknown status {status}.")
    _event(state, n, event_id)["status"] = status
    _reopen(volume_gap(state, n))
    _changed(name, state)
    storage.save_state(name, state)
    return state


def edit_event(name: str, state: dict, n: int, event_id: str, fields: dict) -> dict:
    e = _event(state, n, event_id)
    for k in EDITABLE_FIELDS:
        if k in fields:
            e[k] = fields[k]
    e["editedByCreators"] = True
    _reopen(volume_gap(state, n))
    _changed(name, state)
    storage.save_state(name, state)
    return state


def add_event(name: str, state: dict, n: int, fields: dict) -> dict:
    gv = volume_gap(state, n)
    if not (fields.get("event") or "").strip():
        raise ValueError("Describe what happens in the mini-event.")
    gv["miniEvents"].append({"id": _new_event_id(gv, n), "title": fields.get("title") or "Creator mini-event", "event": fields["event"],
                             "cause": fields.get("cause", ""), "effect": fields.get("effect", ""), "leadsTo": fields.get("leadsTo", ""),
                             "after": fields.get("after", ""), "souls": fields.get("souls") or [], "kind": fields.get("kind") or "TEXTURE",
                             "needsDecision": False, "decisionNote": "", "status": "ACCEPTED", "origin": "CREATORS"})
    if gv["status"] in ("PENDING", "FINISHED"):
        gv["status"] = "PROPOSED"
    _reopen(gv)
    _changed(name, state)
    storage.save_state(name, state)
    return state


def answer_question(name: str, state: dict, n: int, question_id: str, answer: str) -> dict:
    q = next((x for x in volume_gap(state, n)["questions"] if x["id"] == question_id), None)
    if not q:
        raise ValueError(f"Question {question_id} not found.")
    q["answer"] = answer.strip()
    write_ask_me(name, state)
    _changed(name, state)
    storage.save_state(name, state)
    return state


def set_notes(name: str, state: dict, n: int, notes: str) -> dict:
    volume_gap(state, n)["notes"] = notes
    _changed(name, state)
    storage.save_state(name, state)
    return state


def mini_events_doc(state: dict, n: int) -> str:
    gv = volume_gap(state, n)
    events = accepted_events(state, n)
    answered = [q for q in gv["questions"] if (q.get("answer") or "").strip()]
    lines = [f"# VOLUME {n} - CONFIRMED MINI-EVENTS (approved by the creators)", "", f"Where the volume opens: {gv.get('volumeStart', '')}", ""]
    lines += [f"## [{e['id']}] {e['title']}\n{e['event']}\n- Cause: {e.get('cause', '')}\n- Effect: {e.get('effect', '')}\n- Leads to: {e.get('leadsTo', '')}"
              f"\n- Souls: {', '.join(e.get('souls') or [])}\n" for e in events]
    if answered:
        lines.append("## Creators' answers\n" + "\n".join(f"- Q: {q['question']}\n  A: {q['answer']}" for q in answered))
    return "\n".join(lines)


def confirm_volume(name: str, state: dict, n: int, accept_remaining: bool = False) -> dict:
    gv = volume_gap(state, n)
    pending = [e for e in gv["miniEvents"] if e.get("status") == "PROPOSED"]
    if pending and not accept_remaining:
        raise ValueError(f"Volume {n} still has {len(pending)} proposed mini-events. Accept or reject them first.")
    for e in pending:
        e["status"] = "ACCEPTED"
    gv["status"] = "CONFIRMED"
    storage.write_volume_file(name, state["mode"], n, "MINI-EVENTS.md", mini_events_doc(state, n))
    _changed(name, state)
    storage.save_state(name, state)
    return state


def reopen_volume(name: str, state: dict, n: int) -> dict:
    volume_gap(state, n)["status"] = "PROPOSED"
    _changed(name, state)
    storage.save_state(name, state)
    return state


def approve_gaps(name: str, state: dict) -> dict:
    vols = (state.get("bins") or {}).get("volumes", [])
    open_vols = [v["volumeNumber"] for v in vols if volume_gap(state, v["volumeNumber"])["status"] not in ("CONFIRMED", "FINISHED")]
    if open_vols:
        raise ValueError("Confirm gap-fill for Volume" + ("s " if len(open_vols) > 1 else " ") + ", ".join(map(str, open_vols)) + " first.")
    state["status"] = "OUTLINE_REVIEW"
    storage.save_state(name, state)
    return state
