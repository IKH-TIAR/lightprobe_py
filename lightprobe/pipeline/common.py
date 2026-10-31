"""Helpers shared by the pipeline stages."""

from __future__ import annotations

import re
from typing import Callable, Protocol

from .. import storage


class Progress(Protocol):
    def __call__(self, message: str, percentage: int | None = None, **extra) -> None: ...


def no_progress(message: str, percentage: int | None = None, **extra) -> None:
    pass


def key(s: str) -> str:
    return (s or "").lower().strip()


def append_distinct(existing: str | None, incoming: str | None) -> str:
    """Lossless merge: a later note is appended, never overwrites an earlier one."""
    a, b = (existing or "").strip(), (incoming or "").strip()
    if not b:
        return a
    if not a:
        return b
    norm = lambda s: re.sub(r"\s+", " ", s.lower())  # noqa: E731
    return a if norm(b) in norm(a) else f"{a}\n{b}"


# A bare role or relation is not a name: it fits many people and would merge them together
GENERIC_ALIASES = {
    "coach", "captain", "sensei", "teacher", "officer", "principal", "doctor", "nurse", "boss", "sir", "madam",
    "girl", "boy", "kid", "man", "woman", "guy", "big guy", "mom", "dad", "mother", "father", "brother", "sister",
    "grandma", "grandpa", "gramps", "granny", "uncle", "aunt", "friend", "the girl", "the boy", "senpai", "kouhai",
}


def clean_aliases(aliases: list[str] | None) -> list[str]:
    out = []
    for a in aliases or []:
        a = re.sub(r"\s+", " ", re.sub(r"\s*\([^)]*\)\s*", " ", a)).strip()
        if len(a) < 2 or a.lower() in GENERIC_ALIASES:
            continue
        # Descriptions are not names ("the other coach against Hanagawa", "Kaho's brother")
        if re.match(r"^(the|a|an|her|his|their)\s", a, re.I) or re.search(r"'s(\s|$)", a, re.I) or len(a.split(" ")) > 5:
            continue
        out.append(a)
    return out


SOUL_FIELDS = ("essence", "woundsAndDesires", "relationships", "speechHabits")


def merge_soul(souls: list[dict], s: dict, source: str | None = None) -> None:
    """Same person only when a NAME matches: exact name, the incoming name is a known alias, or (for a
    one-word nickname) an incoming alias is an existing name. Never alias-to-alias."""
    s = {**s, "aliases": clean_aliases(s.get("aliases"))}
    is_nickname = not re.search(r"\s", s["name"].strip())
    existing = (next((e for e in souls if key(e["name"]) == key(s["name"])), None)
                or next((e for e in souls if any(key(a) == key(s["name"]) for a in e.get("aliases") or [])), None)
                or (next((e for e in souls if any(key(a) == key(e["name"]) for a in s["aliases"])), None) if is_nickname else None))
    sources = list(s.get("sources") or []) + ([source] if source else [])
    other_names = {key(e["name"]) for e in souls if e is not existing}
    safe = lambda al: [a for a in al if key(a) not in other_names]  # noqa: E731
    if existing is None:
        souls.append({"name": s["name"], "aliases": safe(s["aliases"]), "essence": s.get("essence") or "",
                      "woundsAndDesires": s.get("woundsAndDesires") or "", "relationships": s.get("relationships") or "",
                      "speechHabits": s.get("speechHabits") or "", "sources": sources})
        return
    merged = list(dict.fromkeys((existing.get("aliases") or []) + safe(s["aliases"] + [s["name"]])))
    existing["aliases"] = [a for a in merged if key(a) != key(existing["name"])]
    for f in SOUL_FIELDS:
        existing[f] = append_distinct(existing.get(f), s.get(f))
    existing["sources"] = list(dict.fromkeys((existing.get("sources") or []) + sources))


def merge_rule(rules: list[dict], r: dict, source: str | None = None) -> None:
    existing = next((e for e in rules if key(e["ruleName"]) == key(r["ruleName"])), None)
    sources = list(r.get("sources") or []) + ([source] if source else [])
    if existing is None:
        rules.append({"ruleName": r["ruleName"], "description": r.get("description") or "", "constraint": r.get("constraint") or "", "sources": sources})
        return
    existing["description"] = append_distinct(existing.get("description"), r.get("description"))
    existing["constraint"] = append_distinct(existing.get("constraint"), r.get("constraint"))
    existing["sources"] = list(dict.fromkeys((existing.get("sources") or []) + sources))


def source_file(source: str) -> str:
    """Sources are recorded as "<file> p.<page>"."""
    return re.sub(r" p\.\d+.*$", "", source or "")


def is_events_only(state: dict, file_name: str) -> bool:
    return bool(((state.get("messFileSettings") or {}).get(file_name) or {}).get("eventsOnly"))


def format_clarifications(sort: dict | None) -> str:
    lines = []
    for u in (sort or {}).get("unclear") or []:
        if u.get("status") in ("RESOLVED", "ANSWERED") and (u.get("answer") or "").strip():
            who = "author" if u["status"] == "ANSWERED" else ("from notes" + (f": {u['evidence']}" if u.get("evidence") else ""))
            re_line = f"\n  Re: \"{u['quote'][:300]}\"" if u.get("quote") else ""
            lines.append(f"[{u['id']}] Q: {u['question']}{re_line}\n  A ({who}): {u['answer'].strip()}")
    return "\n".join(lines)


def read_canon(name: str) -> str:
    return "\n\n".join(x for x in (storage.read_core(name, "UNIVERSE-BIBLE.md"), storage.read_core(name, "SOUL-ROSTER.md"),
                                   storage.read_core(name, "AUTHOR-CLARIFICATIONS.md")) if x)


def format_arc_map(sort: dict, fixed: dict[str, int] | None = None) -> str:
    fixed = fixed or {}
    return "\n".join(
        f"[{b['id']}] ({b.get('phase') or 'unplaced'}) {b['event']} -> {b['irreversibleChange']}"
        + (f"  {{{b['source']}}}" if b.get("source") else "")
        + (f"  FIXED -> Volume {fixed[b['id']]}" if b["id"] in fixed else "")
        for b in sort["arcBeats"])


def item_index(state: dict, store: dict | None = None) -> dict[str, dict]:
    """Every placeable item by id: arc beats (B-n), draft passages (M-n), confirmed or proposed mini-events (E..)."""
    sort = state.get("messSortResult") or {}
    out: dict[str, dict] = {}
    for b in sort.get("arcBeats") or []:
        out[b["id"]] = {"id": b["id"], "kind": "BEAT", "label": b.get("phase") or "", "summary": f"{b['event']} -> {b['irreversibleChange']}",
                        "source": b.get("source") or "", "text": ""}
    items = (store or {}).get("items") or {}
    for m in sort.get("chapterMaterial") or []:
        out[m["id"]] = {"id": m["id"], "kind": "DRAFT", "label": m.get("volumeHint") or "", "summary": m.get("content") or "",
                        "source": m.get("source") or "", "text": (items.get(m["id"]) or {}).get("text", "")}
    for vol, gv in ((state.get("gapFill") or {}).get("volumes") or {}).items():
        for e in gv.get("miniEvents") or []:
            out[e["id"]] = {"id": e["id"], "kind": "MINI_EVENT", "label": e.get("kind", ""), "summary": f"{e['title']}: {e['event']}",
                            "source": f"gap-fill Volume {vol} ({e.get('status', 'PROPOSED').lower()})", "text": "", "status": e.get("status")}
    return out


def bin_text(state: dict, ids: list[str], store: dict | None = None, verbatim: bool = False, mini_events: list[dict] | None = None) -> str:
    """The material of a volume bin as prompt text. `verbatim` includes the author's full draft passages."""
    sort = state.get("messSortResult") or {}
    idset = set(ids)
    items = (store or {}).get("items") or {}
    parts = []
    beats = [b for b in sort.get("arcBeats") or [] if b["id"] in idset]
    if beats:
        parts.append("ARC BEATS:\n" + "\n".join(f"[{b['id']}] ({b.get('phase', '')}) {b['event']} -> {b['irreversibleChange']}  {{{b.get('source', '')}}}" for b in beats))
    drafts = [m for m in sort.get("chapterMaterial") or [] if m["id"] in idset]
    if drafts:
        def fmt(m: dict) -> str:
            text = (items.get(m["id"]) or {}).get("text", "")
            if verbatim:
                return f"[{m['id']}] {{{m.get('source', '')}}} {m.get('content', '')}\n\"\"\"\n{text}\n\"\"\""
            excerpt = re.sub(r"\s+", " ", text[:600])
            return f"[{m['id']}] {{{m.get('source', '')}}} {m.get('content', '')}" + (f"\n  Excerpt: {excerpt}{'...' if len(text) > 600 else ''}" if text else "")
        parts.append("AUTHOR DRAFT MATERIAL:\n" + "\n\n".join(fmt(m) for m in drafts))
    if mini_events:
        parts.append("CONFIRMED MINI-EVENTS (approved by the creators; canon):\n" + "\n".join(
            f"[{e['id']}] {e['title']}: {e['event']} (cause: {e.get('cause', '')}; effect: {e.get('effect', '')}; leads to: {e.get('leadsTo', '')})"
            for e in mini_events))
    return "\n\n".join(parts)


def invalidate_downstream(name: str, state: dict, back_to: str, label: str, clear: tuple[str, ...]) -> str | None:
    """An earlier stage changed, so later results built on it are stale: they are backed up and cleared, and
    the furthest stage reached drops back to `back_to`, so every later stage must be approved again (no jumping
    forward over a changed stage). Returns the backup folder name, if anything was cleared."""
    from ..styles import STATE_ORDER
    backup = None
    if any(state.get(k) for k in clear):
        backup = storage.new_backup_dir(name, label).name
        for k in clear:
            state[k] = None
    state["resumeStatus"] = None
    if STATE_ORDER.index(state.get("furthestStatus") or state["status"]) > STATE_ORDER.index(back_to):
        state["furthestStatus"] = back_to
    return backup


def next_id(existing: list[str], prefix: str) -> int:
    """Next free number for ids like B-12 (never reuses a number, even after items were removed)."""
    nums = [int(i[len(prefix):]) for i in existing if i.startswith(prefix) and i[len(prefix):].isdigit()]
    return max(nums, default=0) + 1


def run_safely(fn: Callable[[], None], progress: Progress, label: str) -> None:
    """Runs a follow-up step; a failure is reported but never undoes the step before it."""
    try:
        fn()
    except Exception as err:  # noqa: BLE001 - reported to the creators, never swallowed silently
        progress(f"{label} stopped ({err}). You can run it again from this screen.")
