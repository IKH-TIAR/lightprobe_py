"""STEP 2 — Universe Bible + Soul Roster (Cards LNF-00 v2 + LNF-02)."""

from __future__ import annotations

import re

from ..llm import CallOptions, S, arr, generate_json, obj

ROSTER_BATCH_SIZE = 8
BIBLE_SCHEMA = obj({"corePremise": S, "civilizationalModel": S,
                    "worldRules": arr(obj({"ruleName": S, "description": S, "constraint": S})), "themes": arr(S)})
ROSTER_SCHEMA = obj({"souls": arr(obj({"name": S, "aliases": arr(S), "essence": S, "woundsAndDesires": S,
                                       "relationships": S, "speechHabits": S, "continuityTripwire": S}))})


def generate_universe_bible(sort: dict, standing_laws: str, model: str, correction: str = "") -> dict:
    system = ("You are the Story Bible Architect. From pre-classified lore data, produce the canonical Universe Bible. "
              "You consolidate; you never drop a distinct rule or constraint. Respond ONLY with valid JSON.")
    rules = "\n".join(f"- {r['ruleName']}: {r['description']} (Constraint: {r['constraint']})" +
                      (f" [{'; '.join(r['sources'])}]" if r.get("sources") else "") for r in sort["worldRules"])
    themes = "\n".join(f"- {t}" for t in sort["themes"])
    beats = "\n".join(f"- [{a.get('phase', '')}] {a['event']} -> {a['irreversibleChange']}" for a in sort["arcBeats"])
    corr = f"\nCORRECTION FROM PREVIOUS ATTEMPT: {correction}\n" if correction else ""
    prompt = f"""
Generate the canonical UNIVERSE BIBLE from the classified intake data below.

=== STANDING LAWS (author's own definitions) ===
{standing_laws}

=== CLASSIFIED WORLD RULES (accumulated across every page; may contain overlapping notes) ===
{rules}

=== CLASSIFIED THEMES ===
{themes}

=== ARC BEATS (for context on how the rules play out) ===
{beats}

RULES:
1. Merge ONLY notes that describe the SAME mechanic (e.g. five wordings of the same ledger button become one entry), keeping EVERY distinct detail and constraint from all of its notes.
2. Do NOT fold different mechanics, factions, institutions or abilities into broad umbrella rules. Each distinct mechanic, faction ("Faction: ..."), law, technology and ability keeps its own entry, even if related.
3. Do not add rules that are not in the intake. Do not infer settings or tropes from names or surface details.
4. THE SINGLE TEST: if a sentence could appear in any other series, rewrite it until it could only belong to THIS universe.
{corr}
corePremise: 2-3 dense sentences grounded in the actual rules and mechanics.
civilizationalModel: the specific civilizational model; name the nest and the nexus; the physics events obey."""
    bible = generate_json(CallOptions(model=model, system=system, schema=BIBLE_SCHEMA), prompt)
    # Guard against over-compression: near-duplicate wordings collapse, distinct mechanics should not.
    distinct = len({re.sub(r"[^a-z0-9]+", " ", r["ruleName"].lower()).strip() for r in sort["worldRules"]})
    floor = int(distinct * 0.35)
    if not correction and len(bible.get("worldRules") or []) < floor:
        return generate_universe_bible(sort, standing_laws, model,
                                       f"You consolidated {distinct} rule notes into only {len(bible.get('worldRules') or [])} rules, which merges "
                                       "distinct mechanics together. Keep each distinct mechanic, faction, law, technology and ability as its own "
                                       "entry; merge only different wordings of the same mechanic.")
    return bible


def generate_soul_roster(souls: list[dict], bible: dict, model: str, clarifications: str = "", on_batch=None) -> dict:
    system = ("You are the Soul Codex Architect. From accumulated soul notes, produce canonical 7-point soul profiles. "
              "You consolidate every note about a soul; you do not invent. Respond ONLY with valid JSON.")
    # Most-documented souls first so the main cast is profiled with the most context
    ordered = sorted(souls, key=lambda s: len(s.get("sources") or []), reverse=True)
    total = (len(ordered) + ROSTER_BATCH_SIZE - 1) // ROSTER_BATCH_SIZE
    roster: list[dict] = []
    for i in range(0, len(ordered), ROSTER_BATCH_SIZE):
        if on_batch:
            on_batch(i // ROSTER_BATCH_SIZE + 1, total)
        batch = ordered[i:i + ROSTER_BATCH_SIZE]
        notes = "\n\n".join(
            f"## {s['name']}" + (f" (aliases: {', '.join(s['aliases'])})" if s.get("aliases") else "") +
            f"\nEssence notes: {s.get('essence', '')}\nWounds/Desires notes: {s.get('woundsAndDesires', '')}"
            f"\nRelationship notes: {s.get('relationships', '')}\nSpeech notes: {s.get('speechHabits') or '(none captured)'}"
            f"\nSources: {'; '.join(s.get('sources') or [])}" for s in batch)
        clar = f"=== AUTHOR CLARIFICATIONS (canon) ===\n{clarifications}\n\n" if clarifications else ""
        prompt = f"""
Build the canonical SOUL ROSTER entries for the souls below.

=== UNIVERSE BIBLE ===
Core Premise: {bible.get('corePremise', '')}
Civilizational Model: {bible.get('civilizationalModel', '')}

{clar}=== ACCUMULATED SOUL NOTES (every page's notes are kept; consolidate them) ===
{notes}

For EACH soul above (exactly {len(batch)} entries, same names), keep every distinct fact from its notes:
- essence: one sentence that could only describe THIS person
- woundsAndDesires: core wound, internal conflict, driving want - and how they develop across the notes
- relationships: key tensions, alliances, loyalties
- speechHabits: cadence, what they avoid saying, what they say instead
- continuityTripwire: the #1 thing most likely to be written wrong about this character"""
        roster.extend(_roster_batch(batch, prompt, system, model, retry=True))
    return {"souls": roster}


def _roster_batch(batch: list[dict], prompt: str, system: str, model: str, retry: bool) -> list[dict]:
    res = generate_json(CallOptions(model=model, system=system, schema=ROSTER_SCHEMA), prompt)
    entries = res.get("souls") or []
    # Keep the exact names the roster was asked for (a shortened name would collide with others)
    asked = {b["name"].lower().strip() for b in batch}
    for idx, entry in enumerate(entries):
        if entry.get("name", "").lower().strip() not in asked and idx < len(batch):
            entry["name"] = batch[idx]["name"]
    got = {e.get("name", "").lower().strip() for e in entries}
    missing = [b for b in batch if b["name"].lower().strip() not in got]
    if missing and retry:
        # A character left out of the answer is asked for again on its own, never silently dropped
        names = ", ".join(b["name"] for b in missing)
        entries += _roster_batch(missing, f"{prompt}\n\nOnly these characters are still needed: {names}.", system, model, retry=False)
    elif missing:
        entries += [{"name": b["name"], "aliases": b.get("aliases") or [], "essence": b.get("essence", ""),
                     "woundsAndDesires": b.get("woundsAndDesires", ""), "relationships": b.get("relationships", ""),
                     "speechHabits": b.get("speechHabits", ""), "continuityTripwire": "(profile built from the raw notes)"} for b in missing]
    return entries
