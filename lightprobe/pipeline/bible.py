"""STAGE 3 — Universe Bible, Soul Roster and Arc Map.

Before the roster is built, an identity check merges entries for the same person, drops aliases
attached to the wrong person, and splits entries that mix two people (line-number based, verbatim).
"""

from __future__ import annotations

import re
import shutil

from .. import storage
from ..ai import planning_model
from ..ai.canon import generate_soul_roster, generate_universe_bible
from ..ai.sorting import group_soul_aliases, split_merged_soul
from .common import (SOUL_FIELDS, Progress, append_distinct, clean_aliases, format_arc_map, format_clarifications, key, merge_rule,
                     merge_soul, no_progress)
from .ingest import write_clarifications

DEEP_CHECK_TOP = 15  # most-documented characters always get the line-by-line identity check


def _split_soul_notes(sort: dict, soul: dict, all_names: list[str], touched: set[str], model: str) -> dict:
    name_keys = {key(n) for n in all_names}
    lines = []
    for f in SOUL_FIELDS:
        for text in (soul.get(f) or "").split("\n"):
            if text.strip():
                lines.append({"n": len(lines) + 1, "field": f, "text": text})
    split = split_merged_soul(soul["name"], soul.get("aliases") or [], "\n".join(f"[{l['n']}] ({l['field']}) {l['text']}" for l in lines),
                              [{"name": s["name"], "preview": (s.get("essence") or "").split("\n")[0][:110]} for s in sort["souls"] if s is not soul], model)
    move_to: dict[int, dict] = {}
    line_numbers = {l["n"] for l in lines}
    for m in split.get("moved") or []:
        to = (m.get("toName") or "").strip()
        if not to or key(to) == key(soul["name"]) or m.get("line") not in line_numbers:
            continue
        target = next((e for e in sort["souls"] if key(e["name"]) == key(to) and e is not soul), None)
        if target is None:
            # A distinct person with no entry yet (e.g. an unnamed relative folded into a named character)
            target = {"name": to, "aliases": [], "essence": "", "woundsAndDesires": "", "relationships": "", "speechHabits": "",
                      "sources": list(soul.get("sources") or [])}
            sort["souls"].append(target)
            all_names.append(to)
        move_to[m["line"]] = target
    for f in SOUL_FIELDS:
        soul[f] = "\n".join(l["text"] for l in lines if l["field"] == f and l["n"] not in move_to)
    moved = []
    for l in lines:
        target = move_to.get(l["n"])
        if target:
            target[l["field"]] = append_distinct(target.get(l["field"]), l["text"])
            touched.add(target["name"])
            moved.append({"to": target["name"], "line": l["text"][:120]})
    before = soul.get("aliases") or []
    soul["aliases"] = [a for a in clean_aliases(split.get("aliases")) if key(a) not in name_keys and key(a) != key(soul["name"])]
    return {"name": soul["name"], "movedOut": moved, "removedAliases": [a for a in before if a not in soul["aliases"]]}


def clean_roster_aliases(roster: dict) -> None:
    """An alias that is another character's name, or a bare name that fits several characters, identifies no one."""
    souls = roster["souls"]
    name_keys = {key(s["name"]) for s in souls}

    def is_proper(n: str) -> bool:
        bare = re.sub(r"\(.*?\)", "", n).strip()
        return not re.search(r"\b(who|of|with|from|at|the|a|an)\b|'s\b", bare, re.I) and bool(re.match(r"^[A-Z]", bare))

    def words(n: str) -> list[str]:
        return [w for w in re.split(r"[^a-z']+", re.sub(r"\(.*?\)", " ", n.lower())) if w]

    owners: dict[str, list[dict]] = {}
    for s in souls:
        if is_proper(s["name"]):
            for w in set(words(s["name"])):
                owners.setdefault(w, []).append(s)
    for s in souls:
        kept = []
        for a in clean_aliases(s.get("aliases")):
            k = key(a)
            if k == key(s["name"]) or k in name_keys:
                continue
            if not re.search(r"\s", k):
                own = owners.get(k, [])
                if len(own) > 1:
                    starters = [o for o in own if words(o["name"])[:1] == [k]]
                    if not (len(starters) == 1 and starters[0] is s):
                        continue
            kept.append(a)
        s["aliases"] = kept


def format_roster_doc(roster: dict) -> str:
    return "# SOUL ROSTER (CANONICAL)\n\n" + "\n\n".join(
        f"## {s['name']}" + (f" (aka {', '.join(s['aliases'])})" if s.get("aliases") else "") +
        f"\n- **Essence**: {s.get('essence', '')}\n- **Wounds/Desires**: {s.get('woundsAndDesires', '')}\n- **Relationships**: {s.get('relationships', '')}"
        f"\n- **Speech**: {s.get('speechHabits', '')}\n- **Continuity Tripwire**: {s.get('continuityTripwire', '')}" for s in roster["souls"])


def format_bible_doc(bible: dict) -> str:
    rules = "\n\n".join(f"### {r['ruleName']}\n{r['description']}\nConstraint: {r['constraint']}" for r in bible.get("worldRules") or [])
    themes = "\n".join(f"- {t}" for t in bible.get("themes") or [])
    return (f"# UNIVERSE BIBLE (CANONICAL)\n\n## CORE PREMISE\n{bible.get('corePremise', '')}\n\n## CIVILIZATIONAL MODEL\n"
            f"{bible.get('civilizationalModel', '')}\n\n## WORLD RULES\n{rules}\n\n## THEMES\n{themes}")


def run_bible(name: str, state: dict, progress: Progress = no_progress) -> dict:
    sort = state.get("messSortResult")
    if not sort or not sort.get("complete"):
        raise ValueError("Finish the MESS sort first.")
    state["status"] = "BIBLE_REVIEW"
    storage.save_state(name, state)
    model = planning_model(state)
    clar = format_clarifications(sort)

    progress(f"Checking who is who across {len(sort['souls'])} character entries (aliases, misspellings, groups vs people)...", 5)
    check = group_soul_aliases([{"name": s["name"], "aliases": s.get("aliases"), "essence": s.get("essence", ""),
                                 "relationships": s.get("relationships", "")} for s in sort["souls"]], model, clar)
    for soul_name, bad in check["wrongAliases"].items():
        soul = next((s for s in sort["souls"] if s["name"] == soul_name), None)
        if soul:
            soul["aliases"] = [a for a in soul.get("aliases") or [] if not any(key(b) == key(a) for b in bad)]
    all_names = [s["name"] for s in sort["souls"]]
    name_keys = {key(n) for n in all_names}
    note_lines = lambda s: sum(len([l for l in (s.get(f) or "").split("\n") if l.strip()]) for f in SOUL_FIELDS)  # noqa: E731
    most_documented = {s["name"] for s in sorted(sort["souls"], key=note_lines, reverse=True)[:DEEP_CHECK_TOP]}
    to_split = [s for s in sort["souls"] if s["name"] in check["mixedEntries"] or s["name"] in most_documented
                or any(key(a) in name_keys and key(a) != key(s["name"]) for a in s.get("aliases") or [])]
    for i, soul in enumerate(to_split):
        progress(f"Separating mixed-up notes for {soul['name']} ({i + 1}/{len(to_split)})...", 8)
        _split_soul_notes(sort, soul, all_names, set(), model)
    # A split can create a new character (e.g. an unnamed relative); it is its own person, never dropped
    grouped = {m for g in check["groups"] for m in g["members"]}
    check["groups"] += [{"canonical": s["name"], "members": [s["name"]], "kind": "PERSON"} for s in sort["souls"] if s["name"] not in grouped]

    # Merge entries that are the same person; nothing is dropped (groups -> world rules, references -> themes)
    persons = []
    for g in check["groups"]:
        members = [s for s in sort["souls"] if s["name"] in g["members"]]
        if not members:
            continue
        primary = next((m for m in members if m["name"] == g["canonical"]), members[0])
        entry = {**primary, "name": g["canonical"],
                 "aliases": list(dict.fromkeys((primary.get("aliases") or []) + ([primary["name"]] if primary["name"] != g["canonical"] else [])))}
        merged = [entry]
        for m in members:
            if m is not primary:
                merge_soul(merged, {**m, "aliases": (m.get("aliases") or []) + [m["name"]], "name": g["canonical"]})
        soul = merged[0]
        if g["kind"] == "GROUP":
            merge_rule(sort["worldRules"], {"ruleName": f"Faction: {soul['name']}", "description": "\n".join(x for x in (soul.get("essence"), soul.get("relationships")) if x),
                                            "constraint": soul.get("woundsAndDesires") or "", "sources": soul.get("sources")})
        elif g["kind"] == "REFERENCE":
            theme = f"Reference: {soul['name']} - {' '.join((soul.get('essence') or '').split())}"
            if theme not in sort["themes"]:
                sort["themes"].append(theme)
        else:
            persons.append(soul)
    sort["souls"] = persons

    laws = "\n\n".join(x for x in (storage.read_core(name, "00-LAWS.md"), storage.read_core(name, "06-MULTI-QUADRANT.md"),
                                   f"=== AUTHOR CLARIFICATIONS (canon - override the notes where they conflict) ===\n{clar}" if clar else "") if x)
    progress(f"{len(persons)} individual characters after merging. Consolidating {len(sort['worldRules'])} rule notes into the Universe Bible...", 20)
    bible = generate_universe_bible(sort, laws, model)
    storage.write_core(name, "UNIVERSE-BIBLE.md", format_bible_doc(bible))
    state["universeBible"] = bible
    storage.save_state(name, state)

    progress(f"Universe Bible ready ({len(bible.get('worldRules') or [])} rules). Building the Soul Roster for {len(persons)} characters...", 45)
    roster = generate_soul_roster(persons, bible, model, clar,
                                  on_batch=lambda b, t: progress(f"Soul Roster - profiling characters, batch {b}/{t}...", round(45 + (b - 1) / max(1, t) * 50)))
    clean_roster_aliases(roster)
    storage.write_core(name, "SOUL-ROSTER.md", format_roster_doc(roster))
    storage.write_core(name, "ARC-MAP.md", f"# ARC MAP (all sorted arc beats, intake order)\n\n{format_arc_map(sort)}")
    write_clarifications(name, state)
    state["soulRoster"] = roster
    storage.save_state(name, state)
    progress(f"Universe Bible and Soul Roster ready ({len(roster['souls'])} characters).", 100)
    return state


def repair_souls(name: str, state: dict, entries: list[str] | None = None, progress: Progress = no_progress) -> dict:
    """Separates characters that were wrongly merged, rebuilding only the touched roster entries.
    state.json and SOUL-ROSTER.md are backed up first."""
    sort = state.get("messSortResult")
    if not sort or not state.get("universeBible") or not state.get("soulRoster"):
        raise ValueError("Build the Universe Bible and Soul Roster first.")
    backup = storage.new_backup_dir(name, "repair-souls")
    roster_file = storage.core_dir(name) / "SOUL-ROSTER.md"
    if roster_file.exists():
        shutil.copy2(roster_file, backup / "SOUL-ROSTER.md")
    all_names = [s["name"] for s in sort["souls"]]
    name_keys = {key(n) for n in all_names}
    if entries:
        affected = [s for s in sort["souls"] if any(key(e) == key(s["name"]) for e in entries)]
    else:
        affected = [s for s in sort["souls"] if any(key(a) in name_keys and key(a) != key(s["name"]) for a in s.get("aliases") or [])]
    touched = {s["name"] for s in affected}
    model = planning_model(state)
    report = []
    for i, soul in enumerate(affected):
        progress(f"Separating wrongly merged notes for {soul['name']} ({i + 1}/{len(affected)})...", round(5 + i / max(1, len(affected)) * 70))
        report.append(_split_soul_notes(sort, soul, all_names, touched, model))
    progress(f"Rebuilding {len(touched)} Soul Roster entries...", 80)
    rebuilt = generate_soul_roster([s for s in sort["souls"] if s["name"] in touched], state["universeBible"], model, format_clarifications(sort))
    roster = state["soulRoster"]
    for entry in rebuilt["souls"]:
        idx = next((i for i, s in enumerate(roster["souls"]) if key(s["name"]) == key(entry["name"])), None)
        if idx is None:
            roster["souls"].append(entry)
        else:
            roster["souls"][idx] = entry
    clean_roster_aliases(roster)
    storage.write_core(name, "SOUL-ROSTER.md", format_roster_doc(roster))
    storage.save_state(name, state)
    progress(f"Repaired {len(affected)} characters; rebuilt {len(rebuilt['souls'])} roster entries. Backup: {backup.name}", 100)
    return {"report": report, "backup": backup.name}
