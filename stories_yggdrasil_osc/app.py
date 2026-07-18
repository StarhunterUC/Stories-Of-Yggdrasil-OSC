from __future__ import annotations

import os
import queue
import subprocess
import sys
import time
import uuid
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from PIL import Image, ImageTk

from . import __version__
from .combat import CombatState
from .config import get_app_data_dir, get_log_path, load_config, load_runtime_state, save_config, save_runtime_state
from .controller import BridgeController
from .models import EventResult
from .osc_service import OSCEvent, OSCService
from .sam_client import SamClient, SamEvent
from .update_manager import UpdateEvent, UpdateManager

THEME = {
    "bg": "#090a0d",
    "sidebar": "#0e1014",
    "panel": "#12151a",
    "panel2": "#181c22",
    "panel3": "#20262d",
    "border": "#2e3740",
    "gold": "#d6b45b",
    "gold2": "#f1d98e",
    "text": "#edf0f2",
    "muted": "#98a1aa",
    "green": "#39b96d",
    "blue": "#4c87c7",
    "red": "#c84e55",
    "yellow": "#d6a947",
}


class StoriesOSCApp:
    POLL_MS = 45

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"Stories Of Yggdrasil OSC {__version__}")
        self.root.geometry("1220x760")
        self.root.minsize(1040, 680)
        self.root.configure(bg=THEME["bg"])

        self.install_dir = Path(__file__).resolve().parents[1]
        self._logo_image: ImageTk.PhotoImage | None = None
        self._set_window_icon()

        self.config = load_config()
        profile = self.config["profile"]
        runtime = load_runtime_state(int(profile.get("starting_hp", profile["maximum_hp"])))
        self.state = CombatState(
            maximum_hp=int(profile["maximum_hp"]),
            current_hp=int(runtime.get("current_hp", profile.get("starting_hp", profile["maximum_hp"]))),
            damage_values=self.config["combat"]["damage"],
            invulnerability_seconds=float(self.config["combat"]["global_invulnerability_seconds"]),
            critical_hp_percent=float(profile.get("critical_hp_percent", 0.25)),
            status_rules=self.config["statuses"],
            clear_statuses_when_disabled=bool(self.config["combat"].get("clear_statuses_when_disabled", True)),
            combat_enabled=bool(runtime.get("combat_enabled", False)),
        )

        self.osc_events: queue.Queue[OSCEvent] = queue.Queue()
        self.sam_events: queue.Queue[SamEvent] = queue.Queue()
        self.update_events: queue.Queue[UpdateEvent] = queue.Queue()
        self.osc = self._make_osc_service()
        self.sam_client = SamClient(self.sam_events, self.config.get("sam", {}))
        self.update_manager = UpdateManager(self.update_events, __version__)
        self.controller = BridgeController(
            config=self.config,
            state=self.state,
            send_parameter=self._send_parameter,
            pulse_parameter=self._pulse_parameter,
            event_sink=self._on_result,
        )

        self.closing = False
        self.output_cache: dict[str, Any] = {}
        self.last_avatar_id = "—"
        self.last_event = "Program started."
        self.event_rows: list[dict[str, str]] = []
        self.remote_character: dict[str, Any] = {}
        self.remote_state: dict[str, Any] = {}
        self.remote_mp = 0
        self.remote_max_mp = 0
        self.recovery_options: list[dict[str, Any]] = []
        self.recovery_by_row: dict[str, dict[str, Any]] = {}
        self.latest_release: dict[str, Any] = {}

        self.sam_sync_due_at = 0.0
        self.sam_sync_inflight = False
        self.sam_local_dirty = False
        self.sam_client_seq = 0
        self.sam_client_session = uuid.uuid4().hex
        self.sam_last_event_name = "startup"
        self.sam_last_revision = -1
        self.sam_last_dm_gate_active = False
        self.sam_last_rejection_at = 0.0
        self.sam_status_handoff_signature = ""

        self._setup_styles()
        self._build_ui()
        self.sam_client.start()
        self._append_activity("SYSTEM", f"Stories Of Yggdrasil OSC v{__version__} started.")
        self._refresh_ui()

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(self.POLL_MS, self._poll)
        self.root.after(500, self._refresh_loop)
        self.root.after(1000, self._autosave_tick)
        if self.config["osc"].get("auto_start_listener", True):
            self.root.after(120, self.start_listener)
        if self.config.get("updates", {}).get("check_on_start", True):
            self.root.after(1600, self.check_for_updates)

    # ------------------------------------------------------------------
    # Window / style
    # ------------------------------------------------------------------
    def _asset_path(self, name: str) -> Path:
        return self.install_dir / "assets" / name

    def _set_window_icon(self) -> None:
        try:
            ico = self._asset_path("stories_osc_icon.ico")
            if os.name == "nt" and ico.exists():
                self.root.iconbitmap(default=str(ico))
            png = self._asset_path("stories_osc_icon.png")
            if png.exists():
                image = Image.open(png).convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
                self._logo_image = ImageTk.PhotoImage(image)
                self.root.iconphoto(True, self._logo_image)
        except Exception:
            pass

    def _setup_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=THEME["bg"])
        style.configure("Sidebar.TFrame", background=THEME["sidebar"])
        style.configure("Panel.TFrame", background=THEME["panel"])
        style.configure("Card.TFrame", background=THEME["panel2"], relief="solid", borderwidth=1)
        style.configure("CardInner.TFrame", background=THEME["panel2"], relief="flat", borderwidth=0)
        style.configure("TLabel", background=THEME["bg"], foreground=THEME["text"], font=("Segoe UI", 10))
        style.configure("Panel.TLabel", background=THEME["panel"], foreground=THEME["text"])
        style.configure("Card.TLabel", background=THEME["panel2"], foreground=THEME["text"])
        style.configure("Muted.TLabel", background=THEME["bg"], foreground=THEME["muted"])
        style.configure("Muted.Panel.TLabel", background=THEME["panel"], foreground=THEME["muted"])
        style.configure("Muted.Card.TLabel", background=THEME["panel2"], foreground=THEME["muted"])
        style.configure("Brand.TLabel", background=THEME["panel"], foreground=THEME["gold2"], font=("Segoe UI Semibold", 18))
        style.configure("Version.TLabel", background=THEME["panel"], foreground=THEME["muted"], font=("Segoe UI", 9))
        style.configure("PageTitle.TLabel", background=THEME["bg"], foreground=THEME["gold2"], font=("Segoe UI Semibold", 16))
        style.configure("CardTitle.TLabel", background=THEME["panel2"], foreground=THEME["gold2"], font=("Segoe UI Semibold", 11))
        style.configure("Character.TLabel", background=THEME["panel2"], foreground=THEME["gold2"], font=("Segoe UI Semibold", 18))
        style.configure("BigValue.TLabel", background=THEME["panel2"], foreground=THEME["text"], font=("Segoe UI Semibold", 13))
        style.configure("StatusOff.TLabel", background=THEME["panel3"], foreground=THEME["muted"], padding=(10, 5), font=("Segoe UI Semibold", 9))
        style.configure("StatusOn.TLabel", background="#183827", foreground="#75e69f", padding=(10, 5), font=("Segoe UI Semibold", 9))
        style.configure("TButton", padding=(12, 8), font=("Segoe UI Semibold", 9), background=THEME["panel3"], foreground=THEME["text"], bordercolor=THEME["border"])
        style.map("TButton", background=[("active", "#2a333c"), ("pressed", "#333e49")])
        style.configure("Gold.TButton", background=THEME["gold"], foreground="#15120b")
        style.map("Gold.TButton", background=[("active", THEME["gold2"])])
        style.configure("Green.TButton", background="#1e7142", foreground=THEME["text"])
        style.map("Green.TButton", background=[("active", "#279055")])
        style.configure("Danger.TButton", background="#6a252b", foreground=THEME["text"])
        style.map("Danger.TButton", background=[("active", "#8d323a")])
        style.configure("Nav.TButton", background=THEME["sidebar"], foreground=THEME["muted"], borderwidth=0, padding=(10, 13), font=("Segoe UI Semibold", 10))
        style.map("Nav.TButton", background=[("active", THEME["panel2"])], foreground=[("active", THEME["gold2"])])
        style.configure("HP.Horizontal.TProgressbar", troughcolor="#28312c", background=THEME["green"], lightcolor=THEME["green"], darkcolor=THEME["green"], bordercolor=THEME["border"])
        style.configure("MP.Horizontal.TProgressbar", troughcolor="#242c36", background=THEME["blue"], lightcolor=THEME["blue"], darkcolor=THEME["blue"], bordercolor=THEME["border"])
        style.configure("Treeview", background=THEME["panel2"], fieldbackground=THEME["panel2"], foreground=THEME["text"], rowheight=28, bordercolor=THEME["border"])
        style.configure("Treeview.Heading", background=THEME["panel3"], foreground=THEME["gold2"], font=("Segoe UI Semibold", 9))
        style.map("Treeview", background=[("selected", "#374654")])
        style.configure("TCheckbutton", background=THEME["panel2"], foreground=THEME["text"])
        style.map("TCheckbutton", background=[("active", THEME["panel2"])])
        style.configure("TCombobox", fieldbackground=THEME["panel3"], background=THEME["panel3"], foreground=THEME["text"])

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.shell = ttk.Frame(self.root)
        self.shell.pack(fill=tk.BOTH, expand=True)
        self.sidebar = ttk.Frame(self.shell, style="Sidebar.TFrame", width=150)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)
        self.content = ttk.Frame(self.shell)
        self.content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        logo_wrap = ttk.Frame(self.sidebar, style="Sidebar.TFrame")
        logo_wrap.pack(fill=tk.X, pady=(20, 20))
        try:
            png = self._asset_path("stories_osc_icon.png")
            image = Image.open(png).convert("RGBA").resize((72, 72), Image.Resampling.LANCZOS)
            self.sidebar_logo = ImageTk.PhotoImage(image)
            ttk.Label(logo_wrap, image=self.sidebar_logo, background=THEME["sidebar"]).pack()
        except Exception:
            ttk.Label(logo_wrap, text="Y", background=THEME["sidebar"], foreground=THEME["gold2"], font=("Georgia", 32, "bold")).pack()

        self.nav_buttons: dict[str, ttk.Button] = {}
        for key, label in (("overview", "♡  Overview"), ("recovery", "✦  Recovery"), ("connection", "↔  Connection"), ("settings", "⚙  Settings")):
            button = ttk.Button(self.sidebar, text=label, style="Nav.TButton", command=lambda k=key: self.show_page(k))
            button.pack(fill=tk.X, padx=10, pady=4)
            self.nav_buttons[key] = button
        ttk.Label(self.sidebar, text=f"v{__version__}", background=THEME["sidebar"], foreground=THEME["muted"], font=("Segoe UI", 9)).pack(side=tk.BOTTOM, pady=16)

        self._build_topbar()
        self.page_host = ttk.Frame(self.content)
        self.page_host.pack(fill=tk.BOTH, expand=True, padx=22, pady=(0, 20))
        self.pages: dict[str, ttk.Frame] = {}
        self.pages["overview"] = self._build_overview_page()
        self.pages["recovery"] = self._build_recovery_page()
        self.pages["connection"] = self._build_connection_page()
        self.pages["settings"] = self._build_settings_page()
        self.show_page("overview")

        self.footer = ttk.Frame(self.content, style="Panel.TFrame")
        self.footer.pack(fill=tk.X, side=tk.BOTTOM)
        self.footer_listener = ttk.Label(self.footer, text="OSC stopped", style="Muted.Panel.TLabel")
        self.footer_listener.pack(side=tk.LEFT, padx=18, pady=7)
        self.footer_sam = ttk.Label(self.footer, text="Sam.py not paired", style="Muted.Panel.TLabel")
        self.footer_sam.pack(side=tk.RIGHT, padx=18, pady=7)

    def _build_topbar(self) -> None:
        top = ttk.Frame(self.content, style="Panel.TFrame")
        top.pack(fill=tk.X, padx=22, pady=(18, 16))
        brand = ttk.Frame(top, style="Panel.TFrame")
        brand.pack(side=tk.LEFT, padx=18, pady=12)
        ttk.Label(brand, text="Stories Of Yggdrasil OSC", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(brand, text=f"Version {__version__}", style="Version.TLabel").pack(anchor="w")
        self.update_button = ttk.Button(top, text="Check for updates", command=self.check_for_updates)
        self.update_button.pack(side=tk.RIGHT, padx=18, pady=16)

    def _new_page(self) -> ttk.Frame:
        page = ttk.Frame(self.page_host)
        return page

    def _card(self, parent: tk.Misc) -> ttk.Frame:
        return ttk.Frame(parent, style="Card.TFrame")

    def show_page(self, key: str) -> None:
        for page in self.pages.values():
            page.pack_forget()
        self.pages[key].pack(fill=tk.BOTH, expand=True)
        if key == "recovery":
            self.refresh_recovery_options()

    def _build_overview_page(self) -> ttk.Frame:
        page = self._new_page()
        ttk.Label(page, text="Character Overview", style="PageTitle.TLabel").pack(anchor="w", pady=(0, 12))
        body = ttk.Frame(page)
        body.pack(fill=tk.BOTH, expand=True)
        left = self._card(body)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        right = self._card(body)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))

        self.character_name_label = ttk.Label(left, text="Not paired", style="Character.TLabel")
        self.character_name_label.pack(anchor="w", padx=22, pady=(22, 3))
        self.character_meta_label = ttk.Label(left, text="Pair this device with Sam.py to load a character.", style="Muted.Card.TLabel")
        self.character_meta_label.pack(anchor="w", padx=22, pady=(0, 18))

        hp_head = ttk.Frame(left, style="CardInner.TFrame")
        hp_head.pack(fill=tk.X, padx=22)
        ttk.Label(hp_head, text="HP", style="BigValue.TLabel").pack(side=tk.LEFT)
        self.hp_value_label = ttk.Label(hp_head, text="0 / 0", style="Muted.Card.TLabel")
        self.hp_value_label.pack(side=tk.RIGHT)
        self.hp_bar = ttk.Progressbar(left, maximum=100, value=100, style="HP.Horizontal.TProgressbar")
        self.hp_bar.pack(fill=tk.X, padx=22, pady=(6, 16), ipady=7)

        mp_head = ttk.Frame(left, style="CardInner.TFrame")
        mp_head.pack(fill=tk.X, padx=22)
        ttk.Label(mp_head, text="MP", style="BigValue.TLabel").pack(side=tk.LEFT)
        self.mp_value_label = ttk.Label(mp_head, text="0 / 0", style="Muted.Card.TLabel")
        self.mp_value_label.pack(side=tk.RIGHT)
        self.mp_bar = ttk.Progressbar(left, maximum=100, value=0, style="MP.Horizontal.TProgressbar")
        self.mp_bar.pack(fill=tk.X, padx=22, pady=(6, 18), ipady=7)

        toggle_row = ttk.Frame(left, style="CardInner.TFrame")
        toggle_row.pack(fill=tk.X, padx=22, pady=(0, 16))
        ttk.Label(toggle_row, text="RP Combat", style="CardTitle.TLabel").pack(side=tk.LEFT)
        self.combat_var = tk.BooleanVar(value=self.state.combat_enabled)
        self.combat_toggle = ttk.Checkbutton(toggle_row, text="Enabled", variable=self.combat_var, command=self._combat_toggle_from_ui)
        self.combat_toggle.pack(side=tk.RIGHT)

        ttk.Label(left, text="Active Status", style="CardTitle.TLabel").pack(anchor="w", padx=22, pady=(4, 8))
        self.status_frame = ttk.Frame(left, style="CardInner.TFrame")
        self.status_frame.pack(fill=tk.X, padx=18, pady=(0, 18))
        self.status_labels: dict[str, ttk.Label] = {}
        for index, name in enumerate(("Burn", "Bleed", "Silence", "Freeze", "Bind")):
            label = ttk.Label(self.status_frame, text=name, style="StatusOff.TLabel")
            label.grid(row=index // 3, column=index % 3, sticky="ew", padx=4, pady=4)
            self.status_labels[name.lower()] = label
        for col in range(3):
            self.status_frame.columnconfigure(col, weight=1)

        self.dm_gate_label = ttk.Label(left, text="Dungeon Master Gate: CLOSED", style="Muted.Card.TLabel")
        self.dm_gate_label.pack(anchor="w", padx=22, pady=(0, 22))

        title_row = ttk.Frame(right, style="CardInner.TFrame")
        title_row.pack(fill=tk.X, padx=18, pady=(18, 8))
        ttk.Label(title_row, text="Recent Activity", style="CardTitle.TLabel").pack(side=tk.LEFT)
        ttk.Button(title_row, text="Clear", command=self.clear_activity).pack(side=tk.RIGHT)
        self.event_tree = ttk.Treeview(right, columns=("time", "type", "event"), show="headings", height=18)
        self.event_tree.heading("time", text="Time")
        self.event_tree.heading("type", text="Type")
        self.event_tree.heading("event", text="Event")
        self.event_tree.column("time", width=78, anchor="center", stretch=False)
        self.event_tree.column("type", width=86, anchor="center", stretch=False)
        self.event_tree.column("event", width=520)
        self.event_tree.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 18))
        return page

    def _build_recovery_page(self) -> ttk.Frame:
        page = self._new_page()
        header = ttk.Frame(page)
        header.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(header, text="Recovery", style="PageTitle.TLabel").pack(side=tk.LEFT)
        ttk.Button(header, text="Refresh", command=self.refresh_recovery_options).pack(side=tk.RIGHT)
        self.recovery_summary_label = ttk.Label(page, text="Potions, ethers, and restorative magick are calculated by Sam.py.", style="Muted.TLabel")
        self.recovery_summary_label.pack(anchor="w", pady=(0, 10))
        card = self._card(page)
        card.pack(fill=tk.BOTH, expand=True)
        self.recovery_tree = ttk.Treeview(card, columns=("kind", "name", "effect", "cost", "available"), show="headings")
        for key, title, width in (("kind", "Type", 85), ("name", "Recovery", 190), ("effect", "Expected Result", 250), ("cost", "Cost", 130), ("available", "Available", 110)):
            self.recovery_tree.heading(key, text=title)
            self.recovery_tree.column(key, width=width, anchor="w")
        self.recovery_tree.pack(fill=tk.BOTH, expand=True, padx=18, pady=(18, 10))
        actions = ttk.Frame(card, style="CardInner.TFrame")
        actions.pack(fill=tk.X, padx=18, pady=(0, 18))
        self.use_recovery_button = ttk.Button(actions, text="Use Selected", style="Green.TButton", command=self.use_selected_recovery)
        self.use_recovery_button.pack(side=tk.RIGHT)
        self.recovery_notice_label = ttk.Label(actions, text="Select an option. Actual recovery cannot exceed missing HP or MP.", style="Muted.Card.TLabel")
        self.recovery_notice_label.pack(side=tk.LEFT)
        return page

    def _build_connection_page(self) -> ttk.Frame:
        page = self._new_page()
        ttk.Label(page, text="Connection", style="PageTitle.TLabel").pack(anchor="w", pady=(0, 12))
        row = ttk.Frame(page)
        row.pack(fill=tk.BOTH, expand=True)
        sam_card = self._card(row)
        sam_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        osc_card = self._card(row)
        osc_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))

        ttk.Label(sam_card, text="Sam.py Pairing", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(20, 12))
        sam_cfg = self.config.get("sam", {})
        self.sam_url_var = tk.StringVar(value=str(sam_cfg.get("base_url") or "https://admin.storiesofyggdrasil.com/api/osc"))
        self.sam_device_var = tk.StringVar(value=str(sam_cfg.get("device_name") or "Stories OSC Desktop"))
        self.sam_code_var = tk.StringVar()
        self._entry(sam_card, 1, "Server", self.sam_url_var)
        self._entry(sam_card, 2, "Device", self.sam_device_var)
        self._entry(sam_card, 3, "Pairing code", self.sam_code_var, show="")
        buttons = ttk.Frame(sam_card, style="CardInner.TFrame")
        buttons.grid(row=4, column=0, columnspan=2, sticky="ew", padx=20, pady=12)
        ttk.Button(buttons, text="Pair Device", style="Gold.TButton", command=self.pair_with_sam).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(buttons, text="Test", command=self.test_sam_connection).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="Unlink", style="Danger.TButton", command=self.unlink_from_sam).pack(side=tk.LEFT, padx=6)
        self.sam_status_label = ttk.Label(sam_card, text="Not paired", style="Muted.Card.TLabel", wraplength=430, justify="left")
        self.sam_status_label.grid(row=5, column=0, columnspan=2, sticky="w", padx=20, pady=(2, 20))
        sam_card.columnconfigure(1, weight=1)

        ttk.Label(osc_card, text="VRChat OSC", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(20, 12))
        self.listener_status_label = ttk.Label(osc_card, text="Listener stopped", style="Muted.Card.TLabel")
        self.listener_status_label.grid(row=1, column=0, columnspan=2, sticky="w", padx=20, pady=4)
        self.avatar_status_label = ttk.Label(osc_card, text="Avatar: —", style="Muted.Card.TLabel")
        self.avatar_status_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=20, pady=4)
        self.activity_status_label = ttk.Label(osc_card, text="VRChat activity: none", style="Muted.Card.TLabel")
        self.activity_status_label.grid(row=3, column=0, columnspan=2, sticky="w", padx=20, pady=4)
        osc_buttons = ttk.Frame(osc_card, style="CardInner.TFrame")
        osc_buttons.grid(row=4, column=0, columnspan=2, sticky="ew", padx=20, pady=18)
        ttk.Button(osc_buttons, text="Start Listener", style="Green.TButton", command=self.start_listener).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(osc_buttons, text="Stop", command=self.stop_listener).pack(side=tk.LEFT, padx=6)
        ttk.Button(osc_buttons, text="Restart", command=self.restart_listener).pack(side=tk.LEFT, padx=6)
        ttk.Label(osc_card, text="VRChat defaults: receive 9000, send 9001.", style="Muted.Card.TLabel").grid(row=5, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 20))
        return page

    def _build_settings_page(self) -> ttk.Frame:
        page = self._new_page()
        ttk.Label(page, text="Settings", style="PageTitle.TLabel").pack(anchor="w", pady=(0, 12))
        canvas = tk.Canvas(page, bg=THEME["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas)
        body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        osc = self.config["osc"]
        combat = self.config["combat"]
        bridge = self.config["avatar_bridge"]
        sam = self.config["sam"]
        updates = self.config["updates"]

        network = self._card(body)
        network.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(network, text="Network", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", padx=20, pady=(18, 10))
        self.listen_ip_var = tk.StringVar(value=str(osc["listen_ip"]))
        self.listen_port_var = tk.StringVar(value=str(osc["listen_port"]))
        self.vrchat_ip_var = tk.StringVar(value=str(osc["vrchat_ip"]))
        self.vrchat_port_var = tk.StringVar(value=str(osc["vrchat_port"]))
        self.auto_start_var = tk.BooleanVar(value=bool(osc.get("auto_start_listener", True)))
        self._entry(network, 1, "Listen IP", self.listen_ip_var, col=0)
        self._entry(network, 1, "Listen port", self.listen_port_var, col=2)
        self._entry(network, 2, "VRChat IP", self.vrchat_ip_var, col=0)
        self._entry(network, 2, "VRChat port", self.vrchat_port_var, col=2)
        ttk.Checkbutton(network, text="Start listener automatically", variable=self.auto_start_var).grid(row=3, column=0, columnspan=4, sticky="w", padx=20, pady=(4, 16))
        for col in (1, 3): network.columnconfigure(col, weight=1)

        damage = self._card(body)
        damage.pack(fill=tk.X, pady=10)
        ttk.Label(damage, text="Contact Damage", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", padx=20, pady=(18, 10))
        self.damage_vars: dict[str, tk.StringVar] = {}
        for index, key in enumerate(("weak", "average", "strong", "critical")):
            var = tk.StringVar(value=str(combat["damage"][key]))
            self.damage_vars[key] = var
            self._entry(damage, 1 + index // 2, key.title(), var, col=(index % 2) * 2)
        for col in (1, 3): damage.columnconfigure(col, weight=1)

        avatar = self._card(body)
        avatar.pack(fill=tk.X, pady=10)
        ttk.Label(avatar, text="Avatar Health Bridge", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", padx=20, pady=(18, 10))
        self.input_mode_var = tk.StringVar(value=str(bridge.get("input_mode", "auto")))
        ttk.Label(avatar, text="Input mode", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=20, pady=6)
        ttk.Combobox(avatar, textvariable=self.input_mode_var, values=("auto", "external", "direct"), state="readonly").grid(row=1, column=1, sticky="ew", padx=(0, 20), pady=6)
        self.observe_health_var = tk.BooleanVar(value=bool(bridge.get("observe_health", True)))
        self.health_invert_var = tk.BooleanVar(value=bool(bridge.get("health_invert", True)))
        self.drive_health_var = tk.BooleanVar(value=bool(sam.get("drive_avatar_health_from_sam", False)))
        self.drive_status_var = tk.BooleanVar(value=bool(sam.get("drive_avatar_statuses_from_sam", False)))
        ttk.Checkbutton(avatar, text="Observe avatar Health parameter", variable=self.observe_health_var).grid(row=2, column=0, columnspan=2, sticky="w", padx=20, pady=5)
        ttk.Checkbutton(avatar, text="Health value represents accumulated damage", variable=self.health_invert_var).grid(row=2, column=2, columnspan=2, sticky="w", padx=20, pady=5)
        ttk.Checkbutton(avatar, text="Drive avatar Health from Sam.py", variable=self.drive_health_var).grid(row=3, column=0, columnspan=2, sticky="w", padx=20, pady=5)
        ttk.Checkbutton(avatar, text="Drive avatar status parameters from Sam.py", variable=self.drive_status_var).grid(row=3, column=2, columnspan=2, sticky="w", padx=20, pady=(5, 16))
        avatar.columnconfigure(1, weight=1)

        update_card = self._card(body)
        update_card.pack(fill=tk.X, pady=10)
        ttk.Label(update_card, text="Updates", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(18, 10))
        self.github_repo_var = tk.StringVar(value=str(updates.get("github_repo") or ""))
        self.update_on_start_var = tk.BooleanVar(value=bool(updates.get("check_on_start", True)))
        self._entry(update_card, 1, "GitHub repository", self.github_repo_var)
        ttk.Checkbutton(update_card, text="Check for updates when the program starts", variable=self.update_on_start_var).grid(row=2, column=0, columnspan=2, sticky="w", padx=20, pady=(5, 16))
        update_card.columnconfigure(1, weight=1)

        actions = ttk.Frame(body)
        actions.pack(fill=tk.X, pady=(10, 20))
        ttk.Button(actions, text="Save Settings", style="Gold.TButton", command=self.save_settings).pack(side=tk.RIGHT)
        ttk.Button(actions, text="Open Settings Folder", command=self.open_settings_folder).pack(side=tk.RIGHT, padx=8)
        return page

    def _entry(self, parent: ttk.Frame, row: int, label: str, variable: tk.Variable, *, col: int = 0, show: str | None = None) -> None:
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=col, sticky="w", padx=20, pady=6)
        kwargs: dict[str, Any] = {"textvariable": variable, "bg": THEME["panel3"], "fg": THEME["text"], "insertbackground": THEME["text"], "relief": tk.FLAT}
        if show is not None:
            kwargs["show"] = show
        entry = tk.Entry(parent, **kwargs)
        entry.grid(row=row, column=col + 1, sticky="ew", padx=(0, 20), pady=6, ipady=6)

    # ------------------------------------------------------------------
    # OSC processing
    # ------------------------------------------------------------------
    def _make_osc_service(self) -> OSCService:
        cfg = self.config["osc"]
        return OSCService(
            listen_ip=str(cfg["listen_ip"]),
            listen_port=int(cfg["listen_port"]),
            vrchat_ip=str(cfg["vrchat_ip"]),
            vrchat_port=int(cfg["vrchat_port"]),
            event_queue=self.osc_events,
        )

    def start_listener(self) -> None:
        try:
            self.osc.start()
            self._append_activity("SYSTEM", f"OSC listening on {self.osc.listen_ip}:{self.osc.listen_port}.")
        except Exception as exc:
            self._append_activity("ERROR", f"OSC listener failed: {exc}")
            messagebox.showerror("OSC Listener", f"Could not start the OSC listener.\n\n{exc}")
        self._refresh_ui()

    def stop_listener(self) -> None:
        self.osc.stop()
        self._append_activity("SYSTEM", "OSC listener stopped.")
        self._refresh_ui()

    def restart_listener(self) -> None:
        self.stop_listener()
        self.root.after(150, self.start_listener)

    def _poll(self) -> None:
        if self.closing:
            return
        try:
            while True:
                self._handle_osc_event(self.osc_events.get_nowait())
        except queue.Empty:
            pass
        try:
            while True:
                self._handle_sam_event(self.sam_events.get_nowait())
        except queue.Empty:
            pass
        try:
            while True:
                self._handle_update_event(self.update_events.get_nowait())
        except queue.Empty:
            pass
        self.controller.tick()
        if self.sam_sync_due_at and time.monotonic() >= self.sam_sync_due_at and not self.sam_sync_inflight:
            self._push_sam_state()
        self.root.after(self.POLL_MS, self._poll)

    def _handle_osc_event(self, event: OSCEvent) -> None:
        if event.kind == "system":
            return
        if event.address == "/avatar/change":
            self.last_avatar_id = str(event.values[0]) if event.values else "—"
            self.output_cache.clear()
            self.controller.handle_osc(event.address, event.values, event.received_at_monotonic)
            self._append_activity("AVATAR", f"Loaded avatar {self._short_avatar(self.last_avatar_id)}.")
            return
        if event.address.startswith("/avatar/parameters/") and self.last_avatar_id == "—":
            self.last_avatar_id = "Build & Test / local"
        self.controller.handle_osc(event.address, event.values, event.received_at_monotonic)

    def _send_parameter(self, name: str, value: Any) -> None:
        if not name:
            return
        if self.output_cache.get(name, object()) == value:
            return
        self.output_cache[name] = value
        try:
            self.osc.send_avatar_parameter(name, value)
        except Exception:
            pass

    def _pulse_parameter(self, name: str, duration: float) -> None:
        try:
            self.osc.pulse_avatar_parameter(name, duration)
        except Exception:
            pass

    def _combat_toggle_from_ui(self) -> None:
        result = self.state.set_combat_enabled(bool(self.combat_var.get()))
        self.controller.commit_result(result)
        self._send_parameter(self.config["parameters"]["combat_enabled"], bool(self.state.combat_enabled))

    def _on_result(self, result: EventResult) -> None:
        category = "EVENT" if result.accepted else "IGNORED"
        if result.event in {"damage", "dot_damage"}: category = "DAMAGE"
        elif result.event in {"healing", "revive"}: category = "HEAL"
        elif "status" in result.event: category = "STATUS"
        elif result.event == "blocked": category = "BLOCK"
        elif result.event == "external_detected": category = "AVATAR"
        self._append_activity(category, result.message)
        if result.accepted and result.event in {
            "damage", "dot_damage", "healing", "revive", "set_hp", "external_health_update",
            "status_applied", "status_expired", "statuses_cleared", "external_status_active",
            "external_status_cleared", "combat_toggle",
        }:
            self._schedule_sam_sync(result.event)

    # ------------------------------------------------------------------
    # Sam.py link and recovery
    # ------------------------------------------------------------------
    def _save_sam_form(self) -> dict[str, Any]:
        cfg = self.config.setdefault("sam", {})
        cfg["base_url"] = str(self.sam_url_var.get()).strip().rstrip("/") or "https://admin.storiesofyggdrasil.com/api/osc"
        cfg["device_name"] = str(self.sam_device_var.get()).strip() or "Stories OSC Desktop"
        save_config(self.config)
        self.sam_client.reconfigure(cfg)
        return cfg

    def pair_with_sam(self) -> None:
        cfg = self._save_sam_form()
        code = str(self.sam_code_var.get()).strip()
        if not code:
            messagebox.showwarning("Pairing Code", "Run /osc_link in Discord, then enter the one-use code.")
            return
        cfg["enabled"] = True
        self.sam_client.reconfigure(cfg)
        self.sam_status_label.configure(text="Pairing…", foreground=THEME["yellow"])
        self.sam_client.pair(code, str(cfg.get("device_name") or "Stories OSC Desktop"))

    def unlink_from_sam(self) -> None:
        if str(self.config.get("sam", {}).get("token") or "").strip():
            self.sam_client.unlink()
        else:
            self._clear_local_sam_link()

    def _clear_local_sam_link(self) -> None:
        cfg = self.config.setdefault("sam", {})
        cfg["token"] = ""
        cfg["enabled"] = False
        save_config(self.config)
        self.sam_client.reconfigure(cfg)
        self.remote_character = {}
        self.remote_state = {}
        self.sam_status_label.configure(text="Not paired", foreground=THEME["muted"])
        self._append_activity("SAM", "Sam.py device link removed.")
        self._refresh_ui()

    def test_sam_connection(self) -> None:
        self._save_sam_form()
        self.sam_client.test()

    def refresh_recovery_options(self) -> None:
        if not str(self.config.get("sam", {}).get("token") or "").strip():
            self.recovery_notice_label.configure(text="Pair this device with Sam.py before using recovery.")
            return
        self.recovery_notice_label.configure(text="Refreshing recovery options…")
        self.sam_client.recovery_options()

    def use_selected_recovery(self) -> None:
        selected = self.recovery_tree.selection()
        if not selected:
            messagebox.showinfo("Recovery", "Select a potion, ether, or spell first.")
            return
        option = self.recovery_by_row.get(selected[0])
        if not option:
            return
        if not bool(option.get("usable", True)):
            messagebox.showwarning("Recovery", str(option.get("unavailable_reason") or "That option cannot be used right now."))
            return
        name = str(option.get("name") or "")
        kind = str(option.get("kind") or "")
        if not messagebox.askyesno("Use Recovery", f"Use {name}?\n\n{option.get('effect_text', '')}"):
            return
        self.recovery_notice_label.configure(text=f"Using {name}…")
        self.sam_client.use_recovery(kind, name)

    def _schedule_sam_sync(self, event_name: str, *, immediate: bool = False) -> None:
        cfg = self.config.get("sam", {})
        if not bool(cfg.get("enabled", False)) or not str(cfg.get("token") or "").strip():
            return
        self.sam_local_dirty = True
        self.sam_last_event_name = str(event_name or "state_change")
        delay = 0.0 if immediate else max(0.05, float(cfg.get("push_debounce_seconds", 0.30)))
        self.sam_sync_due_at = time.monotonic() + delay

    def _build_sam_sync_payload(self) -> dict[str, Any]:
        cfg = self.config.get("sam", {})
        snap = self.state.snapshot()
        self.sam_client_seq += 1
        payload: dict[str, Any] = {
            "client_seq": self.sam_client_seq,
            "client_session": self.sam_client_session,
            "client_event": self.sam_last_event_name,
            "avatar_id": self.last_avatar_id,
            "source_mode": self.controller.active_input_mode,
            "client_drives_remote_statuses": bool(cfg.get("drive_avatar_statuses_from_sam", False)),
        }
        if bool(cfg.get("sync_hp", True)):
            payload["hp"] = int(snap["current_hp"])
            payload["hp_ratio"] = float(snap["hp_ratio"])
        if bool(cfg.get("sync_combat_toggle", True)):
            payload["combat_enabled"] = bool(snap["combat_enabled"])
        payload.update(dict(self.controller.telemetry))
        if int(payload.get("spell_type", 0) or 0) == 0:
            payload.pop("spell_type", None)
        hit_event = str(payload.get("hit_event") or "")
        if hit_event:
            self.controller.telemetry["hit_event"] = ""
        if bool(cfg.get("sync_statuses", True)):
            active = snap.get("statuses", {})
            statuses: dict[str, Any] = {}
            for name in ("burn", "bleed", "silence", "freeze", "bind"):
                info = active.get(name)
                remaining = None
                if isinstance(info, dict):
                    try:
                        raw = info.get("remaining")
                        remaining = None if raw is None or raw == float("inf") else max(1, int(float(raw)))
                    except Exception:
                        remaining = None
                statuses[name] = {"active": info is not None, "duration_seconds": remaining}
            payload["statuses"] = statuses
        return payload

    def _push_sam_state(self) -> None:
        self.sam_sync_due_at = 0.0
        if self.sam_sync_inflight:
            return
        self.sam_sync_inflight = True
        self.sam_client.sync(self._build_sam_sync_payload())

    def _handle_sam_event(self, event: SamEvent) -> None:
        if not event.ok:
            self.sam_sync_inflight = False
            self.sam_status_label.configure(text=event.message, foreground=THEME["red"])
            self._append_activity("SAM ERROR", event.message)
            return
        if event.kind == "paired":
            token = str(event.data.get("token") or "")
            if not token:
                self.sam_status_label.configure(text="Pairing failed: no device token returned.", foreground=THEME["red"])
                return
            cfg = self.config.setdefault("sam", {})
            cfg["token"] = token
            cfg["enabled"] = True
            save_config(self.config)
            self.sam_client.reconfigure(cfg)
            self.sam_code_var.set("")
            state = event.data.get("state")
            if isinstance(state, dict):
                self._apply_sam_state(state, source="pair", force=True)
            self.sam_status_label.configure(text="Paired and connected.", foreground=THEME["green"])
            self._append_activity("SAM", "Device paired with Sam.py.")
            self.sam_client.recovery_options()
            return
        if event.kind == "unlinked":
            self._clear_local_sam_link()
            return
        if event.kind == "test":
            state_response = event.data.get("state_response")
            if isinstance(state_response, dict) and isinstance(state_response.get("state"), dict):
                self._apply_sam_state(state_response["state"], source="test", force=False)
            self.sam_status_label.configure(text="Connection test passed.", foreground=THEME["green"])
            return
        if event.kind == "recovery_options":
            options = event.data.get("options") if isinstance(event.data.get("options"), list) else []
            self._populate_recovery(options, event.data)
            return
        if event.kind == "recovery_used":
            state = event.data.get("state")
            if isinstance(state, dict):
                self._apply_sam_state(state, source="recovery", force=True)
            self._append_activity("RECOVERY", event.message)
            self.recovery_notice_label.configure(text=event.message)
            self.sam_client.recovery_options()
            return
        if event.kind == "state":
            self.sam_sync_inflight = False
            state = event.data.get("state")
            rejected = False
            if isinstance(state, dict):
                sync_result = state.get("sync_result") if isinstance(state.get("sync_result"), dict) else {}
                rejected = bool(sync_result) and not bool(sync_result.get("accepted", True))
                self._apply_sam_state(state, source=event.source, force=event.source in {"sync", "pull"} or rejected)
                if rejected:
                    warning = str(sync_result.get("message") or "No Active DM's - No Hit Registered")
                    self._append_activity("WARNING", warning)
                    self.sam_status_label.configure(text=warning, foreground=THEME["red"])
                    self._restore_avatar_after_rejection(state, sync_result)
            if event.source == "sync":
                self.sam_local_dirty = False
            if not rejected:
                self.sam_status_label.configure(text="Connected to Sam.py.", foreground=THEME["green"])

    def _populate_recovery(self, options: list[dict[str, Any]], payload: dict[str, Any]) -> None:
        self.recovery_options = [x for x in options if isinstance(x, dict)]
        self.recovery_by_row.clear()
        for row in self.recovery_tree.get_children():
            self.recovery_tree.delete(row)
        for option in self.recovery_options:
            kind = str(option.get("kind") or "").title()
            name = str(option.get("name") or "")
            effect = str(option.get("effect_text") or "")
            cost = str(option.get("cost_text") or "—")
            available = str(option.get("available_text") or "")
            row = self.recovery_tree.insert("", tk.END, values=(kind, name, effect, cost, available))
            self.recovery_by_row[row] = option
        missing_hp = int(payload.get("missing_hp", 0) or 0)
        missing_mp = int(payload.get("missing_mp", 0) or 0)
        self.recovery_summary_label.configure(text=f"Missing HP: {missing_hp:,}   •   Missing MP: {missing_mp:,}   •   Values include owned item lores and equipment effects.")
        self.recovery_notice_label.configure(text=f"{len(self.recovery_options)} recovery option(s) available.")

    def _restore_avatar_after_rejection(self, state: dict[str, Any], sync_result: dict[str, Any]) -> None:
        char = state.get("character") if isinstance(state.get("character"), dict) else {}
        hp = max(0, int(char.get("hp", 0) or 0))
        max_hp = max(1, int(char.get("max_hp", max(hp, 1)) or 1))
        self.state.set_hp(hp)
        self.output_cache.clear()
        self.controller.sync_outputs()
        bridge = self.config.get("avatar_bridge", {})
        health_parameter = str(bridge.get("health_parameter", "Health") or "Health").strip()
        if health_parameter:
            ratio = max(0.0, min(1.0, hp / max_hp))
            value = 1.0 - ratio if bool(bridge.get("health_invert", True)) else ratio
            self._send_parameter(health_parameter, value)
        rejected = {str(x).lower() for x in sync_result.get("rejected_events", []) if str(x)}
        params = bridge.get("status_parameters", {})
        if isinstance(params, dict):
            for name in ("burn", "bleed", "silence", "freeze", "bind"):
                if f"status:{name}" in rejected and str(params.get(name) or "").strip():
                    self._send_parameter(str(params[name]), False)

    def _apply_sam_state(self, state: dict[str, Any], *, source: str, force: bool) -> None:
        char = state.get("character")
        if not isinstance(char, dict):
            return
        self.remote_state = dict(state)
        self.remote_character = dict(char)
        osc_state = state.get("osc") if isinstance(state.get("osc"), dict) else {}
        for param_key, value_key in (("enemy_mode", "enemy_mode"), ("mist_charge", "mist_charge"), ("mist_max", "mist_max"), ("mist_percent", "mist_percent"), ("diablos_applicable", "diablos_applicable"), ("diablos_percent", "diablos_percent")):
            parameter = str(self.config.get("parameters", {}).get(param_key) or "").strip()
            if parameter:
                self._send_parameter(parameter, osc_state.get(value_key, False if "applicable" in value_key or "enemy" in value_key else 0))
        rejected_heal = bool(osc_state.get("healing_rejected", False))
        if rejected_heal:
            parameter = str(self.config.get("parameters", {}).get("healing_rejected") or "").strip()
            if parameter:
                self._pulse_parameter(parameter, 0.25)
        name = str(char.get("name") or state.get("active_character") or "Unknown")
        hp = max(0, int(char.get("hp", 0) or 0))
        max_hp = max(1, int(char.get("max_hp", max(hp, 1)) or 1))
        self.remote_mp = max(0, int(char.get("mp", 0) or 0))
        self.remote_max_mp = max(0, int(char.get("max_mp", self.remote_mp) or 0))
        revision = int(state.get("revision", 0) or 0)
        self.sam_last_revision = max(self.sam_last_revision, revision)
        gate = state.get("dm_gate") if isinstance(state.get("dm_gate"), dict) else {}
        self.sam_last_dm_gate_active = bool(gate.get("active", False))

        cfg = self.config.get("sam", {})
        if bool(cfg.get("pull_remote_changes", True)) and not (source == "poll" and (self.sam_local_dirty or self.sam_sync_inflight) and not force):
            self.config["profile"]["name"] = name
            self.config["profile"]["maximum_hp"] = max_hp
            self.state.reconfigure(
                maximum_hp=max_hp,
                damage_values=self.config["combat"]["damage"],
                invulnerability_seconds=self.config["combat"]["global_invulnerability_seconds"],
                critical_hp_percent=self.config["profile"].get("critical_hp_percent", 0.25),
                status_rules=self.config["statuses"],
                preserve_ratio=False,
            )
            self.state.set_hp(hp)
            if bool(cfg.get("sync_combat_toggle", True)):
                enabled = bool(state.get("combat_enabled", self.state.combat_enabled))
                if enabled != self.state.combat_enabled:
                    self.state.set_combat_enabled(enabled)
            names = {str(x).strip().lower() for x in char.get("status_names", [])}
            for status_name in ("burn", "bleed", "silence", "freeze", "bind"):
                if status_name not in self.state.statuses:
                    self.state.set_external_status(status_name, status_name in names)
            self.output_cache.clear()
            self.controller.sync_outputs()
            self._send_parameter(self.config["parameters"]["combat_enabled"], self.state.combat_enabled)
            bridge = self.config.get("avatar_bridge", {})
            if bool(cfg.get("drive_avatar_health_from_sam", False)):
                ratio = max(0.0, min(1.0, hp / max_hp))
                value = 1.0 - ratio if bool(bridge.get("health_invert", True)) else ratio
                self._send_parameter(str(bridge.get("health_parameter") or "Health"), value)
            if bool(cfg.get("drive_avatar_statuses_from_sam", False)):
                params = bridge.get("status_parameters", {})
                if isinstance(params, dict):
                    for status_name in ("burn", "bleed", "silence", "freeze", "bind"):
                        if str(params.get(status_name) or "").strip():
                            self._send_parameter(str(params[status_name]), status_name in names)
                signature = ",".join(sorted(names.intersection({"burn", "bleed", "silence", "freeze", "bind"})))
                if signature != self.sam_status_handoff_signature:
                    self.sam_status_handoff_signature = signature
                    self._schedule_sam_sync("remote_status_handoff", immediate=True)
        self._refresh_ui()

    # ------------------------------------------------------------------
    # Updates and settings
    # ------------------------------------------------------------------
    def check_for_updates(self) -> None:
        updates = self.config.get("updates", {})
        repo = str(updates.get("github_repo") or "").strip()
        self.update_button.configure(text="Checking…")
        self.update_manager.check(repo, str(updates.get("asset_pattern") or ""))

    def _handle_update_event(self, event: UpdateEvent) -> None:
        if event.kind == "update_available":
            self.latest_release = dict(event.data)
            version = str(event.data.get("latest_version") or "new")
            self.update_button.configure(text=f"Update {version} available", style="Green.TButton", command=self.install_available_update)
            notes = str(event.data.get("release_notes") or "").strip()
            summary = notes[:700] + ("…" if len(notes) > 700 else "")
            if messagebox.askyesno("Update Available", f"Stories Of Yggdrasil OSC {version} is available.\n\n{summary}\n\nDownload and install it now?"):
                self.install_available_update()
        elif event.kind == "update_current":
            self.update_button.configure(text="Up to date")
        elif event.kind == "update_ready":
            script = str(event.data.get("script") or "")
            if messagebox.askyesno("Install Update", "The update is ready. Close the program and install it now?"):
                try:
                    UpdateManager.launch_installer(script)
                    self.close()
                except Exception as exc:
                    messagebox.showerror("Update", str(exc))
        else:
            self.update_button.configure(text="Update check unavailable")
            if event.message and "not configured" not in event.message.lower():
                self._append_activity("UPDATE", event.message)

    def install_available_update(self) -> None:
        if not self.latest_release:
            return
        self.update_button.configure(text="Downloading update…")
        self.update_manager.download_and_install(self.latest_release)

    def save_settings(self) -> None:
        try:
            osc = self.config["osc"]
            osc["listen_ip"] = str(self.listen_ip_var.get()).strip() or "127.0.0.1"
            osc["listen_port"] = int(self.listen_port_var.get())
            osc["vrchat_ip"] = str(self.vrchat_ip_var.get()).strip() or "127.0.0.1"
            osc["vrchat_port"] = int(self.vrchat_port_var.get())
            osc["auto_start_listener"] = bool(self.auto_start_var.get())
            for key, var in self.damage_vars.items():
                self.config["combat"]["damage"][key] = max(0, int(var.get()))
            bridge = self.config["avatar_bridge"]
            bridge["input_mode"] = str(self.input_mode_var.get())
            bridge["observe_health"] = bool(self.observe_health_var.get())
            bridge["health_invert"] = bool(self.health_invert_var.get())
            sam = self.config["sam"]
            sam["drive_avatar_health_from_sam"] = bool(self.drive_health_var.get())
            sam["drive_avatar_statuses_from_sam"] = bool(self.drive_status_var.get())
            updates = self.config["updates"]
            updates["github_repo"] = str(self.github_repo_var.get()).strip()
            updates["check_on_start"] = bool(self.update_on_start_var.get())
            save_config(self.config)
            was_running = self.osc.running
            self.osc.reconfigure(listen_ip=osc["listen_ip"], listen_port=osc["listen_port"], vrchat_ip=osc["vrchat_ip"], vrchat_port=osc["vrchat_port"], restart=was_running)
            self.state.reconfigure(
                maximum_hp=self.config["profile"]["maximum_hp"],
                damage_values=self.config["combat"]["damage"],
                invulnerability_seconds=self.config["combat"]["global_invulnerability_seconds"],
                critical_hp_percent=self.config["profile"].get("critical_hp_percent", 0.25),
                status_rules=self.config["statuses"],
                preserve_ratio=True,
            )
            self.controller.reconfigure(self.config)
            self.sam_client.reconfigure(sam)
            messagebox.showinfo("Settings", "Settings saved and applied.")
        except Exception as exc:
            messagebox.showerror("Settings", f"Could not apply settings.\n\n{exc}")

    # ------------------------------------------------------------------
    # UI refresh and persistence
    # ------------------------------------------------------------------
    def _refresh_loop(self) -> None:
        if self.closing:
            return
        self._refresh_ui()
        self.root.after(500, self._refresh_loop)

    def _refresh_ui(self) -> None:
        snap = self.state.snapshot()
        hp = int(snap["current_hp"])
        max_hp = int(snap["maximum_hp"])
        self.hp_bar.configure(value=float(snap["hp_ratio"]) * 100.0)
        self.hp_value_label.configure(text=f"{hp:,} / {max_hp:,}")
        mp_ratio = self.remote_mp / self.remote_max_mp if self.remote_max_mp else 0.0
        self.mp_bar.configure(value=max(0.0, min(100.0, mp_ratio * 100.0)))
        self.mp_value_label.configure(text=f"{self.remote_mp:,} / {self.remote_max_mp:,}")
        self.combat_var.set(bool(snap["combat_enabled"]))

        char = self.remote_character
        if char:
            name = str(char.get("name") or self.remote_state.get("active_character") or "Unknown")
            classes = char.get("classes") if isinstance(char.get("classes"), list) else []
            class_text = " / ".join(str(x) for x in classes if x and str(x) != "None") or str(char.get("class") or "—")
            self.character_name_label.configure(text=name)
            self.character_meta_label.configure(text=f"Level {int(char.get('level', 1) or 1)}  •  {class_text}  •  {char.get('race') or 'Unknown'}  •  {char.get('region') or 'Unknown'}")
        else:
            self.character_name_label.configure(text=str(self.config["profile"].get("name") or "Local Character"))
            self.character_meta_label.configure(text="Pair with Sam.py to load class, race, MP, inventory, and recovery options.")

        active = snap.get("statuses", {})
        for key, label in self.status_labels.items():
            label.configure(style="StatusOn.TLabel" if key in active else "StatusOff.TLabel")
        gate = self.remote_state.get("dm_gate") if isinstance(self.remote_state.get("dm_gate"), dict) else {}
        if bool(gate.get("active", False)):
            names = ", ".join(str(x) for x in gate.get("dm_names", []) if str(x))
            self.dm_gate_label.configure(text=f"Dungeon Master Gate: ACTIVE{(' — ' + names) if names else ''}", foreground=THEME["green"])
        else:
            self.dm_gate_label.configure(text="Dungeon Master Gate: CLOSED — incoming damage will be rejected", foreground=THEME["red"])

        running = bool(self.osc.running)
        listener_text = f"Listening {self.osc.listen_ip}:{self.osc.listen_port}" if running else "Listener stopped"
        self.listener_status_label.configure(text=listener_text, foreground=THEME["green"] if running else THEME["muted"])
        self.footer_listener.configure(text=f"OSC: {listener_text}", foreground=THEME["green"] if running else THEME["muted"])
        recent = self.controller.last_input_at and (time.monotonic() - self.controller.last_input_at) <= float(self.config["osc"].get("activity_timeout_seconds", 5.0))
        self.activity_status_label.configure(text="VRChat activity: active" if recent else "VRChat activity: waiting", foreground=THEME["green"] if recent else THEME["muted"])
        self.avatar_status_label.configure(text=f"Avatar: {self._short_avatar(self.last_avatar_id)}")
        paired = bool(str(self.config.get("sam", {}).get("token") or "").strip())
        self.footer_sam.configure(text=f"Sam.py: {'paired' if paired else 'not paired'}", foreground=THEME["green"] if paired else THEME["muted"])

    def _append_activity(self, category: str, message: str) -> None:
        self.last_event = str(message)
        stamp = datetime.now().strftime("%H:%M:%S")
        row = {"time": stamp, "type": str(category), "event": str(message)}
        self.event_rows.append(row)
        self.event_rows = self.event_rows[-100:]
        try:
            self.event_tree.insert("", 0, values=(stamp, category, message))
            for item in self.event_tree.get_children()[60:]:
                self.event_tree.delete(item)
        except Exception:
            pass
        try:
            with get_log_path().open("a", encoding="utf-8") as handle:
                handle.write(f"[{stamp}] [{category}] {message}\n")
        except Exception:
            pass

    def clear_activity(self) -> None:
        self.event_rows.clear()
        for item in self.event_tree.get_children():
            self.event_tree.delete(item)
        try:
            get_log_path().write_text("", encoding="utf-8")
        except Exception:
            pass

    def _autosave_tick(self) -> None:
        if self.closing:
            return
        save_runtime_state({"current_hp": int(self.state.current_hp), "combat_enabled": bool(self.state.combat_enabled)})
        self.root.after(1000, self._autosave_tick)

    def open_settings_folder(self) -> None:
        path = get_app_data_dir()
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showinfo("Settings Folder", f"{path}\n\n{exc}")

    @staticmethod
    def _short_avatar(value: str) -> str:
        return value if len(value) <= 28 else value[:14] + "…" + value[-10:]

    def close(self) -> None:
        if self.closing:
            return
        self.closing = True
        save_runtime_state({"current_hp": int(self.state.current_hp), "combat_enabled": bool(self.state.combat_enabled)})
        try: self.osc.stop()
        except Exception: pass
        try: self.sam_client.stop()
        except Exception: pass
        self.root.destroy()


def run() -> None:
    root = tk.Tk()
    StoriesOSCApp(root)
    root.mainloop()
