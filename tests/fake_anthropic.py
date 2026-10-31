"""A fake Anthropic Messages API (streaming SSE) for offline tests. It recognises each prompt of the
pipeline by its system prompt and returns a small, valid answer, so the whole flow can be tested
without network access or API credits. Every request is recorded in `FakeAnthropic.requests`."""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _dna(name: str = "") -> dict:
    keys = ["sentenceRhythm", "diction", "paragraphShape", "dialogueAttribution", "interiorityDepth", "sensoryPriority",
            "timeHandling", "chapterOpeningClosing", "signatureMoves", "neverDoes", "overallVoiceSummary"]
    return {k: f"{name} {k} description" for k in keys}


class FakeAnthropic:
    def __init__(self):
        self.requests: list[dict] = []
        self.payoff_calls = 0
        self.truncate_next_sort = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def start(self) -> "FakeAnthropic":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.server.shutdown()

    def calls(self, marker: str) -> list[dict]:
        return [r for r in self.requests if marker in r["system"]]

    # ------------------------------------------------------------------ responses
    def respond(self, system: str, prompt: str):
        if "MESS Sorter (Card 08)" in system:
            return self.sort_page(prompt)
        if "clarification checker" in system:
            ids = re.findall(r"^\[(U-\d+)\]", prompt, re.M)
            return {"results": [{"id": i, "status": "RESOLVED", "answer": "Answered in the notes.", "evidence": "B-1", "duplicateOf": ""} for i in ids]}
        if "identity resolver" in system:
            names = re.findall(r'^- "([^"]+)"', prompt, re.M)
            return {"groups": [{"canonical": n, "members": [n], "kind": "PERSON"} for n in names], "wrongAliases": [], "mixedEntries": []}
        if "identity repairer" in system:
            return {"aliases": [], "moved": []}
        if "Story Bible Architect" in system:
            return {"corePremise": "A courier network delivers letters that change fate.", "civilizationalModel": "The Nest and the Nexus.",
                    "worldRules": [{"ruleName": "Letters", "description": "Letters arrive dated.", "constraint": "Only one per day."}], "themes": ["Fate"]}
        if "Soul Codex Architect" in system:
            names = re.findall(r"^## (.+?)(?: \(aliases:.*)?$", prompt, re.M)
            return {"souls": [{"name": n, "aliases": [], "essence": f"{n} essence", "woundsAndDesires": "w", "relationships": "r",
                               "speechHabits": "s", "continuityTripwire": "t"} for n in names]}
        if "Voice DNA Extractor" in system:
            return _dna("author")
        if "Author Style Engine" in system and "Revise this style candidate" in prompt:
            return {"name": "Revised Voice", "pitch": "revised", **_dna("revised")}
        if "Author Style Engine" in system:
            m = re.search(r"Design (\d+)", prompt)
            n = int(m.group(1)) if m else 2
            return {"candidates": [{"name": f"Voice {i + 1}", "pitch": f"pitch {i + 1}", **_dna(f"v{i + 1}")} for i in range(n)]}
        if "STYLE TEST passage" in system:
            return "The envelope was warm from the stairs. " * 20
        if "Universe Architect" in system:
            return self.roadmap(prompt)
        if "volume router" in system:
            ids = re.findall(r"^\[((?:M|B)-\d+)\]", prompt.split("=== ITEMS ===")[1], re.M)
            return {"assignments": [{"id": i, "volume": 3, "assumed": True} for i in ids]}
        if "Gap-Fill engine" in system:
            vol = int(re.search(r"GAP-FILL - VOLUME (\d+)", prompt).group(1))
            return {"volumeStart": f"Start of volume {vol}", "mainEvents": [{"ref": "B-1", "event": "main"}],
                    "miniEvents": [{"title": f"Mini {vol}.{k}", "event": f"Something happens {k}", "cause": "c", "effect": "e", "leadsTo": "B-1",
                                    "after": "START", "souls": ["Kaho"], "kind": "KNOWLEDGE", "needsDecision": k == 2, "decisionNote": "decide" if k == 2 else ""}
                                   for k in (1, 2)],
                    "questions": [{"question": f"What does Kaho want in volume {vol}?", "why": "needed", "about": "B-1"}]}
        if "Arc Breakdown planner" in system:
            vols = re.findall(r"=== VOLUME (\d+):", prompt)
            return {"volumes": [{"volumeNumber": int(v), "chapters": 3, "reason": "material"} for v in vols]}
        if "Chapter Architect" in system:
            m = re.search(r"outline EXACTLY (\d+) chapters: (\d+) through (\d+)", prompt)
            count, start = int(m.group(1)), int(m.group(2))
            refs = re.findall(r"^\[((?:M|B)-\d+|E\d+-\d+)\]", prompt, re.M)
            return {"chapters": [{"chapterNumber": start + i, "title": f"Chapter title {start + i}", "synopsis": "Things happen.",
                                  "pacingType": "TIGHT_PIVOT", "momentGenre": "S01", "focalSoul": "Kaho", "timeCoordinate": "Morning",
                                  "sourceRefs": refs[:2] + ["Z-999"]} for i in range(count)]}
        if "Multi-Quadrant Payoff" in system:
            self.payoff_calls += 1
            good = {"id": "t1", "threadName": "Shoebox", "origin": "AUTHOR", "setupVolume": 2, "setupChapterNumber": 1, "setupDescription": "A shoebox.",
                    "payoffVolume": 3, "payoffChapterNumber": 2, "payoffDescription": "It opens.", "narrativeImpact": "big"}
            bad = {**good, "id": "t2", "threadName": "Ghost", "setupChapterNumber": 99}
            return {"overallStrategy": "strategy", "payoffs": [good, bad] if self.payoff_calls == 1 else [good]}
        if "Soul Codex (LNF-02)" in system:
            return "## Kaho - Status: MAIN\n- **Most Recent Present**: at home"
        if "Continuity Archivist" in system:
            return "<<<PASS_OUT>>>\n# PASS-OUT\nState.\n<<<VOLUME_SUMMARY>>>\nThe volume ended.\n<<<END>>>"
        if "Chapter Writer (LNF-03v2)" in system:
            n = re.search(r"Chapter (\d+)\n", prompt).group(1)
            return (f"<<<TITLE>>>\nChapter {n}: Written\n<<<CHAPTER_TEXT>>>\nProse of chapter {n}. " + "Words. " * 50 +
                    f"\n<<<BACKGROUND_OVERFLOW>>>\nLore {n}\n<<<LEDGER_ENTRY>>>\nLedger for chapter {n}.\n<<<SOUL_UPDATES>>>\nKaho - changed in {n}\n<<<END>>>")
        if "Finalization checker" in system:
            return {"voice": "PASS", "continuity": "PASS", "noSlop": "PASS", "ledger": "PASS", "overall": "APPROVED", "notes": "fine"}
        if "Subtlety Auditor" in system:
            return {"seeds": [{"threadName": "Shoebox", "found": True, "location": "p1", "subtletyScore": 8, "firstTimeReaderNotice": "no", "revision": ""}]}
        if "elite prose stylist" in system:
            return "<<<CHAPTER_TEXT>>>\nElevated prose.\n<<<ELEVATION_NOTES>>>\n- tighter\n<<<END>>>"
        raise AssertionError(f"Unexpected prompt: {system[:80]}")

    def sort_page(self, prompt: str) -> dict | str:
        if self.truncate_next_sort:
            self.truncate_next_sort = False
            return "TRUNCATE"
        page = prompt.split("=== RAW CONTENT TO CLASSIFY ===")[1].split("CLASSIFICATION RULES:")[0]
        souls, beats, drafts, unclear = [], [], [], []
        for line in page.splitlines():
            if line.startswith("SOUL:"):
                souls.append({"name": line[5:].strip(), "aliases": [], "essence": "e", "woundsAndDesires": "w", "relationships": "r", "speechHabits": ""})
            elif line.startswith("BEAT:"):
                m = re.match(r"BEAT:\s*(?:\[(.*?)\])?\s*(.*)", line)
                beats.append({"phase": m.group(1) or "", "event": m.group(2), "irreversibleChange": "changed"})
            elif line.startswith("DRAFT:"):
                words = line[6:].split()
                drafts.append({"volumeHint": "", "summary": "a draft", "startsWith": " ".join(words[:8]), "endsWith": " ".join(words[-8:])})
            elif line.startswith("CONFLICT:"):
                unclear.append({"quote": line, "question": "Which is right?"})
        return {"souls": souls, "worldRules": [{"ruleName": "Letters", "description": "Dated letters.", "constraint": "One a day."}],
                "arcBeats": beats, "chapterMaterial": drafts, "voiceSamples": [], "themes": ["Fate"], "unclear": unclear, "logistics": []}

    def roadmap(self, prompt: str) -> dict:
        m = re.search(r"EXACTLY (\d+) volumes", prompt)
        n = int(m.group(1)) if m else 3
        beats = re.findall(r"^\[(B-\d+)\].*?(FIXED -> Volume (\d+))?$", prompt, re.M)
        vols = [{"volumeNumber": v, "title": f"Volume title {v}", "premise": f"Premise {v}", "summary": f"Summary {v}",
                 "targetChapterCount": 3, "beatIds": []} for v in range(1, n + 1)]
        free = [v for v in range(2, n + 1)]
        for k, (bid, _, fixed) in enumerate(beats):
            # Deliberately put a FIXED beat in the wrong volume: the code must override it
            target = 2 if fixed else free[k % len(free)]
            vols[target - 1]["beatIds"].append(bid)
        return {"universeSummary": "The universe.", "volumes": vols}

    # ------------------------------------------------------------------ HTTP
    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                system = "\n".join(b["text"] for b in body.get("system") or [])
                prompt = "\n".join(m["content"] if isinstance(m["content"], str) else "".join(c.get("text", "") for c in m["content"])
                                   for m in body["messages"] if m["role"] == "user")
                fake.requests.append({"system": system, "prompt": prompt, "body": body})
                try:
                    out = fake.respond(system, prompt)
                except AssertionError as err:
                    self.send_response(400)
                    self.send_header("content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"type": "error", "error": {"type": "invalid_request_error", "message": str(err)}}).encode())
                    return
                truncated = out == "TRUNCATE"
                text = '{"souls": [' if truncated else (out if isinstance(out, str) else json.dumps(out))
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.end_headers()

                def ev(kind: str, data: dict) -> None:
                    self.wfile.write(f"event: {kind}\ndata: {json.dumps(data)}\n\n".encode())

                ev("message_start", {"type": "message_start", "message": {"id": "msg_1", "type": "message", "role": "assistant", "model": body["model"],
                                                                         "content": [], "stop_reason": None, "stop_sequence": None,
                                                                         "usage": {"input_tokens": 100, "output_tokens": 1}}})
                ev("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})
                ev("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}})
                ev("content_block_stop", {"type": "content_block_stop", "index": 0})
                ev("message_delta", {"type": "message_delta", "delta": {"stop_reason": "max_tokens" if truncated else "end_turn", "stop_sequence": None},
                                     "usage": {"output_tokens": 50}})
                ev("message_stop", {"type": "message_stop"})

        return Handler
