from __future__ import annotations

import asyncio
import subprocess

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Label, OptionList, Select, Static
from textual.widgets.option_list import Option

from . import actions
from .config import Config
from .model import GLYPH, Agent, fmt_wait, sort_agents

STATE_STYLE = {
    "permission": "bold red",
    "question": "bold yellow",
    "done": "green",
    "error": "red",
    "working": "dim",
    "starting": "dim",
}
ROLE_STYLE = {"you": "bold cyan", "claude": "bold magenta"}
PANE_STATES = {"permission", "starting", "unknown"}


class NewAgent(ModalScreen[dict | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, hosts: list[str], default_dir: str) -> None:
        super().__init__()
        self.hosts = hosts
        self.default_dir = default_dir

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label("New agent", classes="title")
            yield Select([(h, h) for h in self.hosts], value=self.hosts[0], allow_blank=False, id="host")
            yield Input(placeholder="name (letters, digits, - _)", id="name")
            yield Input(value=self.default_dir, placeholder="directory", id="dir")
            yield Input(placeholder="first prompt (optional)", id="prompt")
            yield Label("enter = start · esc = cancel", id="hint")

    def on_mount(self) -> None:
        self.query_one("#name", Input).focus()

    @on(Input.Submitted)
    def submit(self) -> None:
        name = self.query_one("#name", Input).value.strip()
        if not actions.NAME_RE.match(name):
            self.query_one("#hint", Label).update("name may only contain letters, digits, - and _")
            self.query_one("#name", Input).focus()
            return
        self.dismiss({
            "host": self.query_one("#host", Select).value,
            "name": name,
            "directory": self.query_one("#dir", Input).value,
            "prompt": self.query_one("#prompt", Input).value,
        })

    def action_cancel(self) -> None:
        self.dismiss(None)


class Confirm(ModalScreen[bool]):
    BINDINGS = [Binding("y", "answer(True)", "Yes"), Binding("n,escape", "answer(False)", "No")]

    def __init__(self, question: str) -> None:
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self.question, classes="title")
            yield Label("y = yes · n = no")

    def action_answer(self, value: bool) -> None:
        self.dismiss(value)


class CcmApp(App):
    TITLE = "ccm"
    CSS = """
    #main { height: 1fr; }
    #agents { width: 44; border: round $primary; }
    #preview-box { width: 1fr; border: round $primary; padding: 0 1; }
    #reply { margin: 0 1; }
    ModalScreen { align: center middle; }
    .dialog { width: 64; height: auto; border: round $accent; background: $surface; padding: 1 2; }
    .dialog .title { text-style: bold; margin-bottom: 1; }
    .dialog Input, .dialog Select { margin-bottom: 1; }
    """
    BINDINGS = [
        Binding("i,enter", "reply", "Reply"),
        Binding("a", "attach", "Attach"),
        Binding("n", "new", "New"),
        Binding("x", "kill", "Kill"),
        Binding("t", "toggle_view", "Chat/screen"),
        Binding("r", "refresh", "Refresh"),
        Binding("j", "move(1)", show=False),
        Binding("k", "move(-1)", show=False),
        Binding("1", "key('1')", show=False),
        Binding("2", "key('2')", show=False),
        Binding("3", "key('3')", show=False),
        Binding("escape", "escape", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.by_host: dict[str, list[Agent]] = {}
        self.host_errors: dict[str, str] = {}
        self.rows: dict[str, Agent] = {}
        self.selected_key: str | None = None
        self.view_override: str | None = None
        self.shown = ""
        self.wake = asyncio.Event()

    def compose(self) -> ComposeResult:
        with Horizontal(id="main"):
            yield OptionList(id="agents")
            with VerticalScroll(id="preview-box"):
                yield Static(id="preview")
        yield Input(placeholder="reply to the selected agent — enter sends, esc leaves", id="reply")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#agents", OptionList).focus()
        self.show_preview()
        for host in self.config.hosts:
            self.run_worker(self.poll_host(host), group="poll")

    # --- polling ---------------------------------------------------------

    async def poll_host(self, host: str) -> None:
        while True:
            try:
                self.by_host[host] = await actions.probe(host, self.config.history)
                self.host_errors.pop(host, None)
            except actions.ProbeError as e:
                self.by_host[host] = []
                self.host_errors[host] = str(e)
            self.rebuild()
            try:
                await asyncio.wait_for(self.wake.wait(), self.config.poll_seconds)
            except asyncio.TimeoutError:
                pass

    def refresh_now(self) -> None:
        self.wake.set()
        self.wake.clear()

    # --- rendering -------------------------------------------------------

    def rebuild(self) -> None:
        agents = sort_agents([a for h in self.config.hosts for a in self.by_host.get(h, [])])
        self.rows = {a.key: a for a in agents}
        options = [Option(self.row_text(a), id=a.key) for a in agents]
        for host, err in self.host_errors.items():
            options.append(Option(Text(f"✗ {host}: {err}", style="dim red", no_wrap=True,
                                       overflow="ellipsis"), disabled=True))
        ol = self.query_one("#agents", OptionList)
        if self.selected_key not in self.rows:
            self.selected_key = agents[0].key if agents else None
        ol.clear_options()
        ol.add_options(options)
        if self.selected_key:
            ol.highlighted = list(self.rows).index(self.selected_key)
        self.show_preview()

    @staticmethod
    def row_text(a: Agent) -> Text:
        style = STATE_STYLE.get(a.state, "")
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append(f"{GLYPH.get(a.state, ' ')} ", style)
        text.append(f"{a.name[:20]:<20} ", style if a.state != "working" else "")
        text.append(f"{a.host[:10]:<10} ", "dim")
        text.append(f"{fmt_wait(a.wait):>5}", "dim")
        return text

    def current(self) -> Agent | None:
        return self.rows.get(self.selected_key or "")

    def view_mode(self, a: Agent) -> str:
        return self.view_override or ("screen" if a.state in PANE_STATES else "chat")

    def show_preview(self) -> None:
        box = self.query_one("#preview-box", VerticalScroll)
        a = self.current()
        if a is None:
            box.border_title = "no agents"
            body = Text("No agents on " + ", ".join(self.config.hosts) + ". Press n to start one.", style="dim")
        else:
            mode = self.view_mode(a)
            box.border_title = f"{a.name}@{a.host} · {a.state} {fmt_wait(a.wait)} · {mode}"
            box.border_subtitle = a.cwd
            if mode == "screen":
                body = Text(a.pane or "(empty screen)")
            else:
                body = Text()
                for m in a.messages:
                    if m["role"] == "tool":
                        body.append(f"  ⚙ {m['text']}\n", "dim")
                    else:
                        body.append(f"\n{m['role']} › ", ROLE_STYLE.get(m["role"], ""))
                        body.append(m["text"] + "\n")
                if not a.messages:
                    body.append("(no messages yet — press t for the live screen)", "dim")
        # only repaint and re-scroll when the content really changed
        if body.plain != self.shown:
            self.shown = body.plain
            self.query_one("#preview", Static).update(body)
            box.scroll_end(animate=False)

    @on(OptionList.OptionHighlighted, "#agents")
    def highlighted(self, event: OptionList.OptionHighlighted) -> None:
        key = event.option.id
        if key and key != self.selected_key:
            self.selected_key = key
            self.view_override = None
            self.show_preview()

    # --- actions ---------------------------------------------------------

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        # dashboard keys must not fire underneath a dialog
        if isinstance(self.screen, ModalScreen) and action != "quit":
            return False
        return True

    async def do(self, coro, ok: str = "") -> None:
        r = await coro
        if not r.ok:
            self.notify(r.message, severity="error")
        elif ok:
            self.notify(ok)
        self.refresh_now()

    def action_refresh(self) -> None:
        self.refresh_now()

    def action_move(self, step: int) -> None:
        ol = self.query_one("#agents", OptionList)
        ol.action_cursor_down() if step > 0 else ol.action_cursor_up()

    def action_toggle_view(self) -> None:
        if a := self.current():
            self.view_override = "chat" if self.view_mode(a) == "screen" else "screen"
            self.show_preview()

    def action_reply(self) -> None:
        a = self.current()
        if a is None:
            return
        if a.state == "permission":
            # typed text + Enter would answer the dialog, possibly with the wrong choice
            self.notify(f"{a.name} is showing a prompt — answer it with 1/2/3/esc, or attach (a)")
            return
        self.query_one("#reply", Input).focus()

    def action_escape(self) -> None:
        if isinstance(self.focused, Input):
            self.query_one("#agents", OptionList).focus()
        else:
            self.action_key("Escape")

    @on(Input.Submitted, "#reply")
    def reply_submitted(self, event: Input.Submitted) -> None:
        a = self.current()
        text = event.value.strip()
        if a and text and a.state == "permission":
            self.notify(f"not sent: {a.name} is showing a prompt", severity="warning")
        elif a and text:
            self.run_worker(self.do(actions.send(a.host, a.name, text), f"sent to {a.name}"))
            event.input.clear()
        self.query_one("#agents", OptionList).focus()

    def action_key(self, key: str) -> None:
        a = self.current()
        if a is None:
            return
        if a.state != "permission":
            self.notify(f"{a.name} is not waiting on a prompt — attach (a) to send raw keys")
            return
        self.run_worker(self.do(actions.send_key(a.host, a.name, key)))

    def action_attach(self) -> None:
        a = self.current()
        if a is None:
            return
        with self.suspend():
            subprocess.run(actions.attach_argv(a.host, a.name))
        self.refresh_now()

    def action_new(self) -> None:
        def start(result: dict | None) -> None:
            if result:
                self.selected_key = f"{result['host']}/{result['name']}"
                self.run_worker(self.do(actions.spawn(**result), f"started {result['name']}"))

        self.push_screen(NewAgent(self.config.hosts, self.config.default_dir), start)

    def action_kill(self) -> None:
        a = self.current()
        if a is None:
            return

        def confirmed(yes: bool | None) -> None:
            if yes:
                self.run_worker(self.do(actions.kill(a.host, a.name), f"killed {a.name}"))

        self.push_screen(Confirm(f"Kill {a.name} on {a.host}? Its tmux session will be closed."), confirmed)
