"""LIVE smoke test against the real Anthropic API (costs a little). Runs the whole flow on a temporary
universe built from small synthetic notes - never on real universes:

    python tests/live_smoke.py

Uses the API key from Settings (settings.json) or ANTHROPIC_API_KEY. Prints what each stage produced and
writes a report to the temporary folder."""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="lightprobe-live-"))
os.environ["LIGHTPROBE_DATA"] = str(tmp / "universes")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lightprobe import actions, jobs, llm, storage  # noqa: E402

NAME = "Live_Smoke"

BOOK_ONE = """One

The envelope was on the third stair again, black as wet slate, sealed with a red wax heart. Mio Tanaka stopped with one shoe on and one in her hand. Seven in the morning. The rice cooker clicked downstairs. Her mother was humming the same two bars of a song she never finished.

The date on the envelope was today's. It always was.

Mio slid it into her school bag between the maths workbook and the bento box, and when her mother called up the stairs to ask what she was doing, she said, "Nothing. Looking for my other sock." The lie came out smooth. That worried her more than the envelope.

Inside, in handwriting that leaned left like someone writing against wind, the letter said: Do not cross at the Hayashi crossing at 4:12. Take the bridge.

Two

At 4:10 she stood at the Hayashi crossing anyway, because the letter had been wrong before. Once. A boy in a grey hoodie stood on the opposite kerb, earbuds in, phone in hand. Ren Kisaragi, from class 2-B, who never spoke to anyone and always ate lunch on the roof.

At 4:12 a delivery truck took the corner too fast, skidded on the wet paint of the zebra stripes, and mounted the kerb exactly where Mio would have been standing if she had stepped forward with the crowd.

She had not stepped forward. Ren had. Mio grabbed his sleeve and pulled, and they both went down on the pavement, and the truck's mirror cracked against the signal pole above their heads.

Ren looked at her hand on his sleeve, then at her face. "You knew," he said. It was not a question.

That night there were two envelopes on the stairs. One had her name. The other had his.
"""

NOTES = """CHARACTERS
Mio Tanaka - 16, second-year at Hanagawa High. Receives dated black letters that predict accidents. Lies easily to her mother and hates that she does. Wants to know who writes the letters.
Ren Kisaragi - 16, class 2-B, silent, eats alone on the roof. His older brother died at a crossing two years ago. After Volume 1 he receives letters too.
Mio's mother - widow, runs a small laundry. Hides a shoebox of the same black envelopes from twenty years ago.

WORLD
The Letters: each letter arrives dated for the day it is found. It names a time and a place. Ignoring it means someone gets hurt. A letter never names who will be hurt.
The Delivery Office: an old post office building behind the river shrine, closed since 1998, where the letters are written.

ARC
[Volume 2] Mio and Ren start following the letters together; they save a cyclist and a child at the river.
[Volume 2] Ren finds a letter addressed to his dead brother, dated the day he died.
Mio finds her mother's shoebox and realises the letters came to her mother twenty years ago.
The winter tournament: Ren's basketball team; a letter warns of the gym roof.
The final letter: addressed to Mio's mother, dated the day Mio was born.
CONFLICT: In one note Ren's brother died at a crossing; in another he died in a river.
"""

BRAINDUMP = """Later arcs, rough: after the shoebox, Mio confronts her mother. Her mother wrote the letters as a girl? No - she RECEIVED them. Someone at the Delivery Office has written letters to the women of Mio's family for three generations.
The ending: Mio and Ren go into the Delivery Office. The writer is an old postmaster who sees the timeline as a ledger. Mio writes the last letter herself, to her younger self.
"""


def wait(label: str) -> None:
    while jobs.running(NAME):
        job = jobs.current(NAME)
        print(f"   ... {job.percentage:3d}%  {job.message[:140]}", flush=True)
        time.sleep(4)
    job = jobs.current(NAME)
    if job and job.status != "done":
        raise SystemExit(f"\n!!! {label} FAILED: {job.error or job.message}")
    jobs.clear(NAME)


def run(action: str, payload: dict | None = None) -> dict:
    t0 = time.time()
    print(f"\n>>> {action}", flush=True)
    out = actions.dispatch(NAME, action, payload)
    if isinstance(out, jobs.Job):
        wait(action)
    st = storage.load_state(NAME)
    u = llm.read_usage(NAME)
    print(f"    done in {time.time() - t0:.0f}s | status {st['status']} | total so far: {u.get('calls', 0)} calls, est. ${u.get('estimatedUSD', 0):.3f}", flush=True)
    return st


def main() -> None:
    storage.create_universe(NAME, "SLOW_BURN_MODE")
    storage.add_mess_file(NAME, "Book One.txt", BOOK_ONE.encode())
    storage.add_mess_file(NAME, "Notes.txt", NOTES.encode())
    storage.add_mess_file(NAME, "Braindump.txt", BRAINDUMP.encode())
    run("UPDATE_SETTINGS", {"targetVolumes": 4, "chapterRange": {"min": 3, "max": 4}, "volumePins": {"Book One.txt": 1}})
    report: dict = {}

    st = run("INGEST")
    s = st["messSortResult"]
    report["sort"] = {"souls": [x["name"] for x in s["souls"]], "beats": [f"{b['id']} [{b.get('phase')}] {b['event']}" for b in s["arcBeats"]],
                      "drafts": [f"{m['id']} {m.get('anchor')} {m['content'][:80]}" for m in s["chapterMaterial"]],
                      "unclear": [f"{u['status']}: {u['question']}" for u in s["unclear"]]}
    print(json.dumps(report["sort"], indent=1, ensure_ascii=False))

    run("APPROVE_INGESTION")
    st = run("GENERATE_BIBLE")
    report["roster"] = [x["name"] for x in st["soulRoster"]["souls"]]
    print("roster:", report["roster"])
    run("APPROVE_BIBLE")
    st = run("STYLE_GENERATE")
    cands = st["styleLab"]["candidates"]
    report["styles"] = [{"name": c["name"], "origin": c["origin"], "pitch": c.get("pitch"), "sample_start": c["sample"][:300]} for c in cands]
    for c in report["styles"]:
        print(f" - {c['name']} ({c['origin']}): {c['pitch']}\n   {c['sample_start']!r}")
    run("STYLE_LOCK", {"id": cands[0]["id"]})

    st = run("BUILD_BINS")
    report["bins"] = [{"volume": v["volumeNumber"], "title": v["title"], "items": v["itemIds"], "pinned": v.get("pinnedFrom")} for v in st["bins"]["volumes"]]
    report["fixed"] = st["bins"]["fixed"]
    for v in report["bins"]:
        print(f" V{v['volume']} {v['title']}: {v['items']} {v['pinned'] or ''}")
    book_items = [i for i, why in st["bins"]["fixed"].items() if "Book One" in why]
    v1 = st["bins"]["volumes"][0]["itemIds"]
    print("CHECK pinned Book One items all in Volume 1:", all(i in v1 for i in book_items), book_items)
    run("APPROVE_BINS")

    st = run("GAP_RUN")
    for n, gv in sorted(st["gapFill"]["volumes"].items()):
        print(f" V{n} {gv['status']}: {len(gv['miniEvents'])} mini-events, {len(gv['questions'])} questions")
        for e in gv["miniEvents"][:4]:
            print(f"    {e['id']} [{e['kind']}] {e['title']}: {e['event'][:110]} -> {e['leadsTo']}")
        for q in gv["questions"][:2]:
            print(f"    ? {q['question'][:140]}")
    report["gapFill"] = st["gapFill"]
    for n, gv in st["gapFill"]["volumes"].items():
        if gv["status"] == "PROPOSED":
            run("GAP_CONFIRM", {"volume": int(n), "acceptRemaining": True})
    run("APPROVE_GAPS")

    st = run("OUTLINE_RUN")
    for v in st["plan"]["volumes"]:
        print(f" V{v['volumeNumber']} {v['title']} ({len(v['chapters'])} ch): " + " | ".join(c["title"] for c in v["chapters"]))
    report["outline"] = [{"v": v["volumeNumber"], "chapters": [(c["title"], c["sourceRefs"]) for c in v["chapters"]]} for v in st["plan"]["volumes"]]
    run("APPROVE_PLAN")
    st = run("PAYOFF_RUN")
    report["payoff"] = st["payoffPlan"]
    print(f" {len(st['payoffPlan']['payoffs'])} threads, dropped {st['payoffPlan'].get('dropped')}")
    run("APPROVE_PAYOFF")

    run("SET_START_VOLUME", {"volume": 2})
    st = run("WRITE_CHAPTER")
    d = st["draft"]
    report["chapter"] = {"title": d["title"], "words": len(d["content"].split()), "audit": d["auditStatus"], "ledger": d["ledgerEntry"]}
    print(f" {d['title']} - {len(d['content'].split())} words - audit {d['auditStatus']['overall']}")
    print(d["content"][:1200])
    st = run("SAVE_DRAFT")
    report["usage"] = llm.read_usage(NAME)
    (tmp / "live_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nLIVE SMOKE OK. Report: {tmp / 'live_report.json'}\nUniverse: {storage.universe_dir(NAME)}")
    print("usage:", report["usage"])


if __name__ == "__main__":
    main()
