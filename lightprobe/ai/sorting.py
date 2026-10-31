"""STEP 1 — MESS Sorter (Card 08), clarification checker, and character identity checks.

Every page of every file is read in order; nothing is sampled. Draft scenes and voice samples are
located by anchor quotes and copied verbatim from the source, so the model never re-types (and so
never compresses) the author's own text.
"""

from __future__ import annotations

import logging
import re

from ..llm import CallOptions, I, S, TruncatedOutputError, arr, enum, generate_json, obj

log = logging.getLogger("lightprobe.sort")

MESS_PAGE_SIZE = 24000
MIN_SPLIT_PAGE = 4000


def paginate(content: str, page_size: int = MESS_PAGE_SIZE) -> list[str]:
    """Splits a file into sequential pages, cutting on paragraph/line boundaries where possible."""
    pages, pos = [], 0
    while pos < len(content):
        end = min(pos + page_size, len(content))
        if end < len(content):
            window_start = pos + int(page_size * 0.6)
            window = content[window_start:end]
            para, line = window.rfind("\n\n"), window.rfind("\n")
            cut = para + 2 if para >= 0 else (line + 1 if line >= 0 else -1)
            if cut > 0:
                end = window_start + cut
        pages.append(content[pos:end])
        pos = end
    return pages


# Characters the model often retypes differently from the page (curly vs straight quotes, dashes)
_LOOSE = {
    "'": "['‘’ʼ`]", "‘": "['‘’ʼ`]", "’": "['‘’ʼ`]",
    '"': "[\"“”]", "“": "[\"“”]", "”": "[\"“”]",
    "-": "[-–—]", "–": "[-–—]", "—": "[-–—]",
    "…": r"(?:…|\.\.\.)",
}


def _anchor_regex(words: list[str]) -> re.Pattern | None:
    if len(words) < 2:
        return None
    parts = ["".join(_LOOSE.get(ch, re.escape(ch)) for ch in w) for w in words]
    return re.compile(r"\s+".join(parts), re.I)


def extract_span(page: str, starts_with: str | None, ends_with: str | None) -> tuple[str | None, bool]:
    """Locates the author's verbatim span on the page from the model's start/end anchor quotes.
    Returns (text, exact). When the end anchor is not found the passage runs to the end of the page and
    is marked inexact - it is never cut short."""
    if not starts_with:
        return None, False
    start_re = _anchor_regex(starts_with.split()[:12])
    m = start_re.search(page) if start_re else None
    if not m:
        return None, False
    frm = m.start()
    if ends_with:
        end_re = _anchor_regex(ends_with.split()[-12:])
        if end_re:
            rest = page[frm:]
            em = end_re.search(rest)
            if em:
                return rest[:em.end()], True
    return page[frm:], False


PAGE_SORT_SCHEMA = obj({
    "souls": arr(obj({"name": S, "aliases": arr(S), "essence": S, "woundsAndDesires": S, "relationships": S, "speechHabits": S})),
    "worldRules": arr(obj({"ruleName": S, "description": S, "constraint": S})),
    "arcBeats": arr(obj({"phase": S, "event": S, "irreversibleChange": S})),
    "chapterMaterial": arr(obj({"volumeHint": S, "summary": S, "startsWith": S, "endsWith": S})),
    "voiceSamples": arr(obj({"preview": S, "startsWith": S, "endsWith": S})),
    "themes": arr(S),
    "unclear": arr(obj({"quote": S, "question": S})),
    "logistics": arr(S),
})


def sort_mess_page(file_name: str, page_label: str, page_text: str, rolling_context: str, model: str, events_only: bool = False) -> dict:
    system = ("You are the MESS Sorter (Card 08). You classify raw creative notes into structured categories. "
              "You NEVER guess, NEVER skip content, and NEVER invent facts that are not on the page. Respond ONLY with valid JSON.")
    events_rule = ("\n4. EVENTS-ONLY FILE: the author has rejected this file's writing style. Extract its events, facts and characters, "
                   "but classify its prose as CHAPTER-MATERIAL - NEVER as VOICE-SAMPLE.") if events_only else ""
    prompt = f"""
MESS SORTER PROTOCOL - classify every distinct piece of this intake page.

FILE: "{file_name}" - {page_label}

=== ROLLING CONTEXT (what earlier pages already established) ===
{rolling_context or '(First page - no prior context)'}

=== RAW CONTENT TO CLASSIFY ===
{page_text}

CLASSIFICATION RULES:
1. Read everything on this page. Every distinct piece goes into exactly one category:
   - SOUL: one individual in-universe character - essence, wounds, desires, relationships, speech habits. Use the name as written. "aliases" holds ONLY other names/nicknames/spellings that the page explicitly uses for THIS same person, exactly as written. Never another person (even one with the same surname or title, like a different coach or officer), never a bare role ("Coach", "Captain"), never a description or comment. When unsure, leave it out. If a soul from the rolling context appears, use the SAME name.
     Different names are different people unless the page says otherwise - similar names (e.g. "Sato" vs "Saito") and reversed name orders used in different storylines are NOT automatically the same person. An unnamed person gets a name tied to who they are to someone (e.g. "the heroine's mother"); never file them under a named character unless the page names them.
     NOT souls: groups, factions, teams, institutions, forces (-> WORLD-RULE named "Faction: <name>"); real-world people referenced as inspiration or in pasted transcripts/articles (-> THEME as "Reference: <name> - <why it matters>", or UNCLEAR if you cannot tell whether they are in-universe).
   - WORLD-RULE: civilizational mechanics, laws, technology constraints, physical limits, factions. When this page adds to a rule already listed in the rolling context, reuse that rule's EXACT name so the notes merge.
   - ARC-BEAT: turning points, crises, irreversible changes, timeline events. Put any volume/arc/time marker the notes give in "phase".
   - CHAPTER-MATERIAL: draft scenes, dialogue, prose passages, chapter stubs. Do NOT retype them. Give "startsWith" (the first 8-12 words copied EXACTLY from the page) and "endsWith" (the last 8-12 words copied EXACTLY) so the engine can extract the author's verbatim text, plus a one-sentence "summary" and a "volumeHint" if the page states one (else "").
   - VOICE-SAMPLE: ONLY finished narrative prose written in the author's own storytelling voice (scene narration with the author's rhythm and style). NOT notes, outlines, plans, analysis, lyrics, transcripts, or chat - those are CHAPTER-MATERIAL, THEME or LOGISTICS. Same anchor rule: "startsWith"/"endsWith" copied exactly, plus a short "preview".
   - THEME: civilizational themes, systemic patterns.
   - UNCLEAR: ONLY a real contradiction - this page states something that conflicts with the rolling context or with itself (e.g. two different versions of the same scene or relationship). Give the exact quote and say what it conflicts with.
     Do NOT flag: which volume something belongs to (a later step places material using the whole universe), spelling variants of known names (add them as aliases), or whether a passage is reference/inspiration (classify it as THEME "Reference: ...").
   - LOGISTICS: non-story items (scheduling, meta-discussion).
2. Facts only from this page. Keep each field dense (1-3 sentences). If a field is not on the page, use "".
3. Solve along the way: use the rolling context to decide. Leave volume placement to "volumeHint" when the page states one.{events_rule}

Respond with JSON matching the schema."""
    try:
        raw = generate_json(CallOptions(model=model, system=system, effort="medium", schema=PAGE_SORT_SCHEMA), prompt)
    except TruncatedOutputError:
        # Lossless recovery: a page too dense for one response is split in half and sorted as two pages.
        if len(page_text) <= MIN_SPLIT_PAGE:
            raise
        log.warning("%s %s too dense for one response - splitting", file_name, page_label)
        halves = paginate(page_text, len(page_text) // 2 + 1)
        parts = [sort_mess_page(file_name, f"{page_label} (part {h + 1}/{len(halves)})", half, rolling_context, model, events_only)
                 for h, half in enumerate(halves)]
        return {k: [x for p in parts for x in p[k]] for k in parts[0]}

    # anchor: "exact" (start and end found), "open-end" (end not found: kept to the page end, never cut short),
    # "missing" (start not found: only the model's quotes survive)
    def material(m: dict) -> dict:
        span, exact = extract_span(page_text, m.get("startsWith"), m.get("endsWith"))
        return {
            "volumeHint": m.get("volumeHint") or "",
            "summary": m.get("summary") or "",
            "text": span if span is not None else " ... ".join(x for x in (m.get("startsWith"), m.get("endsWith")) if x),
            "verbatim": exact,
            "anchor": "exact" if exact else ("open-end" if span is not None else "missing"),
        }

    voice = []
    for v in raw.get("voiceSamples") or []:
        span, exact = extract_span(page_text, v.get("startsWith"), v.get("endsWith"))
        if span is not None and not exact:
            continue  # a voice sample must be exactly the author's passage; an open-ended span may include other text
        text = span if span is not None else (v.get("preview") or "")
        if text:
            voice.append({"text": text, "verbatim": exact, "anchor": "exact" if exact else "missing"})
    return {
        "souls": [s for s in raw.get("souls") or [] if s.get("name")],
        "worldRules": [r for r in raw.get("worldRules") or [] if r.get("ruleName")],
        "arcBeats": [a for a in raw.get("arcBeats") or [] if a.get("event")],
        "chapterMaterial": [material(m) for m in raw.get("chapterMaterial") or []],
        "voiceSamples": voice,
        "themes": raw.get("themes") or [],
        "unclear": raw.get("unclear") or [],
        "logistics": raw.get("logistics") or [],
    }


def resolve_unclear_batch(intake_digest: str, items: list[dict], open_so_far: list[dict], model: str) -> list[dict]:
    """Each page was sorted with only a short rolling summary of earlier pages, so many flagged items are
    answered elsewhere in the notes. Checks a batch against the WHOLE sorted intake; resolves only what
    the intake states outright - anything else stays OPEN for the creators."""
    system = ("You are the MESS Sorter's clarification checker. You answer intake questions ONLY from what the author's "
              "sorted notes state. You never guess. Respond ONLY with valid JSON.")
    cached = f"=== THE AUTHOR'S FULL SORTED INTAKE (all files) ===\n{intake_digest}"
    open_list = ("=== QUESTIONS ALREADY LEFT OPEN (for duplicate detection) ===\n" +
                 "\n".join(f"[{o['id']}] {o['question']}" for o in open_so_far) + "\n") if open_so_far else ""
    questions = "\n\n".join(f"[{it['id']}] {{{it.get('source') or 'unknown source'}}}\nQuote: \"{it['quote']}\"\nQuestion: {it['question']}" for it in items)
    prompt = f"""
These questions were raised while sorting individual pages. The sorter could not see the rest of the notes at the time.
Check each one against the full sorted intake above.

{open_list}=== QUESTIONS TO CHECK ===
{questions}

For EACH question:
- "RESOLVED": the intake clearly answers it (e.g. an alias list shows two names are one soul, a beat places the event). "answer" = the answer in one or two sentences; "evidence" = the soul/rule/beat ids, names or sources that show it.
- "DUPLICATE": it asks the same thing as another question (in this batch or the already-open list). "duplicateOf" = that question's id.
- "OPEN": the intake does not settle it, or only an inference would. Leave "answer" empty - the creators will answer.
Use "" for fields that do not apply."""
    res = generate_json(CallOptions(model=model, system=system, cached_context=cached, effort="medium",
                                    schema=obj({"results": arr(obj({"id": S, "status": enum("RESOLVED", "DUPLICATE", "OPEN"),
                                                                    "answer": S, "evidence": S, "duplicateOf": S}))})), prompt)
    return res.get("results") or []


def group_soul_aliases(souls: list[dict], model: str, clarifications: str = "") -> dict:
    """Identity check before the Soul Roster: which entries are the same person, which are not individual
    characters, which aliases are attached to the wrong person, and which entries mix two people's notes."""
    if not souls:
        return {"groups": [], "wrongAliases": {}, "mixedEntries": []}
    system = ("You are the Soul Codex identity resolver. You decide which character entries refer to the same person, which "
              "entries are not individual characters, and which aliases or notes were attached to the wrong person. Respond ONLY with valid JSON.")

    def preview(s: dict) -> str:
        lines = [l for l in (s.get("essence") or "").split("\n") + (s.get("relationships") or "").split("\n") if l.strip()]
        return " | ".join(l[:180] for l in lines[:4])

    entries = "\n".join(f'- "{s["name"]}"' + (f" (aliases: {', '.join(s['aliases'])})" if s.get("aliases") else "") + f": {preview(s)}" for s in souls)
    clar = f"\n=== AUTHOR CLARIFICATIONS (canon - these override your judgment) ===\n{clarifications}" if clarifications else ""
    prompt = f"""
These character entries were extracted page by page from the author's notes. Some may be the same person under a nickname, title, or spelling variant (the notes include voice-transcription misspellings). Some may also carry mistakes from sorting.

{entries}

1. "groups": group entries ONLY when the notes make it clear they are the same person. When unsure, keep them separate.
   Every entry name must appear in exactly one group. "canonical" is the fullest proper name.
   "kind": PERSON (an individual in-universe character), GROUP (a faction, team, family unit, institution, force, or unnamed collective), REFERENCE (a real-world person cited as inspiration or from a pasted transcript).
2. "wrongAliases": for each entry, list aliases that do NOT refer to that person: another character's name, a different person who shares a surname or title (e.g. another coach or officer), a bare role ("Coach", "Captain"), or a description/comment instead of a name.
3. "mixedEntries": entry names whose notes clearly describe two or more different people (e.g. a coach's notes inside a student's entry). Only when the notes show it.{clar}"""
    res = generate_json(CallOptions(model=model, system=system, effort="medium", schema=obj({
        "groups": arr(obj({"canonical": S, "members": arr(S), "kind": enum("PERSON", "GROUP", "REFERENCE")})),
        "wrongAliases": arr(obj({"name": S, "aliases": arr(S)})),
        "mixedEntries": arr(S),
    })), prompt)
    names = {s["name"] for s in souls}
    seen: set[str] = set()
    groups = []
    for g in res.get("groups") or []:
        members = [m for m in g.get("members") or [] if m in names and m not in seen]
        seen.update(members)
        if members:
            groups.append({"canonical": g.get("canonical") or members[0], "kind": g.get("kind") or "PERSON", "members": members})
    for s in souls:
        if s["name"] not in seen:
            groups.append({"canonical": s["name"], "members": [s["name"]], "kind": "PERSON"})
    wrong = {w["name"]: w["aliases"] for w in res.get("wrongAliases") or [] if w.get("name") in names and w.get("aliases")}
    mixed = [n for n in res.get("mixedEntries") or [] if n in names]
    return {"groups": groups, "wrongAliases": wrong, "mixedEntries": mixed}


def split_merged_soul(soul_name: str, aliases: list[str], numbered_notes: str, other_people: list[dict], model: str) -> dict:
    """Repairs a character entry that absorbed notes about other characters. The model only returns line
    NUMBERS to move and the cleaned alias list - note text is never re-typed, so nothing is reworded or dropped."""
    system = ("You are the Soul Codex identity repairer. You identify notes that were wrongly merged into one character's "
              "entry. Respond ONLY with valid JSON.")
    people = "\n".join(f"- {p['name']} - {p['preview']}" for p in other_people)
    prompt = f"""
The entry for "{soul_name}" was built by merging notes page by page. Because of a name-matching mistake, some numbered note lines may be about OTHER characters, and some aliases may be other characters' names.

=== OTHER CHARACTERS IN THIS UNIVERSE (exact name - who they are) ===
{people}

=== ENTRY: {soul_name} ===
Aliases: {', '.join(aliases)}

Numbered note lines:
{numbered_notes}

1. "moved": list ONLY the lines that are about a DIFFERENT person (the line describes that other person - not lines about {soul_name} that merely mention someone else). Give the line number and that person's name:
   - if they are in the list above, their exact name from the list;
   - if they are clearly a different person who is NOT in the list (e.g. an unnamed relative, or someone with a similar but different name such as "Sato" vs "Saito"), a short distinct name built from the notes, such as "the heroine's mother" or "Ken Mori (murdered professor)". Use the same new name for every line about that person.
   A matching or reversed name is NOT enough to use an existing entry: check that the role, storyline and age fit that entry (the line preview after each name shows who they are).
   If you are unsure whether a line is about a different person, do NOT list it.
2. "aliases": only names, nicknames, titles and spellings that refer to {soul_name}. Remove any that belong to another person."""
    return generate_json(CallOptions(model=model, system=system, effort="medium",
                                     schema=obj({"aliases": arr(S), "moved": arr(obj({"line": I, "toName": S}))})), prompt)


