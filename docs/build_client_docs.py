"""Builds the two client PDFs into <repo>/client_proof (HTML -> PDF with Edge). Run: python docs/build_client_docs.py"""

import html
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parents[2] / "client_proof"   # output folder (repo root)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

CSS = """
body { font-family: 'Segoe UI', Arial, sans-serif; color: #1e1b2e; margin: 36px 42px; font-size: 11.5px; line-height: 1.5; }
h1 { font-size: 24px; margin: 0 0 4px; color: #3b1f7a; }
h2 { font-size: 15px; margin: 26px 0 8px; color: #3b1f7a; border-bottom: 2px solid #e4dcf7; padding-bottom: 4px; }
.sub { color: #555; margin-bottom: 18px; }
table { width: 100%; border-collapse: collapse; margin: 6px 0 10px; page-break-inside: auto; }
tr { page-break-inside: avoid; }
th { background: #3b1f7a; color: #fff; text-align: left; padding: 6px 8px; font-size: 11px; }
td { border-bottom: 1px solid #e6e2ef; padding: 6px 8px; vertical-align: top; }
td.q { color: #3d3a4f; font-style: italic; width: 34%; }
td.r { font-weight: 600; width: 22%; }
.note { background: #f5f2fc; border-left: 3px solid #7c4dff; padding: 8px 12px; margin: 10px 0; }
.ok { color: #0a7a52; font-weight: 600; }
.small { color: #666; font-size: 10px; }
"""


def page(title: str, subtitle: str, body: str) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>{CSS}</style></head><body>" \
           f"<h1>{html.escape(title)}</h1><div class='sub'>{subtitle}</div>{body}</body></html>"


def table(headers: list[str], rows: list[list[str]], classes: list[str]) -> str:
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td class='{c}'>{cell}</td>" for c, cell in zip(classes, r)) + "</tr>" for r in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def q(*quotes: str) -> str:
    return "<br>".join(quotes)


# ---------------------------------------------------------------------------------------------
# 1. Requirements and features
# ---------------------------------------------------------------------------------------------

REQ = [
    ("Platform", [
        ["Runs on the laptop", "Light Probe is a desktop application. It opens in its own window from one double-click (Light Probe.bat) and keeps every file in local folders on the laptop.",
         q("Sep 08, 7:40 AM - \u201cNeed it to be local\u201d", "Sep 08, 9:12 AM - \u201cLocally on my laptop, I already have a main folder\u201d")],
        ["An installed app, not a website anyone can reach", "No website, no hosting, no login page. It listens only on the laptop itself (127.0.0.1). The whole folder can be copied to another computer and started the same way.",
         q("Sep 17, 6:50 AM - \u201cIt's a app that is installed correct?\u201d", "Sep 17, 10:30 AM - \u201cwe don't want just anyone accessing the admin dashboard web-based\u201d", "Oct 13, 6:50 AM - \u201cThis needs to be as a downloadable app\u201d")],
        ["Python", "Written in Python. The full source code is included, with a README and one-click start.",
         q("Sep 09, 12:10 PM - \u201cseems Python might be better\u201d")],
        ["Anthropic Claude for the AI steps (not Opus by default)", "Claude Sonnet is the default model for planning and writing; Opus can be selected per universe. All AI calls go through one file, so another or a locally running model can be connected later.",
         q("Sep 09, 7:43 PM - \u201cit would have to be sonnet 4.6\u201d", "Oct 02, 2:10 AM - \u201cI need strictly an app that connects to API and NOT opus\u201d", "Oct 03, 12:50 PM - \u201cjust what antrophic little for now\u201d")],
    ]),
    ("Universe and volume bins", [
        ["One folder per universe, with its volume bins", "Each universe has its own folder; inside it, one folder per volume (Volume_01, Volume_02, ...).",
         q("Sep 08, 9:12 AM - \u201cEach universe has its own folder. Inside each universe folder, there are separate volume bins\u201d")],
        ["Each volume bin holds what the assistant needs", "Each volume folder holds its sorted material (BIN.md), confirmed mini-events, outline, source material, character (soul) index, continuity ledger, summaries and the memory passed from the previous volume. The rules, reminders, no-drift / no-slop cards and skill cards are read before every step.",
         q("Sep 08, 9:12 AM - rules and reminders, no AI drift, no AI schlop, skill cards, main events, detailed summaries, soul tracking files")],
        ["Consistent memory; pause per volume", "Every chapter is written from its volume's own memory bin. Each volume's memory is handed to the next (PASS-OUT / PASS-IN). Writing pauses for review every 3 chapters.",
         q("Sep 08, 7:40 AM - \u201cIt has to have consistent memory, remind itself to pause that way when it works on the separate volume bins it has everything it needs\u201d")],
        ["Number of volumes: system decides, or set by the creators", "Settings field. Empty = the system determines the number from the material. A number (e.g. 20) = exactly that many volumes and folders; never changed.",
         q("Sep 08, 8:40 PM - \u201cMaybe it requires 10 volumes. Maybe it requires 20 ... The system should determine that\u201d", "Oct 08, 9:50 PM - \u201cIT IS 20 MINIMUM\u201d")],
        ["Finished volumes stay finished", "A MESS file can be marked as a finished volume (e.g. V1 = Volume 1). Its material stays whole in that volume and is never split or moved.",
         q("Oct 03, 9:13 PM - volumes 1-3 \u201cwas done already\u201d, events remain the same, \u201cvolume 4 to test it\u201d")],
        ["The author's own volume numbering is kept", "A volume number written in the notes (\u201cVolume 2\u201d) keeps that item in that volume.",
         q("Oct 05 - confirmed in this chat: \u201cYOUR VOLUME NUMBERING IS KEPT\u201d")],
        ["Material placed where it belongs; file names do not force placement", "Every other item is placed by its events, in story order. A long file (e.g. \u201cSecond Half Of The Volume 4\u201d) spreads across the volumes its events cover. The creators can move any item to another volume.",
         q("Oct 12, 9:30 AM - Volume 4 material \u201cdistributed through volume 4, 5, 6, 7, 8\u201d")],
        ["Chapters per volume", "Settings field with a minimum and maximum (e.g. 15-20). Enforced on every volume.",
         q("Oct 12, 8:20 PM - \u201cabout 15 - 20 chapters each\u201d (earlier: 20-40 and 20-30 on Oct 10)")],
        ["Rush Mode and Slow Burn", "Both modes; a parallel track in the other mode can be created from the same sorted notes.",
         q("Sep 16, 12:30 AM - Rush \u201c40 - 60 chapters, sometimes only 100 chapters max\u201d")],
    ]),
    ("MESS sorting", [
        ["Files dropped into MESS, sorted one by one", "Every file is read page by page, one file at a time; nothing is skipped or summarised away. Draft scenes are copied word for word with their source. Accepts .txt, .md, .json, .docx, .pdf.",
         q("Sep 22, 10:22 PM - files dropped into MESS and sorted one by one", "Oct 17 - \u201cextracts the information from each of the documents and moves it, one by one, into the correct volume bin\u201d")],
        ["Watch and review the sorting", "Live progress while sorting; a review screen for characters, rules, events, drafts and questions.",
         q("Sep 08 - \u201cWe want to be able to watch and review the sorting process\u201d")],
        ["Main events identified first", "All arc beats (main events) form the arc map that the volumes are built on.",
         q("Sep 08, 8:40 PM - identify the main events first")],
        ["Do not copy the old style of Volumes 1-3", "A file can be marked \u201cevents only\u201d: its events are used, its writing style never.",
         q("Oct 06, 8:30 AM - \u201cRemember to not copy the old style of Volume 1, 2, 3\u201d")],
    ]),
    ("Gap-fill: mini-events and questions", [
        ["Generate the mini-events that lead to the main events", "For each volume the assistant fixes where the story stands and the author's main events, then generates the mini-events that compound toward them by cause and effect. It never invents a new main event or world rule.",
         q("Sep 08, 8:40 PM - \u201cdetermine the many events that logically lead toward those main events\u201d", "Sep 09, 12:10 PM - fill \u201cany blanks ... mini events / mini arcs ... slice of life\u201d", "Oct 17 - \u201cdetermine the mini-events that logically compound and lead toward those established main events\u201d")],
        ["Ask the creators; the creators confirm", "Anything that needs a decision becomes a question. The creators accept, edit, reject or add mini-events, answer the questions, and confirm each volume. Only confirmed mini-events are used.",
         q("Sep 08, 8:40 PM - questions file \u201cI answer\u201d", "Oct 17 - \u201ccommunicate with the creators ... We confirm things along the way\u201d")],
    ]),
    ("Author style", [
        ["Retain and improve the author's style", "The author's own voice is extracted from their prose; a polished version is offered alongside unique voices.",
         q("Sep 08, 7:40 AM - \u201cretain author style\u201d", "Sep 16 - \u201cpolish and improve it's respective unique style\u201d")],
        ["Style mode: test until right, then lock", "Style Lab: each candidate writes a test passage of the same scene; the creators refine with feedback until one is right and lock it for every chapter and volume.",
         q("Sep 25 - \u201cIt needs to have a style mode at the very beginning, to lock in the style\u201d", "Oct 17 - \u201ccreate unique author styles that we test until we get the correct style\u201d")],
    ]),
    ("Planning and writing", [
        ["Payoff and foreshadowing", "Setups and payoffs from the author's material (and new ones where needed), each planted in an existing chapter.",
         q("Sep 09, 12:40 PM - payoff / foreshadowing pass agreed")],
        ["Chapters written 3 at a time with review", "One chapter at a time from its volume bin, a separate quality check (voice, continuity, no slop), and a review pause every 3 chapters.",
         q("Sep 12 - \u201cwrites chapters 3 at a time\u201d")],
        ["Volume-to-volume memory", "Each finished volume's memory is passed to the next.",
         q("Sep 12 - \u201cVolume-to-volume memory pass\u201d")],
        ["Test Volume 4 first", "Writing can start at any volume; the earlier volumes' planned events are used as the story so far.",
         q("Oct 03, 9:13 PM - \u201cvolume 4 to test it\u201d")],
    ]),
]


def build_requirements() -> str:
    body = ("<div class='note'>Every feature of the Light Probe system, next to the message in our Fiverr conversation where it was "
            "requested or agreed. Dates and times are as shown by Fiverr.</div>")
    for title, rows in REQ:
        body += f"<h2>{title}</h2>" + table(["Requirement", "How Light Probe does it", "Requested / agreed in this chat"], rows, ["r", "", "q"])
    body += ("<h2>About offline use and AI tokens</h2><p>The steps that understand notes and write (sorting meaning out of notes, generating "
             "mini-events, creating author styles, writing chapters) need an AI model. They use Anthropic's Claude, as agreed above, on your own "
             "Anthropic account. Everything else - viewing, reviewing, editing, moving items between volumes, answering questions and "
             "exporting - works without internet. Because every AI call goes through one file, a model running locally on the laptop can be "
             "connected later; how practical that is depends on the laptop's hardware.</p>"
             "<p>Storage is local folders on the laptop.</p>")
    return page("Light Probe - Requirements and Features", "Light Probe novel engine &middot; feature list with references", body)


# ---------------------------------------------------------------------------------------------
# 2. External services and dependencies
# ---------------------------------------------------------------------------------------------

def build_services() -> str:
    deps = [
        ["Anthropic Claude API (<i>anthropic</i> Python package, MIT licence)", "The AI steps: sorting notes, Universe Bible, author styles, volume placement, gap-fill, outlines, payoff plan, chapter writing, quality checks, volume memory", "<b>Yes</b> - only while those steps run. Paid per use on your own Anthropic account."],
        ["NiceGUI (MIT licence)", "The interface", "No"],
        ["pywebview (BSD licence) + Microsoft Edge WebView2 (built into Windows 10/11)", "Shows the interface in its own desktop window", "No"],
        ["python-docx (MIT licence)", "Reading .docx files into MESS; exporting the manuscript as .docx", "No"],
        ["pypdf (BSD licence)", "Reading .pdf files into MESS", "No"],
        ["Python 3.12-3.14 (PSF licence)", "Runs the application", "Only to install it the first time"],
    ]
    offline = [
        ["Open universes, review every stage, read chapters and memory files", "<span class='ok'>Offline</span>"],
        ["Edit volume text, move items between volumes, edit cards", "<span class='ok'>Offline</span>"],
        ["Accept / edit / reject / add mini-events, answer questions, confirm volumes", "<span class='ok'>Offline</span>"],
        ["Change settings (volumes, chapters per volume, finished volumes, events-only, style)", "<span class='ok'>Offline</span>"],
        ["Export the manuscript (.docx)", "<span class='ok'>Offline</span>"],
        ["Sort MESS, build the Bible, Style Lab, place volumes, gap-fill, outline, payoff plan, write chapters, volume handoff", "Internet (Anthropic API)"],
    ]
    body = ("<div class='note'>Light Probe uses <b>one</b> external service: the Anthropic Claude API, for the steps that need an AI model. "
            "There are no developer servers, no accounts with us, no subscriptions, and no hosting. The application listens only on the laptop "
            "itself (127.0.0.1) and cannot be reached from other computers.</div>")
    body += "<h2>Every external service and package</h2>" + table(["Component", "Used for", "Needs internet / payment"], deps, ["r", "", ""])
    body += "<h2>What works offline</h2>" + table(["Function", ""], offline, ["", "r"])
    body += ("<h2>Where your data is</h2><table>"
             "<tr><td class='r'>Universes</td><td>The <i>universes</i> folder next to the application: MESS files, sorted material, cards, volume folders, chapters, memory files, backups and exports. Plain text and JSON files you can open directly.</td></tr>"
             "<tr><td class='r'>API key</td><td><i>settings.json</i> next to the application, on the laptop only (or the ANTHROPIC_API_KEY environment variable).</td></tr>"
             "<tr><td class='r'>What is sent to Anthropic</td><td>Only the text a step needs (for example the notes being sorted, or a chapter's context bin when writing it), sent directly from the laptop to Anthropic over an encrypted connection. Nothing is sent anywhere else.</td></tr>"
             "<tr><td class='r'>Backups</td><td>Before any reset or repair, the affected files are copied to <i>_backups</i> inside the universe. Nothing is deleted.</td></tr></table>")
    body += ("<h2>Cost visibility</h2><p>Each universe shows the number of AI calls and the estimated cost of its API use (header of the "
             "universe screen; stored in <i>usage.json</i>). Example: a small demonstration universe (3 note files, 4 volumes, every stage plus "
             "one written chapter) used 30 calls, about $1.74. Cost grows with the amount of material and the number of chapters written.</p>")
    body += ("<h2>Running it without the developers</h2><table>"
             "<tr><td class='r'>Start</td><td>Double-click <i>Light Probe.bat</i>. The first time, it sets up Python and the packages (a few minutes, internet needed once); after that it opens straight away. Starting it again restarts it.</td></tr>"
             "<tr><td class='r'>Source code</td><td>Full Python source, with README, documentation and automated tests.</td></tr>"
             "<tr><td class='r'>Moving to another computer</td><td>Copy the folder (with <i>universes</i>) and double-click <i>Light Probe.bat</i>.</td></tr>"
             "<tr><td class='r'>Changing the AI model</td><td>Per universe in Settings (Claude Sonnet or Opus). All AI calls are in one file, <i>lightprobe/llm.py</i>.</td></tr></table>")
    return page("Light Probe - External Services and Dependencies", "Light Probe novel engine &middot; what it uses, what needs internet, where data is kept", body)


def write_pdf(name: str, content: str) -> None:
    htm = HERE / f"{name}.html"
    htm.write_text(content, encoding="utf-8")
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={HERE / (name + '.pdf')}", htm.as_uri()],
                   capture_output=True)
    htm.unlink()
    print(name, (HERE / f"{name}.pdf").stat().st_size, "bytes")


if __name__ == "__main__":
    write_pdf("Light Probe - Requirements and Features", build_requirements())
    write_pdf("Light Probe - External Services and Dependencies", build_services())
