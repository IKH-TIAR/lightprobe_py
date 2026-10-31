"""STEP 4 — Style Lab (Cards 03-AUTHOR-VOICE, LNF-VOICE / LNF-FORGE).

The creators test candidate author styles until one is right, then lock it:
- the author's own Voice DNA, extracted from their prose (events-only files excluded),
- a polished version of that voice, and
- distinct unique voices built for this universe,
each with a test passage of the SAME scene so they can be compared side by side.
"""

from __future__ import annotations

from ..llm import CallOptions, S, arr, generate_json, generate_text, obj

DNA_FIELDS = [
    ("overallVoiceSummary", "OVERALL VOICE"),
    ("sentenceRhythm", "1. SENTENCE RHYTHM"),
    ("diction", "2. DICTION"),
    ("paragraphShape", "3. PARAGRAPH SHAPE"),
    ("dialogueAttribution", "4. DIALOGUE ATTRIBUTION"),
    ("interiorityDepth", "5. INTERIORITY DEPTH"),
    ("sensoryPriority", "6. SENSORY PRIORITY"),
    ("timeHandling", "7. TIME HANDLING"),
    ("chapterOpeningClosing", "8. CHAPTER OPENING & CLOSING HABITS"),
    ("signatureMoves", "9. SIGNATURE MOVES"),
    ("neverDoes", "NEVER DOES"),
]
DNA_SCHEMA = obj({k: S for k, _ in DNA_FIELDS})
PROFILE_SCHEMA = obj({"name": S, "pitch": S, **{k: S for k, _ in DNA_FIELDS}})


def format_dna_doc(profile: dict, origin: str) -> str:
    body = "\n\n".join(f"## {label}\n{profile.get(key, '')}" for key, label in DNA_FIELDS)
    return f"# 03-AUTHOR-VOICE-DNA ({origin})\n\n{body}"


def format_profile_brief(profile: dict) -> str:
    return "\n".join(f"{label}: {profile.get(key, '')}" for key, label in DNA_FIELDS)


def extract_author_voice_dna(samples: list[str], universe_premise: str, model: str) -> dict:
    system = ("You are the LNF-VOICE / LNF-FORGE Voice DNA Extractor. You analyze actual prose samples to extract the "
              "author's unique writing fingerprint across 9 dimensions. Respond ONLY with valid JSON.")
    samples_text = "\n\n".join(f"=== WRITING SAMPLE {i + 1} ===\n{s}" for i, s in enumerate(samples))
    ctx = f"\nUniverse Context: {universe_premise}\n" if universe_premise else ""
    prompt = f"""
VOICE DNA EXTRACTION PROTOCOL (LNF-VOICE / LNF-FORGE)

Analyze the writing samples below and extract the author's voice across all 9 dimensions.
Do NOT impose generic "good writing" advice. Describe WHAT THIS AUTHOR ACTUALLY DOES, with quoted evidence.
{ctx}
{samples_text}

Fields: sentenceRhythm (length distribution, where breaks fall, staccato vs lyrical - with quotes), diction (signature lexicon,
register, recurring word choices, words never used), paragraphShape, dialogueAttribution (tags, beats, what carries speech),
interiorityDepth, sensoryPriority (which sense leads), timeHandling (compression, dilation, transitions), chapterOpeningClosing,
signatureMoves, neverDoes (prose moves this author avoids), overallVoiceSummary (3-4 dense sentences usable as the master voice instruction)."""
    return generate_json(CallOptions(model=model, system=system, schema=DNA_SCHEMA), prompt)


def propose_style_variants(author_dna: dict | None, universe_brief: str, voice_card: str, creator_notes: str, count: int, model: str) -> list[dict]:
    system = ("You are the Author Style Engine (LNF-FORGE). You design distinct, specific author voices for one universe. "
              "Every voice obeys the show-don't-tell law. Respond ONLY with valid JSON.")
    if author_dna:
        task = f"""Design {count} style candidates for this universe:
1. "Polished Author Voice": keep the author's own fingerprint below (rhythm, diction, signature moves) and polish and improve it - tighter, more physical, zero stated emotion, no telling.
{''.join(f'{i + 2}. A distinct UNIQUE voice for this universe, clearly different from the others in rhythm, diction and interiority.\n' for i in range(count - 1))}
=== THE AUTHOR'S OWN VOICE DNA (extracted from their prose) ===
{format_profile_brief(author_dna)}"""
    else:
        task = f"Design {count} distinct UNIQUE voices for this universe, clearly different from each other in rhythm, diction and interiority."
    notes = f"\n=== CREATOR NOTES (apply to every candidate) ===\n{creator_notes}\n" if creator_notes.strip() else ""
    prompt = f"""
{task}

=== THE AUTHOR VOICE STANDARD (client card 03-AUTHOR-VOICE) ===
{voice_card}

=== THIS UNIVERSE ===
{universe_brief}
{notes}
For each candidate give a short "name", a one-sentence "pitch" (how it reads), and all nine dimensions plus "neverDoes" and
"overallVoiceSummary" (3-4 dense sentences usable as the master voice instruction). Be concrete: name sentence lengths,
specific word choices, what leads each paragraph. Nothing that could describe any other series."""
    res = generate_json(CallOptions(model=model, system=system, schema=obj({"candidates": arr(PROFILE_SCHEMA)})), prompt)
    return (res.get("candidates") or [])[:count]


def refine_style(profile: dict, feedback: str, universe_brief: str, model: str) -> dict:
    system = "You are the Author Style Engine (LNF-FORGE). You revise one author voice from the creators' feedback. Respond ONLY with valid JSON."
    prompt = f"""
Revise this style candidate according to the creators' feedback. Keep everything the feedback does not ask to change.

=== CURRENT CANDIDATE: {profile.get('name', '')} ===
{format_profile_brief(profile)}

=== CREATOR FEEDBACK ===
{feedback}

=== THIS UNIVERSE ===
{universe_brief}

Return the revised candidate with the same fields (keep the name unless the feedback renames it)."""
    return generate_json(CallOptions(model=model, system=system, schema=PROFILE_SCHEMA), prompt)


def write_style_sample(profile: dict, scene_brief: str, canon: str, standing_rules: str, model: str) -> str:
    system = ("You are the Master Light Probe Chapter Writer writing a STYLE TEST passage. You write in exactly the voice "
              "described, enter the scene physically, and never summarize from outside.")
    cached = f"=== STANDING RULES ===\n{standing_rules}\n\n=== CANON ===\n{canon}"
    prompt = f"""
Write a 700-900 word test passage of the scene below, entirely in this voice:

=== VOICE: {profile.get('name', '')} ===
{format_profile_brief(profile)}

=== SCENE TO WRITE ===
{scene_brief}

Show, never state. Stay inside the canon. Output only the passage - no title, no notes."""
    return generate_text(CallOptions(model=model, system=system, cached_context=cached, max_tokens=8000), prompt).strip()
