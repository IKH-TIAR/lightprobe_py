"""STAGE 1 — MESS sort (Card 08) and the creators' questions.

Every page of every MESS file is read in order. Resumable: a file is committed only once it is fully
sorted, so a stopped run continues at that file without duplicating half of it. Re-running sorts only
new or changed files unless `fresh` is set.
"""

from __future__ import annotations

from datetime import datetime

from .. import storage
from ..ai import planning_model
from ..jobs import JobStopped
from ..ai.sorting import paginate, resolve_unclear_batch, sort_mess_page
from .common import (Progress, format_clarifications, invalidate_downstream, is_events_only, key, merge_rule, merge_soul, next_id, no_progress,
                     source_file)

RESOLVE_BATCH_SIZE = 40
CLARIFICATIONS_FILE = "AUTHOR-CLARIFICATIONS.md"


def empty_sort() -> dict:
    return {"souls": [], "worldRules": [], "arcBeats": [], "chapterMaterial": [], "voiceSamples": [], "themes": [],
            "unclear": [], "logistics": [], "processedFiles": [], "complete": False}


def _new_working_set() -> dict:
    return {"souls": [], "worldRules": [], "arcBeats": [], "chapterMaterial": [], "voiceSamples": [], "themes": [],
            "unclear": [], "logistics": [], "anchorMisses": 0}


def _merge_page(ws: dict, page: dict, source: str) -> None:
    for s in page["souls"]:
        merge_soul(ws["souls"], s, source)
    for r in page["worldRules"]:
        merge_rule(ws["worldRules"], r, source)
    ws["arcBeats"] += [{**a, "source": source} for a in page["arcBeats"]]
    ws["chapterMaterial"] += [{**m, "source": source} for m in page["chapterMaterial"]]
    ws["voiceSamples"] += [{**v, "source": source} for v in page["voiceSamples"]]
    ws["themes"] += page["themes"]
    ws["unclear"] += [{**u, "source": source} for u in page["unclear"]]
    ws["logistics"] += page["logistics"]
    ws["anchorMisses"] += sum(1 for m in page["chapterMaterial"] if not m["verbatim"]) + sum(1 for v in page["voiceSamples"] if not v["verbatim"])


def _commit(acc: dict, store: dict, ws: dict) -> None:
    for s in ws["souls"]:
        merge_soul(acc["souls"], s)
    for r in ws["worldRules"]:
        merge_rule(acc["worldRules"], r)
    # Ids are never reused, even after a changed file's old items were removed (persistent counters)
    counters = acc.setdefault("nextIds", {})

    def take(prefix: str, existing: list[str], count: int) -> int:
        start = max(counters.get(prefix, 1), next_id(existing, prefix))
        counters[prefix] = start + count
        return start

    b = take("B-", [x["id"] for x in acc["arcBeats"]], len(ws["arcBeats"]))
    for a in ws["arcBeats"]:
        acc["arcBeats"].append({"id": f"B-{b}", **a})
        b += 1
    m_n = take("M-", list(store["items"]) + [x["id"] for x in acc["chapterMaterial"]], len(ws["chapterMaterial"]))
    for m in ws["chapterMaterial"]:
        mid = f"M-{m_n}"
        m_n += 1
        acc["chapterMaterial"].append({"id": mid, "volumeHint": m["volumeHint"], "content": m["summary"] or m["text"][:300],
                                       "source": m["source"], "verbatimChars": len(m["text"]) if m["verbatim"] else 0, "anchor": m.get("anchor", "")})
        store["items"][mid] = {"kind": "CHAPTER_MATERIAL", "source": m["source"], "text": m["text"], "verbatim": m["verbatim"], "anchor": m.get("anchor", "")}
    v_n = take("V-", list(store["items"]), len(ws["voiceSamples"]))
    for v in ws["voiceSamples"]:
        store["items"][f"V-{v_n}"] = {"kind": "VOICE_SAMPLE", "source": v["source"], "text": v["text"], "verbatim": v["verbatim"]}
        v_n += 1
    _voice_previews(acc, store)
    for t in ws["themes"]:
        if not any(key(e) == key(t) for e in acc["themes"]):
            acc["themes"].append(t)
    u_n = take("U-", [x["id"] for x in acc["unclear"]], len(ws["unclear"]))
    for u in ws["unclear"]:
        acc["unclear"].append({"id": f"U-{u_n}", "status": "OPEN", **u})
        u_n += 1
    acc["logistics"] += ws["logistics"]


def _voice_previews(acc: dict, store: dict) -> None:
    acc["voiceSamples"] = [it["text"][:300] + ("..." if len(it["text"]) > 300 else "") for it in store["items"].values() if it["kind"] == "VOICE_SAMPLE"]


def _purge_file(acc: dict, store: dict, file_name: str) -> int:
    """Removes what an earlier sort took from a file that has since changed or been deleted, so re-sorting it
    never duplicates material. Character and rule notes are merged text and cannot be separated by file;
    the file is only removed from their sources (identical notes are not duplicated when re-sorted)."""
    of_file = lambda x: source_file(x.get("source", "")) == file_name  # noqa: E731
    before = len(acc["arcBeats"]) + len(acc["chapterMaterial"])
    acc["arcBeats"] = [x for x in acc["arcBeats"] if not of_file(x)]
    acc["chapterMaterial"] = [x for x in acc["chapterMaterial"] if not of_file(x)]
    acc["unclear"] = [x for x in acc["unclear"] if not of_file(x)]
    for k in [k for k, it in store["items"].items() if of_file(it)]:
        del store["items"][k]
    _voice_previews(acc, store)
    for s in acc["souls"] + acc["worldRules"]:
        s["sources"] = [x for x in s.get("sources") or [] if source_file(x) != file_name]
    acc["processedFiles"] = [p for p in acc["processedFiles"] if p["name"] != file_name]
    return before - len(acc["arcBeats"]) - len(acc["chapterMaterial"])


def _rolling_context(acc: dict, ws: dict) -> str:
    souls = list(acc["souls"]) + [s for s in ws["souls"] if not any(key(e["name"]) == key(s["name"]) for e in acc["souls"])]
    rules = list(dict.fromkeys(r["ruleName"] for r in acc["worldRules"] + ws["worldRules"]))
    recent = (acc["arcBeats"] + ws["arcBeats"])[-6:]
    parts = []
    if souls:
        parts.append("Souls established so far (use these exact names):\n" + "\n".join(
            f"- {s['name']}" + (f" (aka {', '.join(s['aliases'])})" if s.get("aliases") else "") + f": {(s.get('essence') or '').split(chr(10))[0][:120]}"
            for s in souls))
    if rules:
        parts.append("World rules established: " + "; ".join(rules))
    if recent:
        parts.append("Most recent arc beats:\n" + "\n".join(f"- [{b.get('phase', '')}] {b['event']}" for b in recent))
    return "\n\n".join(parts)


def run_ingestion(name: str, state: dict, fresh: bool = False, progress: Progress = no_progress) -> dict:
    files = storage.get_mess_files(name)
    if not files:
        raise ValueError("The MESS folder is empty. Add the author's files first.")
    resume = not fresh and bool(state.get("messSortResult"))
    acc = state["messSortResult"] if resume else empty_sort()
    store = storage.get_sorted_material(name) if resume else {"items": {}}
    acc.setdefault("processedFiles", [])
    done = lambda f: any(p["name"] == f["name"] and p["size"] == len(f["content"]) for p in acc["processedFiles"])  # noqa: E731
    log_lines = []
    # A file that changed since it was sorted, or was removed from MESS: drop what was taken from it first
    current = {f["name"] for f in files}
    stale = [p["name"] for p in acc["processedFiles"] if p["name"] not in current or not done({"name": p["name"], "content": next(
        (f["content"] for f in files if f["name"] == p["name"]), "")})]
    for f in stale:
        removed = _purge_file(acc, store, f)
        log_lines.append(f"- {f}: {'removed from MESS' if f not in current else 'changed'} - {removed} earlier items from it were removed")
    changed = fresh or bool(stale) or any(not done(f) for f in files)
    if changed:
        acc["complete"] = False
        # Everything after the intake is built on item ids; it must be rebuilt from the new sort
        backup = invalidate_downstream(name, state, "INGESTION_REVIEW", "resort", ("bins", "gapFill", "plan", "payoffPlan"))
        if backup:
            progress(f"The volume bins, gap-fill and outlines built on the previous sort were saved to _backups/{backup}.", 1)
    if stale:
        state["messSortResult"] = acc
        storage.save_sorted_material(name, store)
        storage.save_state(name, state)

    total_chars = sum(len(f["content"]) for f in files) or 1
    done_chars = 0
    model = planning_model(state)
    for i, f in enumerate(files):
        if done(f):
            done_chars += len(f["content"])
            log_lines.append(f"- {f['name']}: already sorted (resumed run)")
            continue
        pages = paginate(f["content"])
        ws = _new_working_set()
        for p, page in enumerate(pages):
            progress(f'Sorting "{f["name"]}" - page {p + 1}/{len(pages)} ({len(acc["souls"]) + len(ws["souls"])} souls, '
                     f'{len(acc["worldRules"]) + len(ws["worldRules"])} rules, {len(acc["arcBeats"]) + len(ws["arcBeats"])} beats so far)',
                     min(97, round(2 + done_chars / total_chars * 95)), file=f["name"], fileIndex=i + 1, totalFiles=len(files))
            result = sort_mess_page(f["name"], f"Page {p + 1}/{len(pages)}", page, _rolling_context(acc, ws), model, is_events_only(state, f["name"]))
            _merge_page(ws, result, f"{f['name']} p.{p + 1}")
            done_chars += len(page)
        _commit(acc, store, ws)
        acc["processedFiles"] = [p for p in acc["processedFiles"] if p["name"] != f["name"]] + [{"name": f["name"], "size": len(f["content"]), "pages": len(pages)}]
        log_lines.append(f"- {f['name']}: {len(pages)} pages -> {len(ws['souls'])} souls, {len(ws['worldRules'])} rules, {len(ws['arcBeats'])} beats, "
                         f"{len(ws['chapterMaterial'])} draft passages, {len(ws['voiceSamples'])} voice samples, {len(ws['unclear'])} unclear"
                         + (f", {ws['anchorMisses']} passages whose start or end quote did not match the page (see Review Intake)" if ws["anchorMisses"] else ""))
        # Checkpoint after every file
        state["messSortResult"] = acc
        storage.save_sorted_material(name, store)
        storage.save_state(name, state)

    acc["complete"] = True
    state["messSortResult"] = acc
    state["status"] = "INGESTION_REVIEW"
    storage.save_sorted_material(name, store)
    storage.save_state(name, state)
    storage.write_mess_file(name, "_sort-log.md",
                            f"# MESS Sort Log\n\n{datetime.now().isoformat(timespec='seconds')}\n\n" + "\n".join(log_lines) +
                            f"\n\nTotals: {len(acc['souls'])} souls, {len(acc['worldRules'])} rules, {len(acc['arcBeats'])} arc beats, "
                            f"{len(acc['chapterMaterial'])} draft passages, {len(acc['voiceSamples'])} voice samples, {len(acc['unclear'])} unclear.")
    write_ask_me(name, state)

    # Solve along the way: check flagged items against the whole intake (a failure never undoes the sort)
    if any(u.get("status", "OPEN") == "OPEN" for u in acc["unclear"]):
        try:
            run_resolve_unclear(name, state, progress)
        except JobStopped:
            raise
        except Exception as err:  # noqa: BLE001
            progress(f"Checking the flagged items stopped ({err}). Run it again from Review Intake.", 99)
    c = count_unclear(acc)
    progress(f"Sorted {len(files)} files: {len(acc['souls'])} souls, {len(acc['worldRules'])} rules, {len(acc['arcBeats'])} arc beats. "
             f"{c['OPEN']} questions left for you (optional).", 100)
    return state


def write_ask_me(name: str, state: dict) -> None:
    """MESS/_ask-me.md: every open question for the creators (intake contradictions, unplaced material,
    gap-fill questions)."""
    sort = state.get("messSortResult") or {}
    sections = []
    open_items = [u for u in sort.get("unclear") or [] if u.get("status", "OPEN") == "OPEN"]
    if open_items:
        sections.append("## Contradictions in the notes\n\n" + "\n\n---\n\n".join(
            f"> \"{u['quote']}\"\nQuestion [{u['id']}]: {u['question']}" + (f"\nSource: {u['source']}" if u.get("source") else "") for u in open_items))
    unplaced = (state.get("bins") or {}).get("unplaced") or []
    if unplaced:
        idx = {b["id"]: b for b in sort.get("arcBeats") or []} | {m["id"]: m for m in sort.get("chapterMaterial") or []}
        sections.append("## Material that could not be placed in a volume\n\n" + "\n".join(
            f"- [{i}] {(idx.get(i) or {}).get('event') or (idx.get(i) or {}).get('content', '')}"[:400] for i in unplaced))
    gap_q = []
    for vol, gv in sorted(((state.get("gapFill") or {}).get("volumes") or {}).items(), key=lambda x: int(x[0])):
        for q in gv.get("questions") or []:
            if not (q.get("answer") or "").strip():
                gap_q.append(f"- Volume {vol} [{q['id']}]: {q['question']}" + (f" ({q['why']})" if q.get("why") else ""))
    if gap_q:
        sections.append("## Gap-fill questions\n\n" + "\n".join(gap_q))
    storage.write_mess_file(name, "_ask-me.md", "# Questions for the creators\n\n" + ("\n\n".join(sections) if sections else "(none open)"))


def write_clarifications(name: str, state: dict) -> None:
    text = format_clarifications(state.get("messSortResult"))
    storage.write_core(name, CLARIFICATIONS_FILE, "# AUTHOR CLARIFICATIONS (canon)\n\nAnswers to questions raised during the MESS sort. "
                                                  f"Author answers override everything else.\n\n{text or '(none yet)'}")
    write_ask_me(name, state)


def _intake_digest(sort: dict) -> str:
    line = lambda s, n: " ".join((s or "").split())[:n]  # noqa: E731
    return "\n\n".join([
        "SOULS:\n" + "\n".join(f"- {s['name']}" + (f" (aka {', '.join(s['aliases'])})" if s.get("aliases") else "") +
                               f": {line(s.get('essence'), 300)} | {line(s.get('relationships'), 150)} {{{'; '.join((s.get('sources') or [])[:4])}}}" for s in sort["souls"]),
        "WORLD RULES:\n" + "\n".join(f"- {r['ruleName']}: {line(r['description'], 200)}" for r in sort["worldRules"]),
        "ARC BEATS:\n" + "\n".join(f"- [{b['id']}] ({b.get('phase', '')}) {line(b['event'], 200)} {{{b.get('source', '')}}}" for b in sort["arcBeats"]),
        "DRAFT MATERIAL:\n" + "\n".join(f"- [{m['id']}] (hint: {m.get('volumeHint') or 'none'}) {line(m['content'], 200)} {{{m.get('source', '')}}}" for m in sort["chapterMaterial"]),
        "THEMES:\n" + "\n".join(f"- {line(t, 160)}" for t in sort["themes"]),
    ])


def run_resolve_unclear(name: str, state: dict, progress: Progress = no_progress) -> dict:
    """Checks every OPEN question against the whole sorted intake. Exact repeats collapse without a model
    call; the rest are resolved, marked duplicate, or left OPEN for the creators. Answers are never touched."""
    sort = state.get("messSortResult")
    if not sort or not sort.get("complete"):
        raise ValueError("The MESS sort has not finished.")
    first: dict[str, str] = {}
    for u in sort["unclear"]:
        if u.get("status", "OPEN") != "OPEN":
            continue
        k = f"{' '.join(u['quote'].lower().split())}|{' '.join(u['question'].lower().split())}"
        if k in first:
            u["status"], u["duplicateOf"] = "DUPLICATE", first[k]
        else:
            first[k] = u["id"]
    open_items = [u for u in sort["unclear"] if u.get("status", "OPEN") == "OPEN"]
    digest = _intake_digest(sort)
    still_open: list[dict] = []
    total = (len(open_items) + RESOLVE_BATCH_SIZE - 1) // RESOLVE_BATCH_SIZE
    for i in range(0, len(open_items), RESOLVE_BATCH_SIZE):
        batch = open_items[i:i + RESOLVE_BATCH_SIZE]
        resolved = sum(1 for u in sort["unclear"] if u.get("status") == "RESOLVED")
        progress(f"Checking flagged items against all sorted notes - batch {i // RESOLVE_BATCH_SIZE + 1}/{total} ({resolved} answered so far)",
                 round(5 + i / max(1, len(open_items)) * 90))
        results = {r["id"]: r for r in resolve_unclear_batch(digest, [{"id": u["id"], "quote": u["quote"], "question": u["question"],
                                                                        "source": u.get("source")} for u in batch], still_open, planning_model(state))}
        ids = {u["id"] for u in sort["unclear"]}
        for u in batch:
            r = results.get(u["id"]) or {}
            if r.get("status") == "RESOLVED" and (r.get("answer") or "").strip():
                u.update(status="RESOLVED", answer=r["answer"], evidence=r.get("evidence", ""))
            elif r.get("status") == "DUPLICATE" and r.get("duplicateOf") in ids and r["duplicateOf"] != u["id"]:
                u.update(status="DUPLICATE", duplicateOf=r["duplicateOf"])
            else:
                still_open.append({"id": u["id"], "question": u["question"]})
        storage.save_state(name, state)
    write_clarifications(name, state)
    storage.save_state(name, state)
    c = count_unclear(sort)
    progress(f"Checked {len(open_items)} items: {c['RESOLVED']} answered from your notes, {c['DUPLICATE']} duplicates, {c['OPEN']} still need you.", 100)
    return state


def count_unclear(sort: dict) -> dict:
    c = {"OPEN": 0, "RESOLVED": 0, "ANSWERED": 0, "DUPLICATE": 0}
    for u in sort.get("unclear") or []:
        c[u.get("status") or "OPEN"] += 1
    return c


def answer_unclear(name: str, state: dict, answers: dict[str, str]) -> dict:
    """Saves the creators' answers. An empty answer re-opens the item."""
    sort = state.get("messSortResult")
    if not sort:
        raise ValueError("No intake to answer.")
    for u in sort["unclear"]:
        if u["id"] not in answers:
            continue
        ans = (answers[u["id"]] or "").strip()
        if ans:
            u.update(status="ANSWERED", answer=ans, evidence="", duplicateOf="")
        elif u.get("status") == "ANSWERED":
            u.update(status="OPEN", answer="")
    write_clarifications(name, state)
    storage.save_state(name, state)
    return state
