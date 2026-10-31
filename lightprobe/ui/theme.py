"""Shared look: the same colours, panels and buttons as the original app (Tailwind classes)."""

from __future__ import annotations

from typing import Callable

from nicegui import ui

HEAD = """
<style>
  body { background: #0a0a0a; color: #e2e8f0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif; }
  .q-page, .nicegui-content { background: transparent; }
  .nicegui-content { padding: 0; }
  @keyframes blob {
    0% { transform: translate(0px, 0px) scale(1); }
    33% { transform: translate(30px, -50px) scale(1.1); }
    66% { transform: translate(-20px, 20px) scale(0.9); }
    100% { transform: translate(0px, 0px) scale(1); }
  }
  .lp-blob { position: fixed; width: 24rem; height: 24rem; border-radius: 9999px; filter: blur(100px); mix-blend-mode: screen;
             animation: blob 7s infinite; pointer-events: none; z-index: 0; }
  .lp-delay-2 { animation-delay: 2s; } .lp-delay-4 { animation-delay: 4s; }
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 9999px; }
  ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.3); }
  * { scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.15) transparent; }
  .lp-prose { white-space: pre-wrap; font-family: Georgia, 'Times New Roman', serif; line-height: 1.75; }
  .lp-mono { white-space: pre-wrap; font-family: ui-monospace, 'Cascadia Code', Consolas, monospace; }
  .q-field--dark .q-field__control { background: rgba(0,0,0,0.35); }
  .q-dialog__inner > .q-card { background: #0f1017; border: 1px solid rgba(255,255,255,0.1); }
  .q-expansion-item__content { background: transparent; }
</style>
"""

PANEL = "bg-white/5 backdrop-blur-xl border border-white/10 rounded-xl p-6 shadow-lg shadow-purple-500/5"
SUBPANEL = "bg-black/30 border border-white/10 rounded-lg p-3"
HERO = ("bg-gradient-to-r from-purple-950/40 via-slate-900/80 to-blue-950/40 border border-purple-500/30 rounded-2xl p-6 "
        "shadow-xl backdrop-blur-xl")

BUTTONS = {
    "primary": "bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 text-white font-bold rounded-xl shadow-lg shadow-purple-500/25",
    "approve": "bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold rounded-xl shadow-xl shadow-emerald-500/25",
    "secondary": "bg-white/5 hover:bg-white/10 text-slate-200 border border-white/10 rounded-xl font-semibold",
    "purple": "bg-purple-500/15 hover:bg-purple-500/25 text-purple-200 border border-purple-500/30 rounded-xl font-semibold",
    "amber": "bg-amber-600 hover:bg-amber-500 text-white rounded-lg font-bold",
    "danger": "bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/25 rounded-xl font-semibold",
    "ghost": "text-slate-400 hover:text-white rounded-lg",
}


def setup_page(title: str) -> None:
    ui.dark_mode(True)
    ui.add_head_html(HEAD)
    ui.page_title(title)
    ui.element("div").classes("lp-blob bg-purple-600/20").style("top:10%; left:-10%")
    ui.element("div").classes("lp-blob bg-blue-600/20 lp-delay-2").style("top:40%; right:-5%")
    ui.element("div").classes("lp-blob bg-pink-600/20 lp-delay-4").style("bottom:10%; left:20%")


def button(text: str, on_click: Callable | None = None, kind: str = "secondary", icon: str | None = None, size: str = "md") -> ui.button:
    pad = {"sm": "px-3 py-1 text-xs", "md": "px-4 py-2 text-sm", "lg": "px-7 py-3 text-sm"}[size]
    b = ui.button(text, on_click=on_click, icon=icon, color=None).props("no-caps unelevated")
    return b.classes(f"{BUTTONS[kind]} {pad} transition-all")


def badge(text: str, tone: str = "purple") -> ui.label:
    tones = {
        "purple": "bg-purple-500/20 text-purple-300 border-purple-500/30",
        "emerald": "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
        "amber": "bg-amber-500/20 text-amber-300 border-amber-500/30",
        "red": "bg-red-500/20 text-red-300 border-red-500/30",
        "slate": "bg-white/10 text-slate-300 border-white/15",
        "orange": "bg-orange-500/15 text-orange-300 border-orange-500/30",
        "teal": "bg-teal-500/15 text-teal-300 border-teal-500/30",
        "blue": "bg-blue-500/15 text-blue-300 border-blue-500/30",
    }
    return ui.label(text).classes(f"inline-flex items-center text-[11px] font-semibold px-2.5 py-0.5 rounded-full border {tones[tone]}")


def heading(text: str, sub: str | None = None, icon: str | None = None) -> None:
    with ui.row().classes("items-center gap-2"):
        if icon:
            ui.icon(icon).classes("text-purple-400 text-xl")
        ui.label(text).classes("text-2xl font-bold text-white")
    if sub:
        ui.label(sub).classes("text-slate-300 text-sm max-w-4xl leading-relaxed")


def step_tag(text: str) -> None:
    ui.label(text).classes("text-[11px] font-mono uppercase bg-emerald-500/20 text-emerald-300 px-2.5 py-0.5 rounded-full "
                           "border border-emerald-500/30 font-semibold tracking-wider w-fit")


def text_input(label: str, value: str = "", **kwargs) -> ui.input:
    return ui.input(label, value=value, **kwargs).props("dark outlined dense").classes("w-full")


def text_area(label: str, value: str = "", rows: int = 4) -> ui.textarea:
    return ui.textarea(label, value=value).props(f"dark outlined dense rows={rows}").classes("w-full")


def number_input(label: str, value=None, **kwargs) -> ui.number:
    return ui.number(label, value=value, **kwargs).props("dark outlined dense").classes("w-full")


def select(options, value=None, label: str = "", width: str = "w-full", **kwargs) -> ui.select:
    return ui.select(options, value=value, label=label, **kwargs).props("dark outlined dense options-dark").classes(width)


def long_text(text: str, mono: bool = False, max_h: str = "max-h-96") -> None:
    ui.label(text or "(empty)").classes(f"{'lp-mono text-[11px]' if mono else 'lp-prose text-sm'} text-slate-300 bg-black/40 border border-white/10 "
                                         f"rounded-lg p-4 {max_h} overflow-y-auto w-full")


def stat(label: str, value, icon: str | None = None) -> None:
    with ui.column().classes("gap-0"):
        if icon:
            ui.icon(icon).classes("text-slate-400 text-sm")
        ui.label(str(value)).classes("text-2xl font-bold text-white")
        ui.label(label).classes("text-[11px] uppercase tracking-wider text-slate-400")


def format_timer(seconds: int) -> str:
    m, s = divmod(max(0, seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
