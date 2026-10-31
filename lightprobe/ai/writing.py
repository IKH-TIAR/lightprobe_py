"""STEPS 9-10 — Chapter writer (Cards 09 + LNF-03v2), LNF-09 audit, elevation (LNF-LPE), soul index
(LNF-02), volume PASS-OUT (LNF-SUM + handoff), foreshadowing subtlety audit."""

from __future__ import annotations

from ..llm import B, CallOptions, N, S, arr, enum, generate_json, generate_text, obj, parse_sections

CHAPTER_SECTIONS = ["TITLE", "CHAPTER_TEXT", "BACKGROUND_OVERFLOW", "LEDGER_ENTRY", "SOUL_UPDATES"]


def write_chapter(ctx: dict, model: str) -> dict:
    """ONE chapter from its own context bin. `ctx` keys: chapter, volumeNumber, standingCards, styleLock, canon,
    soulIndex, volumeArcMap, ledgerTail, previousChapterTail, sourceMaterial, seeds, payoffs, backgroundRef."""
    c = ctx["chapter"]
    system = ("You are the Master Light Probe Chapter Writer (LNF-03v2). You enter the scene physically, transmit the lived "
              "feed, and never summarize from outside. The standing cards below are law for every sentence.")
    cached = (f"=== STANDING CARDS (read before every chapter) ===\n{ctx['standingCards']}\n\n=== 01-AUTHOR-STYLE (Voice Lock) ===\n"
              f"{ctx['styleLock']}\n\n=== CANON (UNIVERSE BIBLE) ===\n{ctx['canon'] or '(Canon initializing)'}")
    seeds = (f"=== FORESHADOWING SEEDS TO PLANT IN THIS CHAPTER ===\nWeave each as an unremarkable, natural detail. A first-time reader "
             f"must take it as texture. Never draw attention to it.\n{ctx['seeds']}\n") if ctx.get("seeds") else ""
    payoffs = (f"=== FORESHADOWING PAYOFFS DUE IN THIS CHAPTER ===\nResolve these planned threads through concrete action, discovery, "
               f"consequence, or changed understanding. Honor the payoff description without forcing it or explaining the architecture.\n"
               f"{ctx['payoffs']}\n") if ctx.get("payoffs") else ""
    prompt = f"""
CHAPTER LOOP - Volume {ctx['volumeNumber']}, Chapter {c['chapterNumber']}

=== 02-SOUL-INDEX (most recent present of every soul) ===
{ctx['soulIndex'] or '(No soul index)'}

=== VOLUME ARC MAP (where this chapter sits; the next main events you are compounding toward) ===
{ctx['volumeArcMap']}

=== CHAPTER COORDINATE ===
Chapter {c['chapterNumber']}: "{c['title']}"
Pacing: {c.get('pacingType') or 'EXTENSIVE_DEEP_DIVE'} | Moment Genre: {c.get('momentGenre') or 'Light Probe detect'}
Focal Soul: {c.get('focalSoul') or '(Probe selects)'} | Time/Setting: {c.get('timeCoordinate') or '(from ledger)'}
Synopsis: {c['synopsis']}

=== AUTHOR'S SOURCE MATERIAL FOR THIS CHAPTER (EVENTS ONLY) ===
Canon for WHAT happens: events, facts, who is present, what is decided and revealed, the intent of key dialogue. Never contradict it.
It is NOT a style reference: these are old drafts and notes. Do not reuse their sentences, phrasing or rhythm, and do not imitate their prose. Write every line fresh in the locked author voice from the standing cards.
{ctx['sourceMaterial'] or '(No author material for this chapter - gap-fill from the arc map and canon only.)'}

=== CONTINUITY LEDGER (recent entries) ===
{ctx['ledgerTail'] or '(Volume opening - no prior entries; use PASS-IN state in the soul index.)'}

=== PREVIOUS CHAPTER - FINAL PASSAGE (continue the lived chain from here) ===
{ctx['previousChapterTail'] or '(This is the first chapter of the volume.)'}

{seeds}{payoffs}=== 05-BACKGROUND (reference only - never put this in the prose) ===
{ctx['backgroundRef'] or '(none)'}

PROTOCOL:
1. Pre-write reconstruction (02 card): who is where, who knows what, which threads are open.
2. Enter the scene physically at the coordinate. Find the best angle, not the obvious one.
3. SHOW, NEVER STATE: sensation -> action -> observation -> interior movement.
4. The outline is a coordinate. Do not pad. Do not summarize. Do not write past the most recent present.
5. Background the scene cannot carry -> BACKGROUND_OVERFLOW, never the prose.

OUTPUT FORMAT - use these exact markers, in this order, nothing before the first marker:
<<<TITLE>>>
Chapter {c['chapterNumber']}: <evocative title>
<<<CHAPTER_TEXT>>>
<the full chapter prose>
<<<BACKGROUND_OVERFLOW>>>
<lore the scene could not carry, or empty>
<<<LEDGER_ENTRY>>>
<dense 3-5 sentences: key events, soul-state changes, new canon, threads opened/closed, in-universe timestamp>
<<<SOUL_UPDATES>>>
<one line per soul whose state changed: "Name - what changed (physical/emotional/relational/knowledge)", or empty>
<<<END>>>"""
    text = generate_text(CallOptions(model=model, system=system, cached_context=cached), prompt)
    s = parse_sections(text, CHAPTER_SECTIONS)
    if not s["CHAPTER_TEXT"]:
        raise ValueError(f"Chapter {c['chapterNumber']}: the model response did not contain chapter text.")
    return {
        "chapterNumber": c["chapterNumber"],
        "title": s["TITLE"] or f"Chapter {c['chapterNumber']}: {c['title']}",
        "content": s["CHAPTER_TEXT"],
        "backgroundOverflow": s["BACKGROUND_OVERFLOW"],
        "ledgerEntry": s["LEDGER_ENTRY"],
        "soulUpdates": s["SOUL_UPDATES"],
    }


def audit_chapter(chapter_text: str, ledger_entry: str, chapter: dict, no_drift_card: str, voice_cards: str,
                  soul_index: str, ledger_tail: str, model: str) -> dict:
    """LNF-09 / 04-NO-DRIFT-NO-SLOP three checks, as a separate reviewer call (the writer does not grade itself)."""
    system = "You are the LNF-09 Finalization checker. You run the three checks and report only what needs fixing. Respond ONLY with valid JSON."
    cached = f"=== 04-NO-DRIFT-NO-SLOP ===\n{no_drift_card}\n\n=== VOICE CARDS ===\n{voice_cards}"
    prompt = f"""
Run the THREE CHECKS on Chapter {chapter['chapterNumber']} ("{chapter['title']}").

=== SOUL INDEX (most recent present) ===
{soul_index}

=== CONTINUITY LEDGER BEFORE THIS CHAPTER ===
{ledger_tail or '(volume opening)'}

=== CHAPTER TEXT ===
{chapter_text}

=== LEDGER ENTRY WRITTEN FOR THIS CHAPTER ===
{ledger_entry}

1. VOICE - matches the voice cards? Opens and closes on the right beat? No stated emotions, no slop phrases, nothing that could appear in any series?
2. CONTINUITY - any soul knowing what they have not learned, acting from a past state, or a world rule contradicted?
3. LEDGER ACCURACY - does the entry capture the key events, soul-state changes, new canon, threads opened and closed?

Use "PASS" for a passing check, otherwise a short specific fix list."""
    res = generate_json(CallOptions(model=model, system=system, cached_context=cached, effort="medium", schema=obj({
        "voice": S, "continuity": S, "noSlop": S, "ledger": S, "overall": enum("APPROVED", "NEEDS_REVISION"), "notes": S})), prompt)
    ledger_note = f" Ledger: {res['ledger']}" if res.get("ledger") and res["ledger"] != "PASS" else ""
    return {
        "voice": res.get("voice") or "PASS",
        "continuity": res.get("continuity") or "PASS",
        "noSlop": res.get("noSlop") or "PASS",
        "overall": "APPROVED" if res.get("overall") == "APPROVED" else "NEEDS_REVISION",
        "notes": f"{res.get('notes') or ''}{ledger_note}".strip(),
    }


def elevate_chapter(title: str, content: str, standing_cards: str, volume_context: str, model: str) -> dict:
    system = "You are an elite prose stylist executing the LNF-LPE Chapter Elevation protocol."
    prompt = f"""
LNF-LPE CHAPTER ELEVATION.

CONSTRAINTS:
1. Preserve exact POV, tense, tone, canon facts, plot beats, character actions, and world mechanics.
2. Elevate along the 9 Dimensions of Author Voice: rhythm, visceral physical sensation over abstraction, strip stated emotions and AI cliches, micro-actions in dialogue, openings in tension, closings on a physical action or decisive shift.

=== VOLUME CONTEXT (soul index + recent ledger) ===
{volume_context}

=== CURRENT CHAPTER: {title} ===
{content}

OUTPUT FORMAT - exact markers:
<<<CHAPTER_TEXT>>>
<the full elevated chapter>
<<<ELEVATION_NOTES>>>
<concise bullets of what was tightened>
<<<END>>>"""
    text = generate_text(CallOptions(model=model, system=system, cached_context=f"=== STANDING CARDS & AUTHOR STYLE ===\n{standing_cards}"), prompt)
    s = parse_sections(text, ["CHAPTER_TEXT", "ELEVATION_NOTES"])
    if not s["CHAPTER_TEXT"]:
        raise ValueError("Elevation response did not contain chapter text.")
    return {"title": title, "content": s["CHAPTER_TEXT"], "elevationNotes": s["ELEVATION_NOTES"]}


def soul_index_for_volume(soul_roster: str, pass_in: str, volume_number: int, volume_arc_map: str, model: str) -> str:
    system = ("You are the Soul Codex (LNF-02). You reconstruct the exact state of every soul at the opening of a volume. "
              "The most-recent-present is the ONLY present. No soul regresses. No soul knows what they haven't learned.")
    prompt = f"""
SOUL CODEX PROTOCOL - Volume {volume_number} Opening

=== CANONICAL SOUL ROSTER ===
{soul_roster}

=== PASS-IN FROM VOLUME {volume_number - 1} ===
{pass_in or '(First volume - no prior state. Use the Soul Roster baseline.)'}

=== VOLUME {volume_number} ARC MAP ===
{volume_arc_map or '(Arc map not yet generated)'}

For each soul appearing in this volume's arc map, write their 02-SOUL-INDEX entry:

## [SOUL NAME] - Status: MAIN / RECURRING / APPEARING (name the chapter for APPEARING)
- **Irreducible Essence**
- **Most Recent Present**: physical, emotional, relational state as of volume opening
- **Currently KNOWS**
- **Does NOT Know**
- **Changed Since PASS-IN**
- **Active Wound / Want** this volume
- **How They Speak**
- **Continuity Tripwire**

Write the full Soul Index as Markdown. One section per soul."""
    return generate_text(CallOptions(model=model, system=system), prompt)


def volume_pass_out(volume_number: int, ledger: str, soul_index: str, seed_status: str, last_chapter_tail: str,
                    next_volume_outline: str, model: str) -> dict:
    """Built from the ledger, soul index and seed status - not the raw prose - so it fits any volume size."""
    system = "You are the Master Continuity Archivist executing the canonical PASS-OUT / PASS-IN Volume Handoff Protocol."
    prompt = f"""
CANONICAL PASS-OUT PROTOCOL - Volume {volume_number}

=== FULL CONTINUITY LEDGER (one entry per chapter, chronological) ===
{ledger or '(No ledger entries)'}

=== SOUL INDEX (volume-opening state + per-chapter updates) ===
{soul_index or '(No soul index)'}

=== FORESHADOWING SEED STATUS ===
{seed_status or '(No seeds)'}

=== FINAL PASSAGE OF THE VOLUME ===
{last_chapter_tail or '(none)'}

=== NEXT VOLUME OUTLINE ===
{next_volume_outline or '(Final volume)'}

OUTPUT FORMAT - exact markers:
<<<PASS_OUT>>>
# VOLUME {volume_number} - PASS-OUT CONTINUITY DOSSIER
## 1. IRREVERSIBLE STATE CHANGES
## 2. 7-POINT SOUL CODEX (per active soul: Essence, Most Recent Present, KNOWS / Does NOT Know, Changes & Scars, Active Wound/Want, How They Speak, Continuity Tripwire)
## 3. ACTIVE CHEKHOV'S GUNS (setup location + intended detonation point)
## 4. UNRESOLVED THREADS
## 5. VOLUME {volume_number + 1} OPENING COORDINATES (timestamp, location, ambient pressure, immediate crisis)
<<<VOLUME_SUMMARY>>>
<one paragraph: what the timestamp was, what changed, where it left every main soul>
<<<END>>>"""
    text = generate_text(CallOptions(model=model, system=system), prompt)
    s = parse_sections(text, ["PASS_OUT", "VOLUME_SUMMARY"])
    if not s["PASS_OUT"]:
        raise ValueError(f"PASS-OUT for Volume {volume_number} was empty.")
    return {"passOutDoc": s["PASS_OUT"], "volumeSummary": s["VOLUME_SUMMARY"]}


def audit_subtlety(chapter_number: int, chapter_text: str, seeds: list[dict], model: str) -> list[dict]:
    system = "You are the Subtlety Auditor. You verify that foreshadowing seeds are invisible to first-time readers. Respond ONLY with valid JSON."
    listing = "\n\n".join(f"Thread: {s['threadName']}\nSeed: {s['setupDescription']}" for s in seeds)
    prompt = f"""
SUBTLETY AUDIT - Chapter {chapter_number}

A first-time reader should NEVER feel a detail is foreshadowing. Seeds must read as natural worldbuilding, texture, or behavior.

=== SEEDS TARGETED AT THIS CHAPTER ===
{listing}

=== CHAPTER TEXT ===
{chapter_text}

For each seed: was it planted (quote where)? SUBTLETY SCORE 1-10 (1 = screams foreshadowing, 10 = invisible). Would a first-time reader notice? If score < 7, a concrete revision."""
    res = generate_json(CallOptions(model=model, system=system, effort="medium", schema=obj({"seeds": arr(obj({
        "threadName": S, "found": B, "location": S, "subtletyScore": N, "firstTimeReaderNotice": S, "revision": S}))})), prompt)
    return res.get("seeds") or []
