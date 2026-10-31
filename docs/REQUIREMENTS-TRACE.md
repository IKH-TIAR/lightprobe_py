# Light Probe (Python) — Requirements Trace

Every feature of the Python rewrite, traced to where the client asked for it in the Fiverr conversation
(order #FO71C199A1D81, buyer ralphycolon__). Dates/times as shown by Fiverr. Quotes are verbatim from the
chat screenshots (`screencapture-fiverr-inbox-ralphycolon-2026-10-19-08_29_26.pdf`).

Attachments in the chat (the REQUIREMENTS file of Sep 08 9:12 AM, card/.md files, the associate's document)
were not readable from the screenshots; anything stated only there is not covered here.

Legend: **ASKED** = client requested it · **AGREED** = proposed by us and accepted by the client ·
**SUPPORT** = engineering needed to deliver an asked feature reliably (not separately requested).

---

## 1. Platform

| Feature | Basis | Evidence |
|---|---|---|
| Runs locally on the laptop, data in local folders | ASKED | Sep 08 7:40 AM "Need it to be local"; Sep 08 9:12 AM "Locally on my laptop, I already have a main folder" |
| Python | AGREED | Sep 09 11:52 AM proposal "a Python service"; Sep 09 12:10 PM client "seems Python might be better" |
| Anthropic Claude via API, Sonnet by default | ASKED / AGREED | Sep 09 7:43 PM "it would have to be sonnet 4.6"; Sep 14 API usage billed separately (no objection); Sep 20 client sent the API key; Oct 02 2:10 AM "I need strictly an app that connects to API and NOT opus"; Oct 03 12:50 PM "just what antrophic little for now" |
| App on the laptop, not a public web page | ASKED | Sep 17 6:50 AM "It's a app that is installed correct?"; Sep 17 10:30 AM "we don't want just anyone accessing the admin dashboard web-based"; Sep 18 10:10 AM "wouldn't it be better as an app?"; Oct 13 6:50 AM "This needs to be as a downloadable app" |
| Google Drive | ASKED (Sep 08) — **deferred** | Sep 08 7:40 AM / 9:12 AM. Out of scope for this version by decision of 2026-10-19 (local folders only) |
| Offline / no API / local model | First asked Oct 17 7:15 PM — Ollama support added for local testing | Anthropic remains the default provider; Settings can select local Ollama through `llm.py`, with `llama3.1:8b` as the initial local model |

## 2. Universe & folder structure

| Feature | Basis | Evidence |
|---|---|---|
| One folder per universe, each with its volume bins (folders) | ASKED | Sep 08 9:12 AM "organized by separate universes. Each universe has its own folder. Inside each universe folder, there are separate volume bins" |
| Each volume bin holds what the assistant needs for that volume: rules/reminders, no-drift, no-slop, skill cards, main events, detailed summaries, soul tracking | ASKED | Sep 08 9:12 AM (list under "Each volume bin contains the files the assistant needs") |
| Main folder of rules, reminders and skill cards used so it "does not create AI schlop, does not drift" | ASKED | Sep 08 9:12 AM |
| Consistent memory per volume; pauses so each bin has everything it needs | ASKED | Sep 08 7:40 AM "It has to have consistent memory, remind itself to pause that way when it works on the separate volume bins it has everything it needs" |
| Rush Mode (40–60, max 100 chapters) and Slow Burn, sharing one universe folder | ASKED | Sep 16 12:30 AM "40 - 60 chapters, sometimes only 100 chapters max" |

## 3. MESS sorting into volume bins

| Feature | Basis | Evidence |
|---|---|---|
| Drop files into MESS; every file sorted, one by one | ASKED | Sep 22 10:22 PM (files dropped into MESS, sorted one by one); Oct 17 "extracts the information from each of the documents and moves it, one by one, into the correct volume bin" |
| Watch and review the sorting | ASKED | Sep 08 "We want to be able to watch and review the sorting process" |
| Identify the main events first | ASKED | Sep 08 8:40 PM |
| Place every item in the volume where it belongs; move it along the way | ASKED | Sep 08 7:40 AM "organize what information since most the main events already placed right in the bins"; Oct 12 (15–20 chapters message) "extract the information from each file … place it in the correct volume bin and move it along the way" |
| Volume count: system decides when not set; when the creators set it, it is fixed (N volumes = N folders) | ASKED | Sep 08 8:40 PM "Maybe … 10 volumes. Maybe … 20 … The system should determine that"; Oct 08 9:50 PM "IT IS 20 MINIMUM"; Oct 17 "If we stated … 20 volumes, then it has 20 volumes. There are 20 folders" |
| Finished volumes stay finished (pin a file to its volume; never split) | ASKED | Oct 03 9:13 PM "volume 1 - 3 the previous version was done already … events … remain the same"; Oct 17 "If three volumes are already done, then three volumes are already done" |
| The author's own volume numbering is kept | AGREED | Oct 05 (our message) "YOUR VOLUME NUMBERING IS KEPT … Anything you labeled Volume 4 goes into Volume 4" |
| File names never force placement; dense material spreads over the volumes its events cover | ASKED | Oct 12 9:30 AM Volume 4 material "distributed through volume 4, 5, 6, 7, 8" |
| No count-balancing that splits existing volumes | ASKED | Oct 17 4:40 AM "MADE FAKE VOLUMES, YOU PUT SUPPOSED VOLUME 3 - 10 FAKE" |
| Creators can move items between bins | ASKED | Oct 17 "We confirm things along the way for the volumes" |
| Events-only files (use events, never copy the old style) | ASKED | Oct 06 8:30 AM "Remember to not copy the old style of Volume 1, 2, 3" |

## 4. Gap-fill: mini-events and questions to the creators

| Feature | Basis | Evidence |
|---|---|---|
| Find what is missing between the established main events, per volume | ASKED | Oct 17 "it is then able to determine what is missing" |
| Generate the mini-events that compound toward the main events (cause → effect), never new main events | ASKED | Sep 08 8:40 PM "determine the many events that logically lead toward those main events"; Sep 09 12:10 PM fill "any blanks … mini events / mini arcs … slice of life"; Oct 17 "determine the mini-events that logically compound and lead toward those established main events … follow cause and effect step by step" |
| Creators confirm / edit / reject; answer the assistant's questions | ASKED | Sep 08 8:40 PM questions file "I answer"; Oct 17 "communicate with the creators … We confirm things along the way" |

## 5. Author style

| Feature | Basis | Evidence |
|---|---|---|
| Retain the author style; author voice card | ASKED | Sep 08 7:40 AM "retain author style"; Author Skill Card |
| Author style engine that polishes and improves the unique style | ASKED | Sep 16 "polish and improve it's respective unique style"; "author style engine" |
| Style mode at the beginning to lock the style; less telling | ASKED | Sep 25 "too much telling … It needs to have a style mode at the very beginning, to lock in the style" |
| Generate its own unique voice; test candidate styles until correct, then lock | ASKED | Oct 03 "supposed to generate its own unique author voice style"; Oct 17 "create unique author styles that we test until we get the correct style, and then we implement that style" |

## 6. Planning, foreshadowing, writing, memory

| Feature | Basis | Evidence |
|---|---|---|
| Chapters per volume: min/max setting (currently 15–20) | ASKED | Oct 10 9:40 AM "20 - 40"; Oct 10 8:20 PM "20 - 30"; Oct 12 8:20 PM "about 15 - 20 chapters each" (setting, so each change is a value, not code) |
| Payoff & foreshadowing pass | AGREED | Sep 09 12:40/12:46 PM; Sep 12 milestone 2 "Payoff and foreshadowing pass" |
| Chapters written and reviewed in passes of 3 | AGREED | Sep 12 milestone 2 "writes chapters 3 at a time" |
| Volume-to-volume memory pass | AGREED | Sep 12 milestone 2 "Volume-to-volume memory pass" |
| Start at any volume (test Volume 4 first) | ASKED | Oct 03 9:13 PM "volume 4 to test it" |
| Each volume bin has everything when the creators work on it | ASKED | Oct 17 "Whenever we are working on a specific volume, we click into that specific volume bin, and it already has everything it needs" |

## 7. Supporting engineering (SUPPORT)

Not separately requested; each exists to deliver an asked feature without losing or inventing material.

| Feature | Supports |
|---|---|
| Verbatim extraction of draft passages with their source (`file p.N`) | "organize the information", no drift |
| Never sample/condense; split the work when output is cut off | every file sorted completely |
| Approval gate between stages; review every 3 chapters | "we confirm things along the way" |
| Contradiction check (UNCLEAR) answered from the notes or by the creators | questions file |
| Character identity check (merged/mixed characters) | soul tracking files |
| Chapter audit (drift/slop/voice) | no-drift / no-slop cards |
| Backups before any reset or repair | creators' control over their data |
