"""
WL Mouse Beast X — Desktop Config App
======================================
Requirements:
    pip install hid customtkinter

On Linux you may also need:
    sudo apt install libhidapi-hidraw0 libhidapi-libusb0
    # Add udev rule so you don't need sudo:
    echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="36a7", ATTRS{idProduct}=="a887", MODE="0666"' \
         | sudo tee /etc/udev/rules.d/99-beastx.rules
    sudo udevadm control --reload-rules && sudo udevadm trigger

On Windows: install the Zadig WinUSB driver for the mouse's HID interface
    (only needed if the stock software blocked raw HID access — usually not required)

Run:
    python beastx_app.py
"""

import tkinter as tk
import customtkinter as ctk
import json

# 'hidapi' package bundles its own DLL on Windows (more reliable in frozen exes).
# 'hid' package works on Linux/macOS using the system hidapi lib.
# Both expose the same API — we just try hidapi first, fall back to hid.
try:
    import hidapi as hid
except ImportError:
    import hid
import os
import sys
import threading
import time
from pathlib import Path

# ─── DEVICE ──────────────────────────────────────────────────────────────────
VID = 0x36A7
PID = 0xA887
REPORT_SIZE = 64  # bytes

# ─── PROTOCOL PACKETS ────────────────────────────────────────────────────────
# Exact bytes reverse-engineered from WL Mouse stock software (USB capture).
# Byte 0 is the report ID (0x04). Bytes padded to 64 bytes with 0x00.

POLL_PACKETS = {
    125:  [0x04,0x73,0x02,0x06,0x18,0x00,0x00,0x00,0x00,0x04,0x04,0x04,0x00,0x00,0x21,0x00,0x95,0x01,0x00,0x00,0x00,0x00,0x01,0x00,0x40,0x06,0x40,0x06,0x10,0x00,0xc8,0x01],
    250:  [0x04,0x71,0x83,0x06,0x18,0x00,0x00,0x00,0x00,0x04,0x04,0x04,0x00,0x00,0x21,0x00,0x95,0x01,0x00,0x01,0x00,0x00,0x01,0x00,0x40,0x06,0x40,0x06,0x10,0x00,0xc8,0x01],
    500:  [0x04,0x74,0x40,0x06,0x18,0x00,0x00,0x00,0x00,0x04,0x04,0x04,0x00,0x00,0x21,0x00,0x95,0x01,0x00,0x02,0x00,0x00,0x01,0x00,0x40,0x06,0x40,0x06,0x10,0x00,0xc8,0x01],
    1000: [0x04,0x76,0xc1,0x06,0x18,0x00,0x00,0x00,0x00,0x04,0x04,0x04,0x00,0x00,0x21,0x00,0x95,0x01,0x00,0x03,0x00,0x00,0x01,0x00,0x40,0x06,0x40,0x06,0x10,0x00,0xc8,0x01],
    2000: [0x04,0x7d,0x86,0x06,0x18,0x00,0x00,0x00,0x00,0x04,0x04,0x04,0x00,0x00,0x21,0x00,0x95,0x01,0x00,0x04,0x00,0x00,0x01,0x00,0x40,0x06,0x40,0x06,0x10,0x00,0xc8,0x01],
    4000: [0x04,0x7f,0x07,0x06,0x18,0x00,0x00,0x00,0x00,0x04,0x04,0x04,0x00,0x00,0x21,0x00,0x95,0x01,0x00,0x05,0x00,0x00,0x01,0x00,0x40,0x06,0x40,0x06,0x10,0x00,0xc8,0x01],
}

LOD_PACKETS = {
    0: [0x04,0x76,0xc1,0x06,0x18,0x00,0x00,0x00,0x00,0x04,0x04,0x04,0x00,0x00,0x21,0x00,0x95,0x01,0x00,0x03,0x00,0x00,0x01,0x00,0x40,0x06,0x40,0x06,0x10,0x00,0xc8,0x01],  # 1mm
    1: [0x04,0x72,0x3d,0x06,0x18,0x00,0x00,0x00,0x00,0x04,0x04,0x04,0x00,0x00,0x21,0x00,0x95,0x01,0x00,0x03,0x00,0x01,0x01,0x00,0x40,0x06,0x40,0x06,0x10,0x00,0xc8,0x01],  # 2mm
}

def pad_packet(data: list) -> bytes:
    """Pad packet to REPORT_SIZE bytes."""
    buf = bytearray(REPORT_SIZE)
    buf[:len(data)] = data
    return bytes(buf)

# ─── MOUSE DEVICE ────────────────────────────────────────────────────────────

class BeastXDevice:
    def __init__(self):
        self._dev = None

    def find(self):
        """Return True if device is found (plugged in)."""
        for info in hid.enumerate(VID, PID):
            # On some systems there are multiple HID interfaces.
            # The config interface is usually usage_page=0xFF00 or interface 1.
            if info.get('usage_page', 0) == 0xFF00 or info.get('interface_number', -1) == 1:
                return info
            # Fallback: return first match
        devs = hid.enumerate(VID, PID)
        return devs[0] if devs else None

    def connect(self):
        info = self.find()
        if not info:
            raise RuntimeError("Beast X not found. Make sure it's plugged in via USB.")
        self._dev = hid.device()
        self._dev.open_path(info['path'])
        self._dev.set_nonblocking(1)
        return True

    def disconnect(self):
        if self._dev:
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None

    @property
    def connected(self):
        return self._dev is not None

    def send(self, packet: list):
        if not self._dev:
            raise RuntimeError("Not connected")
        buf = pad_packet(packet)
        # hidapi write: prepend report ID 0x00 on some platforms
        result = self._dev.write(bytes([0x00]) + buf)
        if result < 0:
            raise RuntimeError(f"Write failed: {self._dev.error()}")
        return result

    def set_poll_rate(self, hz: int):
        if hz not in POLL_PACKETS:
            raise ValueError(f"Invalid polling rate: {hz}")
        self.send(POLL_PACKETS[hz])

    def set_lod(self, lod: int):
        if lod not in LOD_PACKETS:
            raise ValueError(f"Invalid LOD: {lod}")
        self.send(LOD_PACKETS[lod])

# ─── CONFIG PERSISTENCE ───────────────────────────────────────────────────────

CONFIG_PATH = Path.home() / ".config" / "beastx" / "config.json"

DEFAULT_CONFIG = {
    "dpi_profiles": [400, 800, 1600, 3200],
    "active_dpi": 1,
    "poll_rate": 1000,
    "lod": 0,
}

def load_config():
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                data = json.load(f)
                # merge with defaults to handle missing keys
                merged = dict(DEFAULT_CONFIG)
                merged.update(data)
                return merged
    except Exception:
        pass
    return dict(DEFAULT_CONFIG)

def save_config(cfg: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

# ─── THEME ───────────────────────────────────────────────────────────────────

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

BG       = "#0d0d0f"
BG1      = "#141416"
BG2      = "#1c1c20"
BG3      = "#242428"
LINE     = "#2a2a30"
TEXT     = "#e8e8ec"
DIM      = "#6a6a78"
ACCENT   = "#c8ff57"
ACCENTBG = "#1a2208"
RED      = "#ff5757"
WHITE    = "#ffffff"

FONT_TITLE  = ("Courier New", 22, "bold")
FONT_LABEL  = ("Courier New", 11)
FONT_SMALL  = ("Courier New", 10)
FONT_MONO   = ("Courier New", 10)
FONT_BIG    = ("Courier New", 28, "bold")

# ─── APP ─────────────────────────────────────────────────────────────────────

class BeastXApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Beast X Config")
        self.geometry("860x560")
        self.minsize(760, 480)
        self.configure(fg_color=BG)
        self.resizable(True, True)

        self.device = BeastXDevice()
        self.config = load_config()
        self._toast_job = None
        self._auto_poll_job = None

        self._build_ui()
        self._auto_reconnect()

    # ── UI BUILD ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        # top bar
        self._build_topbar()

        # body: sidebar + content
        body = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self._build_sidebar(body)

        self.content = ctk.CTkFrame(body, fg_color=BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        # pages
        self.pages = {}
        self._build_page_dpi()
        self._build_page_polling()
        self._build_page_lod()
        self._build_page_info()

        self._show_page("dpi")

        # toast label (overlay)
        self.toast_label = ctk.CTkLabel(
            self, text="", fg_color=BG2,
            text_color=ACCENT, corner_radius=8,
            font=FONT_SMALL, padx=14, pady=8
        )

    def _build_topbar(self):
        bar = ctk.CTkFrame(self, fg_color=BG1, height=52, corner_radius=0)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        title = ctk.CTkLabel(bar, text="  ⬡  Beast X", font=("Courier New", 15, "bold"),
                             text_color=TEXT)
        title.pack(side="left", padx=20)

        self.conn_btn = ctk.CTkButton(
            bar, text="Connect", width=110, height=32,
            fg_color=ACCENT, text_color="#000000",
            hover_color="#aee838", font=("Courier New", 11, "bold"),
            corner_radius=7, command=self._toggle_connect
        )
        self.conn_btn.pack(side="right", padx=16, pady=10)

        self.status_label = ctk.CTkLabel(
            bar, text="● Disconnected", font=FONT_SMALL, text_color=DIM
        )
        self.status_label.pack(side="right", padx=4)

    def _build_sidebar(self, parent):
        sidebar = ctk.CTkFrame(parent, fg_color=BG1, width=190, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        NAV = [
            ("dpi",     "◎  DPI Profiles"),
            ("polling", "⊕  Polling Rate"),
            ("lod",     "⊟  Lift-Off Dist."),
            ("info",    "⊙  Device Info"),
        ]

        ctk.CTkLabel(sidebar, text="CONFIGURE", font=("Courier New", 9),
                     text_color=DIM).pack(anchor="w", padx=18, pady=(18, 6))

        self._nav_btns = {}
        for key, label in NAV:
            btn = ctk.CTkButton(
                sidebar, text=label, anchor="w",
                fg_color="transparent", text_color=DIM,
                hover_color=BG2, font=FONT_LABEL,
                height=36, corner_radius=7,
                command=lambda k=key: self._show_page(k)
            )
            btn.pack(fill="x", padx=10, pady=2)
            self._nav_btns[key] = btn

        # bottom info
        info_frame = ctk.CTkFrame(sidebar, fg_color=BG2, corner_radius=8)
        info_frame.pack(side="bottom", fill="x", padx=10, pady=16)
        ctk.CTkLabel(info_frame, text="WL Mouse Beast X", font=("Courier New", 10, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=12, pady=(10,0))
        ctk.CTkLabel(info_frame, text="PAW3395 · nRF52840", font=FONT_MONO,
                     text_color=DIM).pack(anchor="w", padx=12)
        ctk.CTkLabel(info_frame, text="VID:36A7  PID:A887", font=FONT_MONO,
                     text_color=DIM).pack(anchor="w", padx=12, pady=(0,10))

    # ── PAGES ────────────────────────────────────────────────────────────────

    def _make_page(self, key, title, subtitle):
        frame = ctk.CTkScrollableFrame(self.content, fg_color=BG, corner_radius=0)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_remove()
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text=title, font=FONT_TITLE,
                     text_color=TEXT).grid(row=0, column=0, sticky="w", padx=36, pady=(30,2))
        ctk.CTkLabel(frame, text=subtitle, font=FONT_SMALL,
                     text_color=DIM, wraplength=560, justify="left"
                     ).grid(row=1, column=0, sticky="w", padx=36, pady=(0,20))

        self.pages[key] = frame
        return frame

    def _card(self, parent, row, title=None):
        card = ctk.CTkFrame(parent, fg_color=BG1,
                            border_color=LINE, border_width=1, corner_radius=10)
        card.grid(row=row, column=0, sticky="ew", padx=36, pady=(0, 14))
        card.grid_columnconfigure(0, weight=1)
        if title:
            ctk.CTkLabel(card, text=title, font=("Courier New", 11, "bold"),
                         text_color=TEXT).grid(row=0, column=0, sticky="w", padx=20, pady=(16,8))
        return card

    # ── DPI PAGE ─────────────────────────────────────────────────────────────

    def _build_page_dpi(self):
        page = self._make_page("dpi", "DPI Profiles",
            "Up to 5 profiles. Click a number to activate it. Range: 50 – 26,000 DPI.")

        self.dpi_card = self._card(page, 2, "Profiles")
        self._dpi_rows = []
        self._render_dpi_rows()

    def _render_dpi_rows(self):
        # clear old rows
        for w in self._dpi_rows:
            w.destroy()
        self._dpi_rows = []

        profiles = self.config["dpi_profiles"]
        active   = self.config["active_dpi"]

        for i, dpi in enumerate(profiles):
            row = ctk.CTkFrame(self.dpi_card, fg_color="transparent")
            row.grid(row=i+1, column=0, sticky="ew", padx=16, pady=4)
            row.grid_columnconfigure(1, weight=1)
            self._dpi_rows.append(row)

            # index button (click to activate)
            is_active = (i == active)
            idx_btn = ctk.CTkButton(
                row, text=str(i+1), width=30, height=30,
                fg_color=ACCENTBG if is_active else BG3,
                text_color=ACCENT if is_active else DIM,
                border_color=ACCENT if is_active else LINE,
                border_width=1, hover_color=BG2,
                font=FONT_SMALL, corner_radius=6,
                command=lambda idx=i: self._set_active_dpi(idx)
            )
            idx_btn.grid(row=0, column=0, padx=(0, 12))

            # slider
            var = tk.IntVar(value=dpi)
            val_label = ctk.CTkLabel(row, text=f"{dpi:,} DPI",
                                     font=FONT_MONO, text_color=ACCENT, width=90, anchor="e")
            val_label.grid(row=0, column=2, padx=12)

            slider = ctk.CTkSlider(
                row, from_=50, to=26000, number_of_steps=519,
                variable=var,
                button_color=ACCENT, button_hover_color="#aee838",
                progress_color=ACCENT, fg_color=BG3,
                command=lambda v, lbl=val_label, idx=i: self._dpi_slide(v, lbl, idx)
            )
            slider.grid(row=0, column=1, sticky="ew")

            # delete button
            del_btn = ctk.CTkButton(
                row, text="✕", width=28, height=28,
                fg_color="transparent", text_color=DIM,
                border_color=LINE, border_width=1,
                hover_color=BG2, font=FONT_SMALL,
                corner_radius=6,
                command=lambda idx=i: self._del_dpi(idx)
            )
            del_btn.grid(row=0, column=3, padx=(8,0))

        # add profile button
        if len(profiles) < 5:
            add_btn = ctk.CTkButton(
                self.dpi_card, text="+ Add Profile",
                fg_color="transparent", text_color=DIM,
                border_color=LINE, border_width=1,
                hover_color=BG2, font=FONT_SMALL,
                height=34, corner_radius=7,
                command=self._add_dpi
            )
            add_btn.grid(row=len(profiles)+1, column=0,
                         sticky="ew", padx=16, pady=(4,16))
            self._dpi_rows.append(add_btn)
        else:
            # bottom padding
            spacer = ctk.CTkLabel(self.dpi_card, text="", height=12)
            spacer.grid(row=len(profiles)+1, column=0)
            self._dpi_rows.append(spacer)

    def _dpi_slide(self, value, label, idx):
        v = round(float(value) / 50) * 50
        v = max(50, min(26000, v))
        self.config["dpi_profiles"][idx] = v
        label.configure(text=f"{v:,} DPI")
        save_config(self.config)

    def _set_active_dpi(self, idx):
        self.config["active_dpi"] = idx
        save_config(self.config)
        self._render_dpi_rows()
        self.toast(f"Profile {idx+1} active — {self.config['dpi_profiles'][idx]:,} DPI")

    def _add_dpi(self):
        if len(self.config["dpi_profiles"]) >= 5:
            return
        self.config["dpi_profiles"].append(1600)
        save_config(self.config)
        self._render_dpi_rows()

    def _del_dpi(self, idx):
        if len(self.config["dpi_profiles"]) <= 1:
            self.toast("Need at least one profile", ok=False)
            return
        self.config["dpi_profiles"].pop(idx)
        if self.config["active_dpi"] >= len(self.config["dpi_profiles"]):
            self.config["active_dpi"] = len(self.config["dpi_profiles"]) - 1
        save_config(self.config)
        self._render_dpi_rows()

    # ── POLLING PAGE ─────────────────────────────────────────────────────────

    def _build_page_polling(self):
        page = self._make_page("polling", "Polling Rate",
            "How often the mouse reports its position to the PC. Applied to hardware instantly.")

        RATES = [
            (125,  "8ms",     "Power saving"),
            (250,  "4ms",     "Balanced"),
            (500,  "2ms",     "Gaming"),
            (1000, "1ms",     "Standard competitive"),
            (2000, "0.5ms",   "High-performance"),
            (4000, "0.25ms",  "Max — Beast X limit"),
        ]

        card = self._card(page, 2, "Select Rate")
        card.grid_columnconfigure(tuple(range(6)), weight=1)

        self._rate_btns = {}
        for col, (hz, ms, note) in enumerate(RATES):
            is_active = self.config["poll_rate"] == hz
            btn = ctk.CTkButton(
                card, text=f"{hz}\n{ms}",
                fg_color=ACCENTBG if is_active else BG2,
                text_color=ACCENT if is_active else DIM,
                border_color=ACCENT if is_active else LINE,
                border_width=1, hover_color=BG2,
                font=("Courier New", 11, "bold"),
                height=64, corner_radius=8,
                command=lambda h=hz, n=note: self._set_poll(h, n)
            )
            btn.grid(row=1, column=col, padx=5, pady=(0,4), sticky="ew")
            self._rate_btns[hz] = (btn, note)

        self._rate_note = ctk.CTkLabel(
            card, text=self._rate_btns[self.config["poll_rate"]][1],
            font=FONT_SMALL, text_color=DIM
        )
        self._rate_note.grid(row=2, column=0, columnspan=6,
                             sticky="w", padx=20, pady=(4, 16))

    def _set_poll(self, hz, note):
        self.config["poll_rate"] = hz
        save_config(self.config)
        # update button states
        for h, (btn, n) in self._rate_btns.items():
            active = (h == hz)
            btn.configure(
                fg_color=ACCENTBG if active else BG2,
                text_color=ACCENT if active else DIM,
                border_color=ACCENT if active else LINE,
            )
        self._rate_note.configure(text=note)
        # send to hardware
        self._send(lambda: self.device.set_poll_rate(hz),
                   f"Polling rate → {hz} Hz")

    # ── LOD PAGE ─────────────────────────────────────────────────────────────

    def _build_page_lod(self):
        page = self._make_page("lod", "Lift-Off Distance",
            "How high you can lift the mouse before tracking stops. Applied instantly.")

        card = self._card(page, 2, "Select Distance")
        card.grid_columnconfigure((0, 1), weight=1)

        self._lod_btns = {}
        options = [
            (0, "1mm", "Low · Competitive",
             "Tracking stops almost immediately.\nBest for low-sens on hard pads."),
            (1, "2mm", "Standard",
             "More forgiving on soft or textured\npads. Good for most players."),
        ]
        for col, (val, size, label, desc) in enumerate(options):
            is_active = self.config["lod"] == val
            frame = ctk.CTkFrame(
                card,
                fg_color=ACCENTBG if is_active else BG2,
                border_color=ACCENT if is_active else LINE,
                border_width=1, corner_radius=9
            )
            frame.grid(row=1, column=col, padx=(16 if col==0 else 6, 6 if col==0 else 16),
                       pady=(0,16), sticky="nsew")
            frame.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(frame, text=size,
                         font=("Courier New", 32, "bold"),
                         text_color=ACCENT if is_active else DIM
                         ).pack(pady=(20, 2))
            ctk.CTkLabel(frame, text=label,
                         font=("Courier New", 10, "bold"),
                         text_color=TEXT if is_active else DIM
                         ).pack()
            ctk.CTkLabel(frame, text=desc,
                         font=FONT_SMALL, text_color=DIM,
                         justify="center"
                         ).pack(pady=(6, 16), padx=12)

            # invisible click target
            frame.bind("<Button-1>", lambda e, v=val: self._set_lod(v))
            for child in frame.winfo_children():
                child.bind("<Button-1>", lambda e, v=val: self._set_lod(v))

            self._lod_btns[val] = frame

    def _set_lod(self, val):
        self.config["lod"] = val
        save_config(self.config)
        # rebuild lod page to refresh styles
        self.pages["lod"].destroy()
        del self.pages["lod"]
        self._build_page_lod()
        self._show_page("lod")
        self._send(lambda: self.device.set_lod(val),
                   f"Lift-off → {'1mm' if val == 0 else '2mm'}")

    # ── INFO PAGE ────────────────────────────────────────────────────────────

    def _build_page_info(self):
        page = self._make_page("info", "Device Info", "Current configuration overview.")

        card = self._card(page, 2, "Configuration")
        card.grid_columnconfigure((0,1,2), weight=1)

        self._info_labels = {}
        tiles = [
            ("active_dpi", "Active DPI", lambda: f"{self.config['dpi_profiles'][self.config['active_dpi']]:,}"),
            ("poll_rate",  "Polling",    lambda: f"{self.config['poll_rate']} Hz"),
            ("lod",        "Lift-Off",   lambda: "1mm" if self.config['lod']==0 else "2mm"),
        ]
        for col, (key, label, getter) in enumerate(tiles):
            f = ctk.CTkFrame(card, fg_color=BG2, corner_radius=8)
            f.grid(row=1, column=col, padx=(16 if col==0 else 6, 6 if col==2 else 6),
                   pady=(0,16), sticky="ew")
            val = ctk.CTkLabel(f, text=getter(),
                               font=("Courier New", 20, "bold"), text_color=ACCENT)
            val.pack(pady=(14,2))
            ctk.CTkLabel(f, text=label, font=FONT_SMALL, text_color=DIM).pack(pady=(0,12))
            self._info_labels[key] = (val, getter)

        # hardware info
        hw_card = self._card(page, 3, "Hardware")
        hw_rows = [
            ("Sensor",    "PixArt PAW3395"),
            ("MCU",       "Nordic nRF52840"),
            ("VID:PID",   "36A7:A887"),
            ("Interface", "USB HID"),
            ("Config",    str(CONFIG_PATH)),
        ]
        for r, (k, v) in enumerate(hw_rows):
            ctk.CTkLabel(hw_card, text=k, font=FONT_SMALL,
                         text_color=DIM, anchor="w", width=100
                         ).grid(row=r+1, column=0, sticky="w", padx=20, pady=3)
            ctk.CTkLabel(hw_card, text=v, font=FONT_MONO,
                         text_color=TEXT, anchor="w"
                         ).grid(row=r+1, column=1, sticky="w", padx=8, pady=3)
        ctk.CTkLabel(hw_card, text="", height=8).grid(row=len(hw_rows)+1, column=0)

    def _refresh_info(self):
        if "info" not in self._info_labels:
            return
        for key, (lbl, getter) in self._info_labels.items():
            lbl.configure(text=getter())

    # ── NAVIGATION ───────────────────────────────────────────────────────────

    def _show_page(self, key):
        for k, page in self.pages.items():
            page.grid_remove()
        if key in self.pages:
            self.pages[key].grid()
        for k, btn in self._nav_btns.items():
            active = (k == key)
            btn.configure(
                fg_color=ACCENTBG if active else "transparent",
                text_color=ACCENT if active else DIM,
            )
        if key == "info":
            self._refresh_info()

    # ── CONNECT / DISCONNECT ─────────────────────────────────────────────────

    def _toggle_connect(self):
        if self.device.connected:
            self.device.disconnect()
            self._set_status(False)
        else:
            threading.Thread(target=self._do_connect, daemon=True).start()

    def _do_connect(self):
        try:
            self.device.connect()
            self.after(0, lambda: self._set_status(True))
        except Exception as e:
            self.after(0, lambda: self.toast(str(e), ok=False))

    def _set_status(self, connected: bool):
        if connected:
            self.status_label.configure(text="● Connected", text_color=ACCENT)
            self.conn_btn.configure(text="Disconnect")
            self.toast("Mouse connected")
        else:
            self.status_label.configure(text="● Disconnected", text_color=DIM)
            self.conn_btn.configure(text="Connect")

    def _auto_reconnect(self):
        """Try to silently reconnect on startup."""
        def _try():
            try:
                self.device.connect()
                self.after(0, lambda: self._set_status(True))
            except Exception:
                pass
        threading.Thread(target=_try, daemon=True).start()

    # ── SEND HELPER ──────────────────────────────────────────────────────────

    def _send(self, fn, success_msg: str):
        """Run fn() in a thread, show toast on result."""
        def _run():
            try:
                fn()
                self.after(0, lambda: self.toast(f"✓  {success_msg}"))
            except Exception as e:
                self.after(0, lambda: self.toast(f"✗  {e}", ok=False))
        threading.Thread(target=_run, daemon=True).start()

    # ── TOAST ────────────────────────────────────────────────────────────────

    def toast(self, msg: str, ok: bool = True):
        color = ACCENT if ok else RED
        self.toast_label.configure(text=f"  {msg}  ", text_color=color)
        self.toast_label.place(relx=0.5, rely=0.96, anchor="s")
        self.toast_label.lift()
        if self._toast_job:
            self.after_cancel(self._toast_job)
        self._toast_job = self.after(3000, self.toast_label.place_forget)


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = BeastXApp()
    app.mainloop()
