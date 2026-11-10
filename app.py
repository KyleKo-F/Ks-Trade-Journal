import os
import sys
import shutil
import tempfile
import threading
import time
import calendar
import re
import ctypes
import json
import zipfile
import subprocess
from datetime import datetime, timedelta
from collections import defaultdict
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, ttk, filedialog
from PIL import Image, ImageGrab, ImageDraw, ImageTk
import requests
from tradingview_ta import TA_Handler, Interval

import database as db
import analyzer
import tracker

# Application Versioning & Auto-Updater Configuration
CURRENT_VERSION = "1.0.0"
# Replace YOUR_GITHUB_USERNAME and YOUR_REPO_NAME with your GitHub repository details
UPDATE_CHECK_URL = "https://api.github.com/repos/KyleKo-F/Ks-Trade-Journal/releases/latest"

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Explicitly set AppUserModelID so Windows Taskbar uses the custom icon instead of Python logo
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ks.tradejournal.app.1.0")
except Exception:
    pass

ctk.set_appearance_mode("Dark")

# Global UI scaling by +10%
ctk.set_widget_scaling(1.10)

FOREX_PAIRS_LIST = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD", "USD/CAD", "NZD/USD",
    "EUR/GBP", "EUR/JPY", "EUR/CHF", "EUR/CAD", "EUR/AUD", "EUR/NZD",
    "GBP/JPY", "GBP/CHF", "GBP/CAD", "GBP/AUD", "GBP/NZD",
    "AUD/JPY", "AUD/NZD", "AUD/CAD", "AUD/CHF",
    "NZD/JPY", "NZD/CAD", "NZD/CHF",
    "CAD/JPY", "CAD/CHF", "CHF/JPY",
    "XAU/USD (Gold)", "BTC/USD (Crypto)", "ETH/USD (Crypto)"
]

# Pre-parse Forex currency pairs once to optimize background updates
PARSED_FOREX_PAIRS = []
for pair in FOREX_PAIRS_LIST:
    clean_p = pair.split()[0].strip()
    if "/" in clean_p:
        parts = clean_p.split("/")
        PARSED_FOREX_PAIRS.append((clean_p, parts[0].upper().strip(), parts[1].upper().strip()))

RE_MARKDOWN_LINK = re.compile(r'\[([^\]]+)\]\([^\)]+\)')

TV_SYMBOL_MAP = {
    "EUR/USD": ("EURUSD", "FX", "forex"),
    "GBP/USD": ("GBPUSD", "FX", "forex"),
    "USD/JPY": ("USDJPY", "FX", "forex"),
    "USD/CHF": ("USDCHF", "FX", "forex"),
    "AUD/USD": ("AUDUSD", "FX", "forex"),
    "USD/CAD": ("USDCAD", "FX", "forex"),
    "NZD/USD": ("NZDUSD", "FX", "forex"),
    "EUR/GBP": ("EURGBP", "FX", "forex"),
    "EUR/JPY": ("EURJPY", "FX", "forex"),
    "EUR/CHF": ("EURCHF", "FX", "forex"),
    "EUR/CAD": ("EURCAD", "FX", "forex"),
    "EUR/AUD": ("EURAUD", "FX", "forex"),
    "EUR/NZD": ("EURNZD", "FX", "forex"),
    "GBP/JPY": ("GBPJPY", "FX", "forex"),
    "GBP/CHF": ("GBPCHF", "FX", "forex"),
    "GBP/CAD": ("GBPCAD", "FX", "forex"),
    "GBP/AUD": ("GBPAUD", "FX", "forex"),
    "GBP/NZD": ("GBPNZD", "FX", "forex"),
    "AUD/JPY": ("AUDJPY", "FX", "forex"),
    "AUD/NZD": ("AUDNZD", "FX", "forex"),
    "AUD/CAD": ("AUDCAD", "FX", "forex"),
    "AUD/CHF": ("AUDCHF", "FX", "forex"),
    "NZD/JPY": ("NZDJPY", "FX", "forex"),
    "NZD/CAD": ("NZDCAD", "FX", "forex"),
    "NZD/CHF": ("NZDCHF", "FX", "forex"),
    "CAD/JPY": ("CADJPY", "FX", "forex"),
    "CAD/CHF": ("CADCHF", "FX", "forex"),
    "CHF/JPY": ("CHFJPY", "FX", "forex"),
    "XAU/USD (Gold)": ("GOLD", "TVC", "cfd"),
    "BTC/USD (Crypto)": ("BTCUSD", "BITSTAMP", "crypto"),
    "ETH/USD (Crypto)": ("ETHUSD", "BITSTAMP", "crypto")
}

TRADE_TYPE_CHECKLISTS = {
    "HnS": [
        ("Higher Timeframe Trend Direction", "Ensure 4H/1D structural bias is strictly bearish or rejecting a macro supply zone."),
        ("Economic News Clearance", "Check economic calendar to ensure no high-impact red-folder news (CPI, NFP, FOMC) is imminent."),
        ("Left & Right Shoulder Symmetry", "Clear left shoulder, higher head peak, and proportional right shoulder structure form."),
        ("Neckline Break & Retest", "Price closed below the neckline support and retested it as fresh resistance with rejection wicks."),
        ("Risk/Reward & Position Size", "Stop loss positioned above right shoulder peak with a minimum 1:2 R:R ratio targeting head depth.")
    ],
    "i HnS": [
        ("Higher Timeframe Trend Direction", "Verify higher timeframe (4H/1D) structural bias is bullish or bouncing from macro demand."),
        ("Economic News Clearance", "Check economic calendar to ensure no high-impact red-folder news (CPI, NFP, FOMC) is imminent."),
        ("Inverted Structure Validation", "Left shoulder low, deeper head low, and higher right shoulder low are clearly defined."),
        ("Neckline Breach & Retest", "Price broke above resistance neckline and held former resistance as new support with rejection."),
        ("Risk/Reward & Position Size", "Stop loss placed safely below right shoulder low with at least a 1:2 R:R ratio.")
    ],
    "FVG": [
        ("Higher Timeframe Trend Direction", "Confirm trade direction aligns with HTF order flow bias (4H/1D market structure)."),
        ("Economic News Clearance", "Check economic calendar to ensure no high-impact red-folder news (CPI, NFP, FOMC) is imminent."),
        ("3-Candle Imbalance Gap", "Clear Fair Value Gap created by strong displacement leaving unmitigated space between Candle 1 & 3."),
        ("Mitigation & Liquidity Sweep", "Price tapped into the FVG (50% CE level) after sweeping external liquidity / session highs or lows."),
        ("Lower Timeframe Confirmation", "1m/5m Market Structure Shift (MSS) confirmed inside FVG with defined SL (min 1:2 R:R).")
    ],
    "S & R": [
        ("Higher Timeframe Trend Direction", "Align level play with overall HTF trend (buying strong HTF support or shorting HTF resistance)."),
        ("Economic News Clearance", "Check economic calendar to ensure no high-impact red-folder news (CPI, NFP, FOMC) is imminent."),
        ("Multi-Touch Key Level", "Support/Resistance level verified by at least 2 historical touches or HTF key level alignment."),
        ("Rejection Candle Signal", "Clear pinbar, engulfing candle, or strong rejection wick forming directly at the level."),
        ("Risk & Reward Allocation", "Clean traffic to target with SL placed beyond rejection wick tip (minimum 1:2 R:R).")
    ],
    "Breakout": [
        ("Higher Timeframe Trend Direction", "Confirm breakout direction is aligned with macro HTF momentum and market structure."),
        ("Economic News Clearance", "Check economic calendar to ensure no high-impact red-folder news (CPI, NFP, FOMC) is imminent."),
        ("Consolidation Squeeze", "Price compressed within a tight range, flag, or triangle structure before expanding."),
        ("Volume & Momentum Close", "Breakout candle shows noticeable body expansion with a full candle close past range boundary."),
        ("Risk Management Check", "Stop loss placed safely back inside the range with calculated lot size for minimum 1:2 R:R.")
    ]
}

def clean_pair(pair_str):
    if not pair_str:
        return ""
    s = str(pair_str).strip().upper()
    if len(s) == 6 and s.isalpha() and "/" not in s:
        return f"{s[:3]}/{s[3:]}"
    return s

def clean_direction(direction_str):
    if not direction_str:
        return "BUY"
    val = str(direction_str).strip().upper()
    if val in ["LONG", "BUY"]:
        return "BUY"
    elif val in ["SHORT", "SELL"]:
        return "SELL"
    return val

def clean_status(status_str):
    if not status_str:
        return "OPEN"
    val = str(status_str).strip().upper()
    if val in ["WIN", "TP"]:
        return "TP"
    elif val in ["LOSS", "SL"]:
        return "SL"
    return "OPEN" if val not in ["TP", "SL", "OPEN"] else val

def format_timeframe(tf_str):
    if not tf_str:
        return ""
    s = str(tf_str).strip()
    if s.isdigit():
        return f"{s}m"
    return s

def parse_news_event(ev):
    """ Fast helper to parse raw economic event dictionaries """
    title = ev.get("title", ev.get("name", ev.get("event", "")))
    if not title:
        return None

    raw_date_str = str(ev.get("date", ev.get("dateUtc", "")))
    country = str(ev.get("country", ev.get("currency", ev.get("countryCode", "")))).upper()
    impact = str(ev.get("impact", ev.get("volatility", "")))
    actual = str(ev.get("actual", ""))
    forecast = str(ev.get("forecast", ""))
    previous = str(ev.get("previous", ""))

    ev_dt = None
    if raw_date_str:
        try:
            ev_dt = datetime.fromisoformat(raw_date_str)
            if ev_dt.tzinfo is not None:
                ev_dt = ev_dt.astimezone()
        except Exception:
            clean_str = raw_date_str.split("+")[0].split(".")[0]
            if len(clean_str) > 19:
                clean_str = clean_str[:19]
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    ev_dt = datetime.strptime(clean_str, fmt)
                    break
                except ValueError:
                    pass

    time_formatted = "N/A"
    if ev_dt:
        raw_time = ev_dt.strftime("%I:%M%p").lower()
        time_formatted = raw_time.lstrip("0") if raw_time.startswith("0") else raw_time

    return {
        "date": ev_dt.strftime("%a %b %d") if ev_dt else "N/A",
        "time": time_formatted,
        "currency": country,
        "impact": impact,
        "title": title,
        "actual": actual,
        "forecast": forecast,
        "previous": previous,
        "dt": ev_dt
    }

class CustomDropdownButton(ctk.CTkFrame):
    def __init__(self, parent, options, default_val, app_instance, width=None, height=29, command_callback=None, is_searchable=False, enable_favorites=False, custom_max_h=None):
        super().__init__(
            parent,
            fg_color="#0d1117",
            border_color="#30363d",
            border_width=1,
            corner_radius=6,
            height=height,
            cursor="hand2"
        )
        if width:
            self.configure(width=width)

        self.app_instance = app_instance
        self.options = list(options)
        self.selected_value = default_val
        self.command_callback = command_callback
        self.is_searchable = is_searchable
        self.enable_favorites = enable_favorites
        self.custom_max_h = custom_max_h

        self.lbl_text = tk.Label(
            self,
            text=default_val,
            fg="#f0f6fc",
            bg="#0d1117",
            font=("Segoe UI", 10, "bold"),
            anchor="w"
        )
        self.lbl_text.place(relx=0.0, rely=0.5, anchor="w", x=10)

        self.lbl_arrow = tk.Label(
            self,
            text="∨",
            fg="#f0f6fc",
            bg="#0d1117",
            font=("Segoe UI", 10, "bold"),
            anchor="e"
        )
        self.lbl_arrow.place(relx=1.0, rely=0.5, anchor="e", x=-10)

        self._bind_events(self)

    def _bind_events(self, widget):
        widget.bind("<Button-1>", self.toggle)
        widget.bind("<Enter>", lambda e: self.on_hover(True))
        widget.bind("<Leave>", lambda e: self.on_hover(False))
        for child in widget.winfo_children():
            self._bind_events(child)

    def on_hover(self, hovering):
        color = "#21262d" if hovering else "#0d1117"
        self.configure(fg_color=color)
        self.lbl_text.configure(bg=color)
        self.lbl_arrow.configure(bg=color)

    def toggle(self, event=None):
        self.app_instance.show_custom_popup_menu(
            self, 
            self.options, 
            self.command_callback,
            is_searchable=self.is_searchable,
            enable_favorites=self.enable_favorites,
            custom_max_h=self.custom_max_h
        )
        return "break"

    def set(self, val):
        self.selected_value = val
        self.lbl_text.configure(text=val)

    def get(self):
        return self.selected_value

    def update_options(self, new_options):
        self.options = list(new_options)

class TradingJournalApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"K's Trade Journal v{CURRENT_VERSION}")
        
        # Load custom icon if present using dynamic resource path
        icon_file = resource_path("icon.ico")
        if os.path.exists(icon_file):
            self.iconbitmap(icon_file)
        
        self.geometry("1600x900")
        self.minsize(1500, 800)
        self.configure(fg_color="#0d1117")

        db.init_db()
        
        self.saved_images_dir = os.path.join(os.path.expanduser("~"), ".trade_journal_images")
        os.makedirs(self.saved_images_dir, exist_ok=True)

        self.selected_image_path = None
        self.current_preview_image = None
        self.nav_buttons = {}
        self.current_active_view = None
        self.is_animating = False
        self.active_dropdown_window = None
        self.favorite_pairs = set()
        self.cached_news_events = []

        self.current_year = datetime.now().year
        self.current_month = datetime.now().month

        # Save calc settings on window close
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Layout Grid: [Sidebar | Main View]
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.setup_table_styles()
        self.build_sidebar()
        
        self.main_container = ctk.CTkFrame(self, fg_color="#0d1117", corner_radius=0)
        self.main_container.grid(row=0, column=1, sticky="nsew", padx=12, pady=12)
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)

        # Content Area Stack
        self.content_area = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.content_area.grid(row=0, column=0, sticky="nsew")
        self.content_area.grid_rowconfigure(0, weight=1)
        self.content_area.grid_columnconfigure(0, weight=1)

        # Pre-mounted Views Layer
        self.view_dashboard = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.view_calendar = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.view_news = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.view_trades = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.view_calculator = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.view_analytics = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.view_checklist = ctk.CTkFrame(self.content_area, fg_color="transparent")

        for view_frame in (self.view_dashboard, self.view_calendar, self.view_news, self.view_trades, self.view_calculator, self.view_analytics, self.view_checklist):
            view_frame.grid(row=0, column=0, sticky="nsew")

        # Smooth Fade Transition Overlay Layer
        self.fade_overlay = ctk.CTkFrame(self.content_area, fg_color="#0d1117", corner_radius=0)
        self.fade_overlay.grid(row=0, column=0, sticky="nsew")
        self.fade_overlay.grid_remove()

        self.build_dashboard_view()
        self.build_calendar_view()
        self.build_news_view()
        self.build_trades_view()
        self.build_calculator_view()
        self.build_analytics_view()
        self.build_checklist_view()

        self.show_view("Dashboard", animate=False)
        self.load_database_records()
        self.fetch_and_render_news()

        # Context Menu for Recent Trades
        self.dash_context_menu = tk.Menu(self, tearoff=0, background="#161b22", foreground="#f0f6fc", activebackground="#21262d", activeforeground="#00e6a8", borderwidth=1, font=("Segoe UI", 10))
        self.dash_context_menu.add_command(label="✏️ Modify Trade", command=self.modify_selected_trade)

        # Context Menu for Trades View
        self.trades_context_menu = tk.Menu(self, tearoff=0, background="#161b22", foreground="#f0f6fc", activebackground="#21262d", activeforeground="#00e6a8", borderwidth=1, font=("Segoe UI", 10))
        self.trades_context_menu.add_command(label="✏️ Modify Trade", command=self.modify_selected_trade)
        self.trades_context_menu.add_command(label="🗑️ Delete Trade(s)", command=self.delete_selected)

        self.bind("<Button-1>", self.on_global_click, add="+")
        self.start_background_tracker()

        # Check for updates silently on startup
        self.check_for_updates(silent=True)

    # ------------------ AUTO-UPDATER SYSTEM ------------------ #
    def check_for_updates(self, silent=True):
        def worker():
            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                res = requests.get(UPDATE_CHECK_URL, headers=headers, timeout=6)
                if res.status_code == 200:
                    data = res.json()
                    latest_tag = str(data.get("tag_name", "")).lstrip("v").strip()
                    assets = data.get("assets", [])
                    download_url = None

                    for asset in assets:
                        if asset.get("name", "").endswith(".exe"):
                            download_url = asset.get("browser_download_url")
                            break

                    if not download_url and assets:
                        download_url = assets[0].get("browser_download_url")

                    if latest_tag and download_url and self._is_newer_version(latest_tag, CURRENT_VERSION):
                        if self.winfo_exists():
                            self.after(0, lambda: self.prompt_update(latest_tag, download_url))
                    elif not silent and self.winfo_exists():
                        self.after(0, lambda: messagebox.showinfo("Auto Update", f"You are running the latest version (v{CURRENT_VERSION})."))
                elif not silent and self.winfo_exists():
                    self.after(0, lambda: messagebox.showerror("Update Check Failed", f"Unable to connect to update server (Status {res.status_code})."))
            except Exception as e:
                if not silent and self.winfo_exists():
                    self.after(0, lambda: messagebox.showerror("Update Error", f"Failed to check for updates: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def _is_newer_version(self, latest, current):
        try:
            l_parts = [int(x) for x in latest.split(".")]
            c_parts = [int(x) for x in current.split(".")]
            return l_parts > c_parts
        except Exception:
            return latest > current

    def prompt_update(self, latest_tag, download_url):
        if messagebox.askyesno("Update Available", f"A new version (v{latest_tag}) is available!\nYour current version is v{CURRENT_VERSION}.\n\nWould you like to download and install the update now?"):
            self.download_and_apply_update(download_url)

    def download_and_apply_update(self, download_url):
        progress_win = ctk.CTkToplevel(self)
        progress_win.title("Downloading Update...")
        progress_win.geometry("380x140")
        progress_win.configure(fg_color="#0d1117")
        progress_win.transient(self)
        progress_win.focus_force()

        lbl = ctk.CTkLabel(progress_win, text="Downloading latest version, please wait...", font=ctk.CTkFont(size=13, weight="bold"), text_color="#f0f6fc")
        lbl.pack(pady=(20, 10))

        bar = ctk.CTkProgressBar(progress_win, progress_color="#00e6a8", fg_color="#21262d", height=10)
        bar.pack(fill="x", padx=20, pady=10)
        bar.set(0)

        def download_worker():
            try:
                res = requests.get(download_url, stream=True, timeout=30)
                total_len = int(res.headers.get('content-length', 0))
                temp_dir = tempfile.gettempdir()
                temp_exe = os.path.join(temp_dir, "ks_trade_journal_update.exe")

                downloaded = 0
                with open(temp_exe, "wb") as f:
                    for chunk in res.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_len > 0 and self.winfo_exists():
                                self.after(0, lambda p=(downloaded / total_len): bar.set(p))

                current_exe = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)

                # Generate detached Windows batch installer to replace active executable and restart app
                bat_script = os.path.join(temp_dir, "update_installer.bat")
                with open(bat_script, "w", encoding="utf-8") as f:
                    f.write(f'''@echo off
timeout /t 2 /nobreak > nul
copy /y "{temp_exe}" "{current_exe}"
start "" "{current_exe}"
del "{temp_exe}"
del "%~f0"
''')

                subprocess.Popen(["cmd.exe", "/c", bat_script], creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                
                if self.winfo_exists():
                    self.after(0, self.on_closing)

            except Exception as e:
                if self.winfo_exists():
                    self.after(0, lambda: messagebox.showerror("Update Error", f"Failed to download update: {e}"))
                    self.after(0, progress_win.destroy)

        threading.Thread(target=download_worker, daemon=True).start()

    def on_closing(self):
        self.save_calc_settings()
        self.destroy()

    def get_settings_file_path(self):
        return os.path.join(os.path.expanduser("~"), ".trade_journal_calc_settings.json")

    def load_calc_settings(self):
        path = self.get_settings_file_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("balance", "10000"), data.get("risk", "1.0"), data.get("mode", "Risk %")
            except Exception as e:
                print(f"Error loading calc settings: {e}")
        return "10000", "1.0", "Risk %"

    def save_calc_settings(self, event=None):
        try:
            data = {
                "balance": self.calc_balance_entry.get() if hasattr(self, "calc_balance_entry") else "10000",
                "risk": self.calc_risk_entry.get() if hasattr(self, "calc_risk_entry") else "1.0",
                "mode": self.calc_risk_mode_var if hasattr(self, "calc_risk_mode_var") else "Risk %"
            }
            with open(self.get_settings_file_path(), "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Error saving calc settings: {e}")

    def _create_circle_icon(self, color_hex, size=14):
        """ Creates a 14px pixel circle icon """
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((0, 0, size - 1, size - 1), fill=color_hex)
        return ImageTk.PhotoImage(img)

    def setup_table_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.layout("Treeview", [('Treeview.treearea', {'sticky': 'nswe'})])

        style.configure(
            "Treeview",
            background="#0d1117",
            foreground="#f0f6fc",
            fieldbackground="#0d1117",
            bordercolor="#0d1117",
            borderwidth=0,
            rowheight=35,
            font=("Segoe UI", 11)
        )

        style.configure(
            "Treeview.Heading",
            background="#161b22",
            foreground="#8b949e",
            bordercolor="#0d1117",
            borderwidth=0,
            relief="flat",
            padding=(6, 7),
            font=("Segoe UI", 10, "bold")
        )

        style.map(
            "Treeview.Heading",
            background=[("active", "#21262d"), ("pressed", "#30363d")],
            foreground=[("active", "#f0f6fc")]
        )

        style.map(
            "Treeview",
            background=[("selected", "#1f6beb")],
            foreground=[("selected", "#ffffff")]
        )

        # Custom Dark Scrollbar styling for dropdowns
        style.configure(
            "Dark.Vertical.TScrollbar",
            background="#21262d",
            troughcolor="#161b22",
            bordercolor="#161b22",
            arrowcolor="#8b949e",
            relief="flat",
            borderwidth=0
        )
        style.map(
            "Dark.Vertical.TScrollbar",
            background=[("active", "#30363d"), ("pressed", "#00e6a8")]
        )

    def show_custom_popup_menu(self, target_btn, options, callback=None, is_searchable=False, enable_favorites=False, custom_max_h=None):
        if self.active_dropdown_window and self.active_dropdown_window.winfo_exists():
            prev_target = getattr(self.active_dropdown_window, "target_btn", None)
            self.close_dropdown()
            if prev_target == target_btn:
                return

        win = tk.Toplevel(self)
        win.overrideredirect(True)
        win.configure(bg="#30363d")
        win.target_btn = target_btn
        self.active_dropdown_window = win

        # Force window update to get precise button position
        target_btn.update_idletasks()
        x = target_btn.winfo_rootx()
        y = target_btn.winfo_rooty() + target_btn.winfo_height() + 2
        w = max(target_btn.winfo_width(), 240 if (is_searchable or enable_favorites) else 175)

        search_height = 40 if is_searchable else 0

        frame = tk.Frame(win, bg="#161b22", highlightbackground="#30363d", highlightthickness=1)
        frame.pack(fill="both", expand=True)

        search_var = tk.StringVar() if is_searchable else None

        canvas = tk.Canvas(frame, bg="#161b22", highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview, style="Dark.Vertical.TScrollbar")
        scroll_content = tk.Frame(canvas, bg="#161b22")

        def _on_mousewheel(event):
            if canvas.winfo_exists():
                if event.delta:
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                elif event.num == 4:
                    canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    canvas.yview_scroll(1, "units")

        def _bind_mw(w_item):
            w_item.bind("<MouseWheel>", _on_mousewheel)
            w_item.bind("<Button-4>", _on_mousewheel)
            w_item.bind("<Button-5>", _on_mousewheel)

        _bind_mw(win)
        _bind_mw(frame)
        _bind_mw(canvas)
        _bind_mw(scroll_content)

        if is_searchable:
            search_frame = tk.Frame(frame, bg="#0d1117", highlightbackground="#30363d", highlightthickness=1)
            search_frame.pack(fill="x", padx=6, pady=(6, 4))
            _bind_mw(search_frame)

            lbl_icon = tk.Label(search_frame, text="🔍", bg="#0d1117", fg="#8b949e", font=("Segoe UI", 10))
            lbl_icon.pack(side="left", padx=(6, 2))
            _bind_mw(lbl_icon)

            search_entry = tk.Entry(
                search_frame, 
                textvariable=search_var, 
                bg="#0d1117", 
                fg="#f0f6fc", 
                insertbackground="#00e6a8", 
                relief="flat", 
                font=("Segoe UI", 11)
            )
            search_entry.pack(side="left", fill="x", expand=True, padx=4, pady=4)
            search_entry.focus_set()
            _bind_mw(search_entry)

        canvas_window = canvas.create_window((0, 0), window=scroll_content, anchor="nw")
        
        def on_canvas_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=event.width)

        canvas.bind("<Configure>", on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=(0, 2), pady=2)
        scrollbar.pack(side="right", fill="y", pady=2)

        def render_items(filter_text=""):
            for child in scroll_content.winfo_children():
                child.destroy()

            query = filter_text.strip().lower()
            filtered = [opt for opt in options if query in opt.lower()]

            if enable_favorites:
                favs = [opt for opt in filtered if opt in self.favorite_pairs]
                non_favs = [opt for opt in filtered if opt not in self.favorite_pairs]
                display_options = favs + non_favs
            else:
                display_options = filtered

            if not display_options:
                no_res = tk.Label(scroll_content, text="No items match search", bg="#161b22", fg="#8b949e", font=("Segoe UI", 10, "italic"), pady=8)
                no_res.pack(fill="x")
                _bind_mw(no_res)
                return

            for opt in display_options:
                row_frame = tk.Frame(scroll_content, bg="#161b22", cursor="hand2")
                row_frame.pack(fill="x", expand=True)
                _bind_mw(row_frame)

                is_fav = opt in self.favorite_pairs if enable_favorites else False

                def on_row_enter(e, rf=row_frame):
                    rf.configure(bg="#21262d")
                    for c in rf.winfo_children():
                        c.configure(bg="#21262d")

                def on_row_leave(e, rf=row_frame):
                    rf.configure(bg="#161b22")
                    for c in rf.winfo_children():
                        c.configure(bg="#161b22")

                row_frame.bind("<Enter>", on_row_enter)
                row_frame.bind("<Leave>", on_row_leave)
                row_frame.bind("<Button-1>", lambda e, val=opt: self._select_custom_popup_option(target_btn, val, callback))

                if enable_favorites:
                    star_symbol = "★" if is_fav else "☆"
                    star_color = "#f59e0b" if is_fav else "#6b7280"

                    star_btn = tk.Button(
                        row_frame,
                        text=star_symbol,
                        bg="#161b22",
                        fg=star_color,
                        activebackground="#21262d",
                        activeforeground="#f59e0b",
                        relief="flat",
                        padx=10,
                        pady=4,
                        font=("Segoe UI", 12, "bold"),
                        cursor="hand2"
                    )
                    star_btn.pack(side="right", fill="y")
                    star_btn.bind("<Enter>", on_row_enter)
                    star_btn.bind("<Leave>", on_row_leave)
                    _bind_mw(star_btn)

                    def toggle_fav(e, val=opt):
                        if val in self.favorite_pairs:
                            self.favorite_pairs.remove(val)
                        else:
                            self.favorite_pairs.add(val)
                        render_items(search_var.get() if search_var else "")
                        return "break"

                    star_btn.bind("<Button-1>", toggle_fav)

                item_btn = tk.Button(
                    row_frame,
                    text=opt,
                    bg="#161b22",
                    fg="#f0f6fc",
                    activebackground="#21262d",
                    activeforeground="#00e6a8",
                    relief="flat",
                    anchor="w",
                    padx=10,
                    pady=4,
                    font=("Segoe UI", 11),
                    cursor="hand2",
                    command=lambda val=opt: self._select_custom_popup_option(target_btn, val, callback)
                )
                item_btn.pack(side="left", fill="both", expand=True)
                item_btn.bind("<Enter>", on_row_enter)
                item_btn.bind("<Leave>", on_row_leave)
                _bind_mw(item_btn)

        if is_searchable:
            search_var.trace_add("write", lambda *args: render_items(search_var.get()))

        render_items()

        # Safe scaling lookup
        try:
            scale_factor = ctk.ScalingTracker.get_widget_scaling(self)
        except Exception:
            scale_factor = 1.10

        item_height = int(35 * scale_factor)
        padding_offset = int(14 * scale_factor)
        calculated_h = len(options) * item_height + padding_offset + search_height
        
        if custom_max_h:
            max_limit = int(custom_max_h * scale_factor)
        else:
            max_limit = int(350 * scale_factor) if is_searchable else int(400 * scale_factor)
        total_h = min(calculated_h, max_limit)

        win.geometry(f"{w}x{total_h}+{x}+{y}")

    def _select_custom_popup_option(self, btn, val, callback=None):
        if hasattr(btn, "set"):
            btn.set(val)
        self.close_dropdown()
        if callback:
            callback(val)

    def close_dropdown(self):
        if self.active_dropdown_window and self.active_dropdown_window.winfo_exists():
            self.active_dropdown_window.destroy()
        self.active_dropdown_window = None

    def on_global_click(self, event):
        if self.active_dropdown_window and self.active_dropdown_window.winfo_exists():
            widget = event.widget
            if str(widget).startswith(str(self.active_dropdown_window)):
                return
            target_btn = getattr(self.active_dropdown_window, "target_btn", None)
            if target_btn and (widget == target_btn or str(widget).startswith(str(target_btn))):
                return
            self.close_dropdown()

    def start_background_tracker(self):
        def loop():
            while True:
                try:
                    tracker.check_open_trades()
                    if self.winfo_exists():
                        self.after(0, self.load_database_records)
                    
                    if hasattr(self, "cached_news_events") and self.cached_news_events:
                        now = datetime.now().astimezone()
                        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

                        upcoming = []
                        today_events = []
                        for e in self.cached_news_events:
                            ev_dt = e.get("dt")
                            if ev_dt:
                                comp_dt = ev_dt.replace(tzinfo=now.tzinfo) if (ev_dt.tzinfo is None and now.tzinfo is not None) else ev_dt
                                if (comp_dt + timedelta(minutes=30)) >= now:
                                    upcoming.append(e)
                                if today_start <= comp_dt <= today_end:
                                    today_events.append(e)

                        upcoming.sort(key=lambda x: x["dt"] if x["dt"] else now)
                        if self.winfo_exists():
                            self.after(0, lambda u=upcoming: self.update_dashboard_news_widget(u))
                            self.after(0, lambda t=today_events: self.update_dashboard_no_news_widget(t))
                except Exception as e:
                    print(f"Background Tracker error: {e}")
                time.sleep(60)

        threading.Thread(target=loop, daemon=True).start()

    def build_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=220, fg_color="#161b22", corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(8, weight=1)

        brand_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand_frame.pack(anchor="w", padx=20, pady=(20, 25))

        icon_file = resource_path("icon.ico")
        if os.path.exists(icon_file):
            try:
                pil_icon = Image.open(icon_file)
                self.brand_icon_img = ctk.CTkImage(light_image=pil_icon, dark_image=pil_icon, size=(24, 24))
                lbl_icon = ctk.CTkLabel(brand_frame, image=self.brand_icon_img, text="")
                lbl_icon.pack(side="left", padx=(0, 8))
            except Exception as e:
                print(f"Error loading brand icon: {e}")

        brand_lbl = ctk.CTkLabel(
            brand_frame, 
            text="K's Trade Journal", 
            font=ctk.CTkFont(size=20, weight="bold"), 
            text_color="#00e6a8"
        )
        brand_lbl.pack(side="left")

        nav_items = [
            ("Dashboard", "📊 Dashboard"),
            ("Analytics", "🔍 Analytics"),
            ("News", "📰 Economic News"),
            ("Checklist", "📋 Pre-trade Checklist"),
            ("Trades", "📈 Trades"),
            ("Calendar", "📅 Calendar"),
            ("Calculator", "🧮 Calculator")
        ]

        for key, label_text in nav_items:
            btn = ctk.CTkButton(
                sidebar, 
                text=label_text, 
                anchor="w", 
                fg_color="transparent", 
                hover_color="#21262d",
                text_color="#8b949e",
                height=42,
                font=ctk.CTkFont(size=14),
                command=lambda name=key: self.show_view(name)
            )
            btn.pack(fill="x", padx=10, pady=3)
            self.nav_buttons[key] = btn

    def show_view(self, view_name, animate=True):
        if self.current_active_view == view_name or self.is_animating:
            return

        self.close_dropdown()

        for key, btn in self.nav_buttons.items():
            if key == view_name:
                btn.configure(fg_color="#21262d", text_color="#ffffff", font=ctk.CTkFont(size=14, weight="bold"))
            else:
                btn.configure(fg_color="transparent", text_color="#8b949e", font=ctk.CTkFont(size=14, weight="normal"))

        target_frame = None
        if view_name == "Dashboard":
            target_frame = self.view_dashboard
        elif view_name == "Calendar":
            target_frame = self.view_calendar
            self.render_calendar()
        elif view_name == "News":
            target_frame = self.view_news
            self.fetch_and_render_news()
        elif view_name == "Trades":
            target_frame = self.view_trades
            self.load_database_records()
        elif view_name == "Calculator":
            target_frame = self.view_calculator
        elif view_name == "Analytics":
            target_frame = self.view_analytics
            self.populate_analytics_dropdown()
        elif view_name == "Checklist":
            target_frame = self.view_checklist

        if animate and target_frame:
            self.fade_transition_to_view(target_frame)
        elif target_frame:
            target_frame.tkraise()

        self.current_active_view = view_name

    def fade_transition_to_view(self, target_frame):
        self.is_animating = True
        self.fade_overlay.grid()
        self.fade_overlay.tkraise()

        target_frame.tkraise()
        self.fade_overlay.tkraise()

        def fade_out(step=0):
            if step <= 5:
                color_hex = "#0d1117" if step < 3 else "#12171e"
                self.fade_overlay.configure(fg_color=color_hex)
                self.after(20, lambda: fade_out(step + 1))
            else:
                self.fade_overlay.grid_remove()
                self.is_animating = False

        fade_out()

    # ------------------ DASHBOARD VIEW ------------------ #
    def build_dashboard_view(self):
        self.view_dashboard.grid_rowconfigure(1, weight=1)
        self.view_dashboard.grid_columnconfigure(0, weight=1)

        kpi_frame = ctk.CTkFrame(self.view_dashboard, fg_color="transparent")
        kpi_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        
        kpi_frame.grid_columnconfigure(0, weight=18)
        kpi_frame.grid_columnconfigure(1, weight=18)
        kpi_frame.grid_columnconfigure(2, weight=30)
        kpi_frame.grid_columnconfigure(3, weight=34)
        kpi_frame.grid_rowconfigure(0, weight=1)

        # Stacked WIN RATE & AVG R:R container in Column 0
        stacked_col = ctk.CTkFrame(kpi_frame, fg_color="transparent")
        stacked_col.grid(row=0, column=0, padx=4, sticky="nsew")
        stacked_col.grid_rowconfigure(0, weight=1)
        stacked_col.grid_rowconfigure(1, weight=1)
        stacked_col.grid_columnconfigure(0, weight=1)

        self.card_winrate_val = self.create_kpi_card_stacked(stacked_col, 0, "WIN RATE", "0.0%", "#00e6a8")
        self.card_rr_val = self.create_kpi_card_stacked(stacked_col, 1, "AVG R:R", "1:0.00", "#a855f7")

        self.card_best_trade_val = self.create_kpi_card(kpi_frame, 1, "BEST TRADE TYPE", "N/A", "#38bdf8")
        self.card_news_title, self.card_news_container = self.create_news_kpi_card(kpi_frame, 2)
        self.card_no_news_title, self.card_no_news_container = self.create_no_news_kpi_card(kpi_frame, 3)

        body_frame = ctk.CTkFrame(self.view_dashboard, fg_color="transparent")
        body_frame.grid(row=1, column=0, sticky="nsew")
        
        body_frame.grid_columnconfigure(0, weight=3)
        body_frame.grid_columnconfigure(1, weight=7)
        body_frame.grid_rowconfigure(0, weight=1)

        self.build_analyzer_panel(body_frame)
        self.build_dashboard_table_panel(body_frame)

    def create_kpi_card_stacked(self, parent, row_idx, title, initial_val, color):
        card = ctk.CTkFrame(parent, fg_color="#161b22", corner_radius=8, border_width=1, border_color="#21262d")
        pady_tuple = (0, 2) if row_idx == 0 else (2, 0)
        card.grid(row=row_idx, column=0, pady=pady_tuple, sticky="nsew")

        card.grid_rowconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)

        lbl_t = ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=11, weight="bold"), text_color="#8b949e", anchor="center")
        lbl_t.grid(row=0, column=0, sticky="s", pady=(4, 1))

        lbl_v = ctk.CTkLabel(card, text=initial_val, font=ctk.CTkFont(size=16, weight="bold"), text_color=color, anchor="center")
        lbl_v.grid(row=1, column=0, sticky="n", pady=(1, 4))
        return lbl_v

    def create_kpi_card(self, parent, col, title, initial_val, color):
        card = ctk.CTkFrame(parent, fg_color="#161b22", corner_radius=8, border_width=1, border_color="#21262d")
        card.grid(row=0, column=col, padx=4, sticky="nsew")

        # Center content vertically in card height
        card.grid_rowconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)

        lbl_t = ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=12, weight="bold"), text_color="#8b949e", anchor="center")
        lbl_t.grid(row=0, column=0, sticky="s", pady=(8, 2))

        lbl_v = ctk.CTkLabel(card, text=initial_val, font=ctk.CTkFont(size=20, weight="bold"), text_color=color, anchor="center")
        lbl_v.grid(row=1, column=0, sticky="n", pady=(2, 8))
        return lbl_v

    def create_news_kpi_card(self, parent, col):
        card = ctk.CTkFrame(parent, fg_color="#161b22", corner_radius=8, border_width=1, border_color="#21262d")
        card.grid(row=0, column=col, padx=4, sticky="nsew")

        lbl_t = ctk.CTkLabel(card, text="NEWS (UPCOMING 3)", font=ctk.CTkFont(size=12, weight="bold"), text_color="#8b949e", anchor="center")
        lbl_t.pack(anchor="center", padx=10, pady=(8, 2))

        news_container = ctk.CTkFrame(card, fg_color="transparent")
        news_container.pack(fill="both", expand=True, padx=6, pady=(0, 8))

        lbl_none = ctk.CTkLabel(news_container, text="No news today", font=ctk.CTkFont(size=11), text_color="#8b949e")
        lbl_none.pack(expand=True)

        return lbl_t, news_container

    def create_no_news_kpi_card(self, parent, col):
        card = ctk.CTkFrame(parent, fg_color="#161b22", corner_radius=8, border_width=1, border_color="#21262d")
        card.grid(row=0, column=col, padx=4, sticky="nsew")

        lbl_t = ctk.CTkLabel(card, text="NO NEWS", font=ctk.CTkFont(size=12, weight="bold"), text_color="#00e6a8", anchor="center")
        lbl_t.pack(anchor="center", padx=6, pady=(4, 1))

        # Tightened padding to fit 5x4 grid comfortably
        no_news_container = ctk.CTkFrame(card, fg_color="transparent")
        no_news_container.pack(fill="both", expand=True, padx=2, pady=(0, 4))

        lbl_none = ctk.CTkLabel(no_news_container, text="Calculating...", font=ctk.CTkFont(size=11), text_color="#8b949e")
        lbl_none.pack(expand=True)

        return lbl_t, no_news_container

    def update_dashboard_news_widget(self, upcoming_events):
        for widget in self.card_news_container.winfo_children():
            widget.destroy()

        if upcoming_events:
            self.card_news_title.configure(text_color="#ff3b30")  # RED text if upcoming news events exist
            first_3 = upcoming_events[:3]
            for ev in first_3:
                row = ctk.CTkFrame(self.card_news_container, fg_color="transparent")
                row.pack(anchor="center", pady=1)

                impact_str = str(ev.get("impact", "")).capitalize()
                if "High" in impact_str or impact_str in ["Red", "3"]:
                    dot_color = "#ff3b30"
                elif "Medium" in impact_str or impact_str in ["Orange", "2"]:
                    dot_color = "#ff9500"
                elif "Low" in impact_str or impact_str in ["Yellow", "1"]:
                    dot_color = "#ffff33"
                else:
                    dot_color = "#8b949e"

                dot = ctk.CTkLabel(row, text="●", text_color=dot_color, font=ctk.CTkFont(size=10, weight="bold"))
                dot.pack(side="left", padx=(0, 5))

                time_str = ev.get("time", "N/A")
                curr_str = ev.get("currency", "")
                title_str = ev.get("title", "")

                text_lbl = ctk.CTkLabel(
                    row, 
                    text=f"{time_str}  {curr_str}  {title_str}", 
                    font=ctk.CTkFont(size=11), 
                    text_color="#f0f6fc", 
                    anchor="center"
                )
                text_lbl.pack(side="left")
        else:
            self.card_news_title.configure(text_color="#8b949e")
            lbl_none = ctk.CTkLabel(self.card_news_container, text="No upcoming news", font=ctk.CTkFont(size=11), text_color="#8b949e")
            lbl_none.pack(expand=True, pady=4)

    def update_dashboard_no_news_widget(self, today_events):
        for widget in self.card_no_news_container.winfo_children():
            widget.destroy()

        now = datetime.now().astimezone()
        active_news_currencies = set()

        for ev in today_events:
            curr = str(ev.get("currency", "")).upper().strip()
            ev_dt = ev.get("dt")
            if curr and ev_dt:
                comp_dt = ev_dt.replace(tzinfo=now.tzinfo) if (ev_dt.tzinfo is None and now.tzinfo is not None) else ev_dt
                # Restrict pair if news is in future OR less than 1 hour has passed since release
                if comp_dt > now or (comp_dt + timedelta(hours=1)) > now:
                    active_news_currencies.add(curr)
            elif curr:
                active_news_currencies.add(curr)

        no_news_pairs = [clean_p for clean_p, c1, c2 in PARSED_FOREX_PAIRS if c1 not in active_news_currencies and c2 not in active_news_currencies]

        if no_news_pairs:
            display_pairs = no_news_pairs[:20]  # Up to 20 pairs (5 horizontal x 4 vertical)
            for c in range(5):
                self.card_no_news_container.grid_columnconfigure(c, weight=1)
            for r in range(4):
                self.card_no_news_container.grid_rowconfigure(r, weight=1)

            for idx, pair_str in enumerate(display_pairs):
                r = idx // 5
                c = idx % 5
                lbl = ctk.CTkLabel(
                    self.card_no_news_container,
                    text=pair_str,
                    font=ctk.CTkFont(size=10),
                    text_color="#f0f6fc",
                    anchor="center"
                )
                lbl.grid(row=r, column=c, padx=1, pady=0, sticky="nsew")
        else:
            lbl_none = ctk.CTkLabel(self.card_no_news_container, text="No clear pairs today", font=ctk.CTkFont(size=11), text_color="#8b949e")
            lbl_none.pack(expand=True, pady=4)

    def build_analyzer_panel(self, parent):
        panel = ctk.CTkFrame(parent, fg_color="#161b22", corner_radius=10, border_width=1, border_color="#21262d")
        panel.grid(row=0, column=0, padx=(0, 6), sticky="nsew")

        # Container stretched across full height for evenly distributed spacing
        center_wrap = ctk.CTkFrame(panel, fg_color="transparent")
        center_wrap.pack(fill="both", expand=True, padx=14, pady=16)

        btn_frame = ctk.CTkFrame(center_wrap, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 8))
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=0)

        self.btn_paste = ctk.CTkButton(
            btn_frame, 
            text="Paste Chart", 
            fg_color="#00e6a8", 
            hover_color="#00c993", 
            text_color="#0d1117", 
            font=ctk.CTkFont(size=13, weight="bold"), 
            corner_radius=6,
            height=32,
            command=self.paste_image
        )
        self.btn_paste.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        self.btn_clear = ctk.CTkButton(
            btn_frame,
            text="✕",
            width=40,
            height=32,
            fg_color="#da3633",
            hover_color="#f85149",
            text_color="#ffffff",
            font=ctk.CTkFont(weight="bold", size=15),
            corner_radius=6,
            command=self.reset_analyzer_form
        )
        self.btn_clear.grid(row=0, column=1, sticky="e")

        self.img_preview = ctk.CTkLabel(center_wrap, text="No Screenshot Pasted Yet", height=135, fg_color="#0d1117", corner_radius=6, text_color="#8b949e", font=ctk.CTkFont(size=13))
        self.img_preview.pack(fill="x", pady=8)

        fields_frame = ctk.CTkFrame(center_wrap, fg_color="transparent")
        fields_frame.pack(fill="both", expand=True, pady=4)

        self.entry_pair = self.create_dark_field(fields_frame, "Pair / Asset:")
        self.entry_tf = self.create_dark_field(fields_frame, "Timeframe:")
        self.entry_direction = self.create_dark_field(fields_frame, "Direction (BUY/SELL):")
        self.entry_entry = self.create_dark_field(fields_frame, "Entry Price:")
        self.entry_sl = self.create_dark_field(fields_frame, "Stop Loss:")
        self.entry_tp = self.create_dark_field(fields_frame, "Take Profit:")
        self.entry_rr = self.create_dark_field(fields_frame, "Risk / Reward:")
        
        # Status & Type dropdowns - clean options list without (None)
        self.opt_status = self.create_dark_dropdown(fields_frame, "Status (OPEN/TP/SL):", ["OPEN", "TP", "SL"], height=29)
        self.opt_type = self.create_dark_dropdown(fields_frame, "Type:", ["HnS", "i HnS", "FVG", "S & R", "Breakout"], height=29)

        # Default both fields to empty string so form stays clear when analyzed
        self.opt_status.set("")
        self.opt_type.set("")

        self.entry_pair.bind("<KeyRelease>", self.calculate_live_rr)
        self.entry_entry.bind("<KeyRelease>", self.calculate_live_rr)
        self.entry_sl.bind("<KeyRelease>", self.calculate_live_rr)
        self.entry_tp.bind("<KeyRelease>", self.calculate_live_rr)

        self.entry_notes = ctk.CTkEntry(center_wrap, placeholder_text="Optional Trade Confluence Notes...", fg_color="#0d1117", border_color="#30363d", text_color="#f0f6fc", font=ctk.CTkFont(size=13))
        self.entry_notes.pack(fill="x", pady=8)

        self.btn_save = ctk.CTkButton(
            center_wrap, 
            text="Save Trade to Journal", 
            fg_color="#00e6a8", 
            hover_color="#00c993", 
            text_color="#0d1117", 
            font=ctk.CTkFont(size=13, weight="bold"), 
            corner_radius=6,
            height=32,
            command=self.save_trade
        )
        self.btn_save.pack(fill="x", pady=(8, 0))

    def create_dark_field(self, parent, label_text):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", expand=True, pady=4)
        lbl = ctk.CTkLabel(row, text=label_text, width=130, anchor="w", text_color="#8b949e", font=ctk.CTkFont(size=13))
        lbl.pack(side="left")
        entry = ctk.CTkEntry(row, fg_color="#0d1117", border_color="#30363d", text_color="#f0f6fc", height=29, font=ctk.CTkFont(size=13))
        entry.pack(side="right", expand=True, fill="x")
        return entry

    def create_dark_dropdown(self, parent, label_text, options, height=29):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", expand=True, pady=4)
        lbl = ctk.CTkLabel(row, text=label_text, width=130, anchor="w", text_color="#8b949e", font=ctk.CTkFont(size=13))
        lbl.pack(side="left")

        opt_menu = CustomDropdownButton(row, options, "", app_instance=self, height=height)
        opt_menu.pack(side="right", expand=True, fill="x")
        return opt_menu

    def build_dashboard_table_panel(self, parent):
        panel = ctk.CTkFrame(parent, fg_color="#161b22", corner_radius=10, border_width=1, border_color="#21262d")
        panel.grid(row=0, column=1, padx=(6, 0), sticky="nsew")

        title = ctk.CTkLabel(panel, text="Recent Trades", font=ctk.CTkFont(size=14, weight="bold"), text_color="#f0f6fc", anchor="center")
        title.pack(fill="x", padx=12, pady=(12, 6))

        columns = ("ID", "Pair", "TF", "Direction", "Entry", "SL", "TP", "R:R", "Status", "Type", "Date")
        self.tree_dash = ttk.Treeview(panel, columns=columns, show="headings", height=16)
        
        col_widths = {
            "ID": 40, "Pair": 90, "TF": 50, "Direction": 80,
            "Entry": 85, "SL": 85, "TP": 85, "R:R": 65,
            "Status": 70, "Type": 90, "Date": 105
        }

        for col in columns:
            self.tree_dash.heading(col, text=col)
            self.tree_dash.column(col, width=col_widths.get(col, 75), minwidth=40, stretch=True, anchor="center")

        self.tree_dash.pack(fill="both", expand=True, padx=12, pady=(4, 10))
        self.tree_dash.bind("<Double-1>", self.on_trade_double_click)
        self.tree_dash.bind("<Button-3>", lambda event: self.show_dash_context_menu(event, self.tree_dash))
        self.tree_dash.bind("<Button-2>", lambda event: self.show_dash_context_menu(event, self.tree_dash))

    # ------------------ ECONOMIC NEWS VIEW ------------------ #
    def build_news_view(self):
        self.view_news.grid_rowconfigure(1, weight=1)
        self.view_news.grid_columnconfigure(0, weight=1)

        # High-contrast impact circle icons (Low Impact vibrant light yellow #ffff33, Passed muted gray #484f58)
        self.impact_icons = {
            "high": self._create_circle_icon("#ff3b30", size=14),     # Bright Red
            "medium": self._create_circle_icon("#ff9500", size=14),   # Pure Orange
            "low": self._create_circle_icon("#ffff33", size=14),      # Vibrant Light Yellow
            "none": self._create_circle_icon("#8b949e", size=14),     # Muted Gray
            "passed": self._create_circle_icon("#484f58", size=14)   # Grayed out past event
        }

        ctrl_frame = ctk.CTkFrame(self.view_news, fg_color="#161b22", corner_radius=10, border_width=1, border_color="#21262d")
        ctrl_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10), padx=5)

        left_ctrls = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        left_ctrls.pack(side="left", padx=15, pady=12)

        self.news_range_var = "Today"
        self.opt_news_range = CustomDropdownButton(
            left_ctrls,
            ["Today", "This Week", "Next Week", "Last Week"],
            "Today",
            app_instance=self,
            width=130,
            height=32,
            command_callback=lambda val: self.on_news_range_change(val)
        )
        self.opt_news_range.pack(side="left", padx=(0, 8))

        self.news_currency_var = "All Currencies"
        self.opt_news_currency = CustomDropdownButton(
            left_ctrls,
            ["All Currencies", "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "CNY"],
            "All Currencies",
            app_instance=self,
            width=140,
            height=32,
            command_callback=lambda val: self.on_news_currency_change(val),
            custom_max_h=440
        )
        self.opt_news_currency.pack(side="left")

        btn_refresh_news = ctk.CTkButton(
            ctrl_frame,
            text="Refresh News",
            fg_color="#21262d",
            hover_color="#30363d",
            text_color="#f0f6fc",
            width=130,
            height=32,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.fetch_and_render_news
        )
        btn_refresh_news.pack(side="right", padx=15, pady=12)

        # Absolutely centered in total parent container regardless of left/right element widths
        lbl_title = ctk.CTkLabel(ctrl_frame, text="Forex Economic Calendar", font=ctk.CTkFont(size=16, weight="bold"), text_color="#f0f6fc", anchor="center")
        lbl_title.place(relx=0.5, rely=0.5, anchor="center")

        table_panel = ctk.CTkFrame(self.view_news, fg_color="#161b22", corner_radius=10, border_width=1, border_color="#21262d")
        table_panel.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        table_panel.grid_rowconfigure(0, weight=1)
        table_panel.grid_columnconfigure(0, weight=1)

        columns = ("Date", "Time", "Currency", "Event", "Actual", "Forecast", "Previous")
        self.tree_news = ttk.Treeview(table_panel, columns=columns, show=("tree", "headings"), height=20)

        # Alternating row striping and passed-event graying
        self.tree_news.tag_configure("evenrow", background="#161b22", foreground="#f0f6fc")
        self.tree_news.tag_configure("oddrow", background="#0d1117", foreground="#f0f6fc")
        self.tree_news.tag_configure("passed_evenrow", background="#12161b", foreground="#484f58")
        self.tree_news.tag_configure("passed_oddrow", background="#0a0d12", foreground="#484f58")

        self.tree_news.heading("#0", text="Impact")
        self.tree_news.column("#0", width=65, minwidth=50, stretch=False, anchor="center")

        col_widths = {
            "Date": 110,
            "Time": 90,
            "Currency": 80,
            "Event": 350,
            "Actual": 90,
            "Forecast": 90,
            "Previous": 90
        }

        for col in columns:
            self.tree_news.heading(col, text=col)
            self.tree_news.column(col, width=col_widths.get(col, 100), minwidth=60, stretch=(col == "Event"), anchor="w" if col == "Event" else "center")

        self.tree_news.pack(fill="both", expand=True, padx=15, pady=15)

    def on_news_range_change(self, selected_range):
        self.news_range_var = selected_range
        self.fetch_and_render_news()

    def on_news_currency_change(self, selected_currency):
        self.news_currency_var = selected_currency
        self.fetch_and_render_news()

    def fetch_and_render_news(self):
        for item in self.tree_news.get_children():
            self.tree_news.delete(item)

        self.tree_news.insert("", "end", image=self.impact_icons["none"], values=("", "", "", "Loading economic calendar events...", "", "", ""))

        def worker():
            events = []
            upcoming_events = []
            today_events = []
            now = datetime.now().astimezone()
            
            # Sunday-Saturday calendar alignment
            days_since_sunday = (now.weekday() + 1) % 7
            current_sunday = (now - timedelta(days=days_since_sunday)).replace(hour=0, minute=0, second=0, microsecond=0)

            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

            if self.news_range_var == "Today":
                start_date = today_start
                end_date = today_end
            elif self.news_range_var == "This Week":
                start_date = current_sunday
                end_date = (current_sunday + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=999999)
            elif self.news_range_var == "Next Week":
                start_date = current_sunday + timedelta(days=7)
                end_date = (start_date + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=999999)
            elif self.news_range_var == "Last Week":
                start_date = current_sunday - timedelta(days=7)
                end_date = (start_date + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=999999)
            else:
                start_date = current_sunday
                end_date = (current_sunday + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=999999)

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }

            json_urls = [
                "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                "https://pipatlas.com/api/calendar"
            ]

            raw_events = []
            for target_url in json_urls:
                try:
                    res = requests.get(target_url, headers=headers, timeout=8)
                    if res.status_code == 200:
                        data = res.json()
                        if isinstance(data, dict) and "events" in data:
                            raw_events = data["events"]
                        elif isinstance(data, list):
                            raw_events = data
                        if raw_events:
                            break
                except Exception as e:
                    print(f"Error fetching calendar JSON: {e}")
                    continue

            for ev in raw_events:
                item_dict = parse_news_event(ev)
                if not item_dict:
                    continue

                ev_dt = item_dict.get("dt")

                # Include events until 30 minutes after release time
                if ev_dt:
                    comp_dt = ev_dt.replace(tzinfo=now.tzinfo) if (ev_dt.tzinfo is None and now.tzinfo is not None) else ev_dt
                    if (comp_dt + timedelta(minutes=30)) >= now:
                        upcoming_events.append(item_dict)
                    if today_start <= comp_dt <= today_end:
                        today_events.append(item_dict)

                if ev_dt:
                    if start_date <= ev_dt <= end_date:
                        events.append(item_dict)
                else:
                    events.append(item_dict)

            # Store in cache for background tracker updates
            self.cached_news_events = events

            # Sort upcoming chronologically
            upcoming_events.sort(key=lambda x: x["dt"] if x["dt"] else now)

            # Fallback if strict range boundary yields no items due to week boundary offset
            if not events and raw_events:
                for ev in raw_events:
                    item_dict = parse_news_event(ev)
                    if item_dict:
                        events.append(item_dict)

            def update_ui():
                self.update_dashboard_news_widget(upcoming_events)
                self.update_dashboard_no_news_widget(today_events)

                for item in self.tree_news.get_children():
                    self.tree_news.delete(item)

                # Apply Currency Filter if specified
                filtered_events = events
                if self.news_currency_var != "All Currencies":
                    filtered_events = [e for e in events if e["currency"].upper() == self.news_currency_var.upper()]

                if not filtered_events:
                    self.tree_news.insert("", "end", image=self.impact_icons["none"], values=("", "", "", "No news events match current filter.", "", "", ""))
                    return

                current_time = datetime.now().astimezone()
                first_active_item = None

                for idx, ev in enumerate(filtered_events):
                    ev_dt = ev.get("dt")
                    has_passed = False
                    if ev_dt:
                        comp_dt = ev_dt.replace(tzinfo=current_time.tzinfo) if (ev_dt.tzinfo is None and current_time.tzinfo is not None) else ev_dt
                        if comp_dt < current_time:
                            has_passed = True

                    impact_str = str(ev.get("impact", "")).capitalize()

                    if has_passed:
                        icon = self.impact_icons["passed"]
                        row_tag = "passed_evenrow" if idx % 2 == 0 else "passed_oddrow"
                    else:
                        if "High" in impact_str or impact_str in ["Red", "3"]:
                            icon = self.impact_icons["high"]
                        elif "Medium" in impact_str or impact_str in ["Orange", "2"]:
                            icon = self.impact_icons["medium"]
                        elif "Low" in impact_str or impact_str in ["Yellow", "1"]:
                            icon = self.impact_icons["low"]
                        else:
                            icon = self.impact_icons["none"]
                        row_tag = "evenrow" if idx % 2 == 0 else "oddrow"

                    item_id = self.tree_news.insert(
                        "",
                        "end",
                        image=icon,
                        values=(
                            ev["date"], 
                            ev["time"], 
                            ev["currency"], 
                            ev["title"], 
                            ev["actual"], 
                            ev["forecast"], 
                            ev["previous"]
                        ),
                        tags=(row_tag,)
                    )

                    # Track first non-passed event to auto-scroll down to active events
                    if not has_passed and first_active_item is None:
                        first_active_item = item_id

                # Auto-scroll to first active/upcoming event if inactive events fill top of view
                if first_active_item:
                    self.tree_news.see(first_active_item)

            if self.winfo_exists():
                self.after(0, update_ui)

        threading.Thread(target=worker, daemon=True).start()

    # ------------------ CALENDAR VIEW ------------------ #
    def build_calendar_view(self):
        self.view_calendar.grid_rowconfigure(1, weight=1)
        self.view_calendar.grid_columnconfigure(0, weight=1)

        ctrl_frame = ctk.CTkFrame(self.view_calendar, fg_color="#161b22", corner_radius=8, border_width=1, border_color="#21262d")
        ctrl_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10), padx=5)

        btn_prev = ctk.CTkButton(ctrl_frame, text="❮", width=44, fg_color="#21262d", hover_color="#30363d", command=self.prev_month, font=ctk.CTkFont(size=13, weight="bold"))
        btn_prev.pack(side="left", padx=10, pady=8)

        self.lbl_month_year = ctk.CTkLabel(ctrl_frame, text="", font=ctk.CTkFont(size=20, weight="bold"), text_color="#f0f6fc")
        self.lbl_month_year.pack(side="left", expand=True)

        btn_next = ctk.CTkButton(ctrl_frame, text="❯", width=44, fg_color="#21262d", hover_color="#30363d", command=self.next_month, font=ctk.CTkFont(size=13, weight="bold"))
        btn_next.pack(side="right", padx=10, pady=8)

        self.cal_grid_frame = ctk.CTkFrame(self.view_calendar, fg_color="#161b22", corner_radius=10, border_width=1, border_color="#21262d")
        self.cal_grid_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
        for col in range(7):
            self.cal_grid_frame.grid_columnconfigure(col, weight=1, uniform="cal_col")
        for row in range(7):
            self.cal_grid_frame.grid_rowconfigure(row, weight=1, uniform="cal_row")

    def render_calendar(self):
        for widget in self.cal_grid_frame.winfo_children():
            widget.destroy()

        month_name = calendar.month_name[self.current_month]
        self.lbl_month_year.configure(text=f"{month_name} {self.current_year}")

        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for idx, day in enumerate(days):
            lbl = ctk.CTkLabel(self.cal_grid_frame, text=day, font=ctk.CTkFont(size=13, weight="bold"), text_color="#8b949e")
            lbl.grid(row=0, column=idx, pady=(8, 4), sticky="nsew")

        # Fetch raw trades to calculate per-day TP vs SL count accurately
        all_trades = db.fetch_all_trades()
        daily_trades_map = defaultdict(list)
        for t in all_trades:
            d_str = str(t[9])[:10] if len(str(t[9])) >= 10 else str(t[9])
            daily_trades_map[d_str].append(t)

        cal = calendar.Calendar(firstweekday=0)
        month_days = cal.monthdayscalendar(self.current_year, self.current_month)

        while len(month_days) < 6:
            month_days.append([0] * 7)

        for row_idx, week in enumerate(month_days, start=1):
            for col_idx, day_num in enumerate(week):
                if day_num == 0:
                    tile = ctk.CTkFrame(self.cal_grid_frame, fg_color="#0d1117", corner_radius=6)
                    tile.grid(row=row_idx, column=col_idx, padx=3, pady=3, sticky="nsew")
                    continue

                date_str = f"{self.current_year:04d}-{self.current_month:02d}-{day_num:02d}"
                day_trades = daily_trades_map.get(date_str, [])

                bg_color = "#21262d"
                border_color = "#30363d"
                txt_color = "#f0f6fc"

                if day_trades:
                    count = len(day_trades)
                    trades_count_str = f"{count} trade{'s' if count > 1 else ''}"
                    
                    tp_count = sum(1 for t in day_trades if clean_status(t[8]) == "TP")
                    sl_count = sum(1 for t in day_trades if clean_status(t[8]) == "SL")

                    # Green if TPs >= SLs (or default), Red if SLs > TPs
                    if sl_count > tp_count:
                        bg_color = "#4a151b"
                        border_color = "#7f1d1d"
                    else:
                        bg_color = "#1e4620"
                        border_color = "#2e7d32"
                else:
                    trades_count_str = "0 trades"

                tile = ctk.CTkFrame(self.cal_grid_frame, fg_color=bg_color, border_color=border_color, border_width=1, corner_radius=6, cursor="hand2")
                tile.grid(row=row_idx, column=col_idx, padx=3, pady=3, sticky="nsew")

                lbl_day = ctk.CTkLabel(tile, text=str(day_num), font=ctk.CTkFont(size=12, weight="bold"), text_color=txt_color)
                lbl_day.place(x=8, y=6, anchor="nw")

                lbl_count = ctk.CTkLabel(tile, text=trades_count_str, font=ctk.CTkFont(size=12, weight="bold"), text_color=txt_color if day_trades else "#484f58")
                lbl_count.place(relx=0.5, rely=0.5, anchor="center")

                for widget in (tile, lbl_day, lbl_count):
                    widget.bind("<Button-1>", lambda e, d=date_str: self.open_day_trades_dialog(d))

    def open_day_trades_dialog(self, date_str):
        trades = db.fetch_trades_by_date(date_str)
        if not trades:
            messagebox.showinfo("Calendar Info", f"No trades recorded on {date_str}.")
            return

        all_records = db.fetch_all_trades()
        total_records = len(all_records)
        id_map = {r[0]: total_records - i for i, r in enumerate(all_records)}

        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Trades Recorded on {date_str}")
        dialog.geometry("1080x420")
        dialog.configure(fg_color="#0d1117")
        dialog.transient(self)
        dialog.focus_force()

        lbl = ctk.CTkLabel(dialog, text=f"📊 Trades for {date_str} (Double-click to view chart)", font=ctk.CTkFont(size=16, weight="bold"), text_color="#00e6a8")
        lbl.pack(anchor="w", padx=15, pady=12)

        columns = ("ID", "Pair", "TF", "Direction", "Entry", "SL", "TP", "R:R", "Status", "Type", "Date")
        tree = ttk.Treeview(dialog, columns=columns, show="headings", height=10)
        
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=90, stretch=True, anchor="center")

        tree.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        for t in trades:
            db_id = t[0]
            display_id = id_map.get(db_id, db_id)
            display_row = [
                display_id, clean_pair(t[1]), t[2], clean_direction(t[3]), t[4], t[5], t[6], t[7],
                clean_status(t[8]), t[12] if len(t) > 12 and t[12] else "HnS",
                str(t[9])[:10] if len(str(t[9])) > 10 else t[9]
            ]
            tree.insert("", "end", values=display_row, tags=(str(db_id),))

        tree.bind("<Double-1>", self.on_trade_double_click)

    def prev_month(self):
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        self.render_calendar()

    def next_month(self):
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        self.render_calendar()

    # ------------------ TRADES VIEW ------------------ #
    def build_trades_view(self):
        self.view_trades.grid_rowconfigure(0, weight=1)
        self.view_trades.grid_columnconfigure(0, weight=1)

        panel = ctk.CTkFrame(self.view_trades, fg_color="#161b22", corner_radius=10, border_width=1, border_color="#21262d")
        panel.grid(row=0, column=0, sticky="nsew")

        header_frame = ctk.CTkFrame(panel, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=(15, 10))

        title = ctk.CTkLabel(header_frame, text="Complete Journal Database (Double-click to view chart, Right-click to modify/delete)", font=ctk.CTkFont(size=15, weight="bold"), text_color="#f0f6fc")
        title.pack(side="left")

        # Delete Selected button (supports multi-selection deletion)
        btn_delete = ctk.CTkButton(
            header_frame, 
            text="Delete Selected", 
            fg_color="#da3633", 
            hover_color="#f85149", 
            command=self.delete_selected, 
            width=150, 
            height=32, 
            font=ctk.CTkFont(size=13, weight="bold")
        )
        btn_delete.pack(side="right", padx=(5, 0))

        # Refresh Database button
        btn_refresh = ctk.CTkButton(
            header_frame, 
            text="Refresh Database", 
            fg_color="#21262d", 
            hover_color="#30363d", 
            command=self.load_database_records, 
            width=150, 
            height=32, 
            font=ctk.CTkFont(size=13, weight="bold")
        )
        btn_refresh.pack(side="right", padx=5)

        # Import / Export button matching the style and size of existing buttons
        self.btn_io = ctk.CTkButton(
            header_frame,
            text="Import / Export",
            fg_color="#21262d",
            hover_color="#30363d",
            command=self.show_import_export_options,
            width=150,
            height=32,
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.btn_io.pack(side="right", padx=5)

        columns = ("ID", "Pair", "TF", "Direction", "Entry", "SL", "TP", "R:R", "Status", "Type", "Date")
        self.tree_trades = ttk.Treeview(panel, columns=columns, show="headings", height=20, selectmode="extended")
        
        for col in columns:
            self.tree_trades.heading(col, text=col)
            self.tree_trades.column(col, width=90, stretch=True, anchor="center")

        self.tree_trades.pack(fill="both", expand=True, padx=15, pady=(5, 15))
        self.tree_trades.bind("<Double-1>", self.on_trade_double_click)
        self.tree_trades.bind("<Button-3>", lambda event: self.show_trades_context_menu(event, self.tree_trades))
        self.tree_trades.bind("<Button-2>", lambda event: self.show_trades_context_menu(event, self.tree_trades))

    def show_import_export_options(self):
        self.show_custom_popup_menu(
            self.btn_io,
            ["Export Journal (.zip)", "Import Journal (.zip)", "Check for Auto Update"],
            callback=self.handle_import_export_choice
        )

    def handle_import_export_choice(self, choice):
        if "Export" in choice:
            self.export_journal()
        elif "Import" in choice:
            self.import_journal()
        elif "Update" in choice:
            self.check_for_updates(silent=False)

    def export_journal(self):
        file_path = filedialog.asksaveasfilename(
            title="Export Trade Journal Backup",
            defaultextension=".zip",
            filetypes=[("Zip Archive", "*.zip")]
        )
        if not file_path:
            return

        try:
            records = db.fetch_all_trades()
            total_records = len(records)
            export_data = []

            with zipfile.ZipFile(file_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for idx, r in enumerate(records):
                    db_id = r[0]
                    display_id = total_records - idx
                    img_path = db.get_trade_image_path(db_id)

                    if img_path and os.path.exists(img_path):
                        img_filename = f"chart_{display_id}.png"
                        zipf.write(img_path, f"images/{img_filename}")

                    trade_dict = {
                        "display_id": display_id,
                        "pair": clean_pair(r[1]),
                        "timeframe": r[2],
                        "direction": clean_direction(r[3]),
                        "entry_price": r[4],
                        "stop_loss": r[5],
                        "take_profit": r[6],
                        "rr_ratio": r[7],
                        "status": clean_status(r[8]),
                        "date": str(r[9]),
                        "notes": r[10] if len(r) > 10 else "",
                        "trade_type": r[12] if len(r) > 12 and r[12] else "HnS",
                        "image_filename": f"chart_{display_id}.png" if (img_path and os.path.exists(img_path)) else ""
                    }
                    export_data.append(trade_dict)

                json_str = json.dumps(export_data, indent=2)
                zipf.writestr("journal_trades.json", json_str)

            messagebox.showinfo("Export Complete", f"Successfully exported {len(export_data)} trade(s) and chart screenshots to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export journal: {e}")

    def import_journal(self):
        file_path = filedialog.askopenfilename(
            title="Import Trade Journal Backup",
            filetypes=[("Zip Archive", "*.zip")]
        )
        if not file_path:
            return

        try:
            imported_count = 0
            with tempfile.TemporaryDirectory() as temp_dir:
                with zipfile.ZipFile(file_path, "r") as zipf:
                    zipf.extractall(temp_dir)

                json_path = os.path.join(temp_dir, "journal_trades.json")
                if not os.path.exists(json_path):
                    messagebox.showerror("Import Error", "Invalid backup archive: missing 'journal_trades.json'")
                    return

                with open(json_path, "r", encoding="utf-8") as f:
                    trades_list = json.load(f)

                # Ensure oldest trades are imported first to preserve chronological order
                trades_list.reverse()

                for item in trades_list:
                    img_filename = item.get("image_filename", "")
                    dest_img_path = ""

                    existing_records = db.fetch_all_trades()
                    new_display_id = len(existing_records) + 1

                    if img_filename:
                        extracted_img = os.path.join(temp_dir, "images", img_filename)
                        if os.path.exists(extracted_img):
                            new_filename = f"chart_{new_display_id}.png"
                            dest_img_path = os.path.join(self.saved_images_dir, new_filename)
                            shutil.copy(extracted_img, dest_img_path)

                    payload = {
                        "pair": clean_pair(item.get("pair", "")),
                        "timeframe": item.get("timeframe", ""),
                        "direction": clean_direction(item.get("direction", "")),
                        "entry_price": item.get("entry_price", ""),
                        "stop_loss": item.get("stop_loss", ""),
                        "take_profit": item.get("take_profit", ""),
                        "rr_ratio": item.get("rr_ratio", ""),
                        "status": clean_status(item.get("status", "OPEN")),
                        "notes": item.get("notes", ""),
                        "trade_type": item.get("trade_type", "HnS"),
                        "image_path": dest_img_path
                    }

                    success, _ = db.add_trade(payload)
                    if success:
                        imported_count += 1

            self.load_database_records()
            messagebox.showinfo("Import Complete", f"Successfully imported {imported_count} trade(s) into your journal database!")
        except Exception as e:
            messagebox.showerror("Import Error", f"Failed to import journal: {e}")

    # ------------------ CALCULATOR VIEW ------------------ #
    def build_calculator_view(self):
        self.view_calculator.grid_rowconfigure(0, weight=1)
        self.view_calculator.grid_columnconfigure(0, weight=1)

        saved_balance, saved_risk, saved_mode = self.load_calc_settings()

        container = ctk.CTkFrame(self.view_calculator, fg_color="transparent")
        container.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        container.grid_columnconfigure(0, weight=1)
        container.grid_columnconfigure(1, weight=1)
        container.grid_rowconfigure(0, weight=1)

        input_card = ctk.CTkFrame(container, fg_color="#161b22", corner_radius=10, border_width=1, border_color="#21262d")
        input_card.grid(row=0, column=0, padx=(0, 6), pady=0, sticky="nsew")

        lbl_header = ctk.CTkLabel(input_card, text="Account & Trade Inputs", font=ctk.CTkFont(size=15, weight="bold"), text_color="#f0f6fc", anchor="center")
        lbl_header.pack(fill="x", padx=16, pady=(14, 10))

        self.calc_balance_entry = self.create_calc_field(input_card, "Account Balance ($):", saved_balance)

        row_risk = ctk.CTkFrame(input_card, fg_color="transparent")
        row_risk.pack(fill="x", padx=16, pady=5)
        
        lbl_r = ctk.CTkLabel(row_risk, text="Risk:", width=140, anchor="w", text_color="#8b949e", font=ctk.CTkFont(size=13))
        lbl_r.pack(side="left")

        risk_wrap = ctk.CTkFrame(row_risk, fg_color="transparent")
        risk_wrap.pack(side="right", expand=True, fill="x")

        self.calc_risk_entry = ctk.CTkEntry(
            risk_wrap, 
            fg_color="#0d1117", 
            border_color="#30363d",
            border_width=1,
            corner_radius=6,
            text_color="#f0f6fc", 
            height=32,
            font=ctk.CTkFont(size=13)
        )
        self.calc_risk_entry.pack(fill="x", expand=True)
        self.calc_risk_entry.insert(0, saved_risk)

        self.calc_risk_mode_var = saved_mode
        symbol = "% ∨" if saved_mode == "Risk %" else "$ ∨"

        self.btn_risk_dropdown = ctk.CTkButton(
            self.calc_risk_entry,
            text=symbol,
            width=46,
            height=24,
            fg_color="#161b22",
            hover_color="#21262d",
            corner_radius=4,
            text_color="#00e6a8",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self.toggle_risk_dropdown
        )
        self.btn_risk_dropdown.place(relx=1.0, rely=0.5, anchor="e", x=-4)

        row_pair = ctk.CTkFrame(input_card, fg_color="transparent")
        row_pair.pack(fill="x", padx=16, pady=5)
        
        lbl_p = ctk.CTkLabel(row_pair, text="Pair:", width=140, anchor="w", text_color="#8b949e", font=ctk.CTkFont(size=13))
        lbl_p.pack(side="left")

        pair_wrap = ctk.CTkFrame(row_pair, fg_color="transparent")
        pair_wrap.pack(side="right", expand=True, fill="x")

        self.calc_pair_entry = CustomDropdownButton(
            pair_wrap,
            FOREX_PAIRS_LIST,
            "XAU/USD (Gold)",
            app_instance=self,
            height=32,
            command_callback=lambda val: self.select_pair_option(val),
            is_searchable=True,
            enable_favorites=True
        )
        self.calc_pair_entry.pack(fill="x", expand=True)

        row_entry = ctk.CTkFrame(input_card, fg_color="transparent")
        row_entry.pack(fill="x", padx=16, pady=5)
        
        lbl_e = ctk.CTkLabel(row_entry, text="Entry Price:", width=140, anchor="w", text_color="#8b949e", font=ctk.CTkFont(size=13))
        lbl_e.pack(side="left")

        entry_wrap = ctk.CTkFrame(row_entry, fg_color="transparent")
        entry_wrap.pack(side="right", expand=True, fill="x")

        self.calc_entry_price = ctk.CTkEntry(
            entry_wrap, 
            fg_color="#0d1117", 
            border_color="#30363d",
            border_width=1,
            corner_radius=6,
            text_color="#f0f6fc", 
            height=32,
            font=ctk.CTkFont(size=13)
        )
        self.calc_entry_price.pack(fill="x", expand=True)
        self.calc_entry_price.insert(0, "2730.50")

        self.btn_live_price = ctk.CTkButton(
            self.calc_entry_price,
            text="LIVE",
            width=46,
            height=24,
            fg_color="#238636",
            hover_color="#2ea043",
            corner_radius=4,
            text_color="#ffffff",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self.fetch_live_entry_price
        )
        self.btn_live_price.place(relx=1.0, rely=0.5, anchor="e", x=-4)

        self.calc_sl_price = self.create_calc_field(input_card, "Stop Loss Price:", "2720.50")

        btn_calc = ctk.CTkButton(
            input_card, 
            text="Calculate Lot Size", 
            fg_color="#00e6a8", 
            hover_color="#00c993", 
            text_color="#0d1117", 
            font=ctk.CTkFont(size=14, weight="bold"),
            height=36,
            command=self.run_lot_calculator
        )
        btn_calc.pack(fill="x", padx=16, pady=(16, 16))

        # Output Card Panel
        out_card = ctk.CTkFrame(container, fg_color="#161b22", corner_radius=10, border_width=1, border_color="#21262d")
        out_card.grid(row=0, column=1, padx=(6, 0), pady=0, sticky="nsew")

        lbl_out_hdr = ctk.CTkLabel(out_card, text="Position Results", font=ctk.CTkFont(size=15, weight="bold"), text_color="#f0f6fc", anchor="center")
        lbl_out_hdr.pack(fill="x", padx=16, pady=(14, 10))

        self.calc_res_lots = self.create_result_display(out_card, "RECOMMENDED LOT SIZE", "0.00 Lots", "#00e6a8", size=18)
        self.calc_res_cash = self.create_result_display(out_card, "TOTAL CASH RISK", "$0.00", "#f85149", size=18)

        for entry_field in (self.calc_balance_entry, self.calc_risk_entry, self.calc_entry_price, self.calc_sl_price):
            entry_field.bind("<KeyRelease>", lambda e: (self.run_lot_calculator(), self.save_calc_settings()))

    def create_calc_field(self, parent, label_text, default_val):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=5)
        lbl = ctk.CTkLabel(row, text=label_text, width=140, anchor="w", text_color="#8b949e", font=ctk.CTkFont(size=13))
        lbl.pack(side="left")
        entry = ctk.CTkEntry(row, fg_color="#0d1117", border_color="#30363d", text_color="#f0f6fc", height=32, font=ctk.CTkFont(size=13))
        entry.pack(side="right", expand=True, fill="x")
        entry.insert(0, default_val)
        return entry

    def create_result_display(self, parent, title, default_val, color, size=18):
        box = ctk.CTkFrame(parent, fg_color="#0d1117", corner_radius=8, border_width=1, border_color="#21262d")
        box.pack(fill="x", padx=16, pady=6)
        
        lbl_t = ctk.CTkLabel(box, text=title, font=ctk.CTkFont(size=11, weight="bold"), text_color="#8b949e", anchor="center")
        lbl_t.pack(anchor="center", padx=12, pady=(8, 2))

        lbl_v = ctk.CTkLabel(box, text=default_val, font=ctk.CTkFont(size=size, weight="bold"), text_color=color, anchor="center")
        lbl_v.pack(anchor="center", padx=12, pady=(0, 8))
        return lbl_v

    # ------------------ ANALYTICS VIEW ------------------ #
    def build_analytics_view(self):
        self.view_analytics.grid_rowconfigure(1, weight=1)
        self.view_analytics.grid_columnconfigure(0, weight=1)

        ctrl_card = ctk.CTkFrame(self.view_analytics, fg_color="#161b22", corner_radius=10, border_width=1, border_color="#21262d")
        ctrl_card.grid(row=0, column=0, sticky="ew", pady=(0, 12), padx=5)

        lbl_select = ctk.CTkLabel(ctrl_card, text="Select Trade for Post-Mortem:", font=ctk.CTkFont(size=14, weight="bold"), text_color="#8b949e")
        lbl_select.pack(side="left", padx=15, pady=12)

        self.opt_analytics_trades = CustomDropdownButton(
            ctrl_card,
            ["No Saved Trades Found"],
            "No Saved Trades Found",
            app_instance=self,
            width=360,
            height=32,
            is_searchable=True
        )
        self.opt_analytics_trades.pack(side="left", padx=(10, 5), pady=12)

        self.opt_analytics_lang = CustomDropdownButton(
            ctrl_card,
            ["English", "Dutch"],
            "English",
            app_instance=self,
            width=110,
            height=32,
            command_callback=self.on_analytics_language_change
        )
        self.opt_analytics_lang.pack(side="left", padx=5, pady=12)

        self.btn_run_analytics = ctk.CTkButton(
            ctrl_card,
            text="Run trade review",
            fg_color="#00e6a8",
            hover_color="#00c993",
            text_color="#0d1117",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=32,
            corner_radius=6,
            command=self.run_ai_trade_review
        )
        self.btn_run_analytics.pack(side="left", padx=5, pady=12)

        self.btn_analytics_paste = ctk.CTkButton(
            ctrl_card,
            text="Paste Chart",
            fg_color="#00e6a8",
            hover_color="#00c993",
            text_color="#0d1117",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=32,
            corner_radius=6,
            command=self.run_ai_pasted_chart_review
        )
        self.btn_analytics_paste.pack(side="left", padx=5, pady=12)

        # Added red reset button matching chart analyzer clear button styling to the complete right
        self.btn_analytics_clear = ctk.CTkButton(
            ctrl_card,
            text="✕",
            width=40,
            height=32,
            fg_color="#da3633",
            hover_color="#f85149",
            text_color="#ffffff",
            font=ctk.CTkFont(weight="bold", size=15),
            corner_radius=6,
            command=self.reset_analytics_output
        )
        self.btn_analytics_clear.pack(side="right", padx=(5, 15), pady=12)

        output_card = ctk.CTkFrame(self.view_analytics, fg_color="#161b22", corner_radius=10, border_width=1, border_color="#21262d")
        output_card.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        output_card.grid_rowconfigure(0, weight=1)
        output_card.grid_columnconfigure(0, weight=1)

        self.txt_analytics_log = ctk.CTkTextbox(
            output_card,
            fg_color="#0d1117",
            text_color="#f0f6fc",
            font=ctk.CTkFont(family="Consolas", size=16),
            border_color="#30363d",
            border_width=1,
            corner_radius=8,
            wrap="word"
        )
        self.txt_analytics_log.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)
        self.txt_analytics_log.insert("end", "💡 Select any trade from your journal above and click 'Run trade review', or click 'Paste Chart' to evaluate and rate an un-saved chart setup.")

    def reset_analytics_output(self):
        selected_lang = self.opt_analytics_lang.get()
        self.on_analytics_language_change(selected_lang)

    # ------------------ CHECKLIST VIEW ------------------ #
    def build_checklist_view(self):
        self.view_checklist.grid_rowconfigure(1, weight=1)
        self.view_checklist.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(self.view_checklist, fg_color="#161b22", corner_radius=10, border_width=1, border_color="#21262d")
        card.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=5, pady=5)
        card.grid_rowconfigure(2, weight=1)
        card.grid_columnconfigure(0, weight=1)

        # Header Section
        header_frame = ctk.CTkFrame(card, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 10))

        lbl_title = ctk.CTkLabel(header_frame, text="☑️ Pre-Trade Execution Checklist", font=ctk.CTkFont(size=18, weight="bold"), text_color="#00e6a8")
        lbl_title.pack(side="left")

        lbl_select_type = ctk.CTkLabel(header_frame, text="Select Setup Type:", font=ctk.CTkFont(size=13, weight="bold"), text_color="#8b949e")
        lbl_select_type.pack(side="left", padx=(25, 8))

        self.opt_checklist_type = CustomDropdownButton(
            header_frame,
            list(TRADE_TYPE_CHECKLISTS.keys()),
            "HnS",
            app_instance=self,
            width=140,
            height=32,
            command_callback=lambda selected_type: self.load_checklist_for_type(selected_type)
        )
        self.opt_checklist_type.pack(side="left")

        btn_reset = ctk.CTkButton(
            header_frame,
            text="Reset Checklist",
            fg_color="#21262d",
            hover_color="#30363d",
            text_color="#f0f6fc",
            width=130,
            height=32,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.reset_checklist
        )
        btn_reset.pack(side="right")

        # Progress Indicator Section
        progress_frame = ctk.CTkFrame(card, fg_color="#0d1117", corner_radius=8, border_width=1, border_color="#21262d")
        progress_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 15))
        progress_frame.grid_columnconfigure(0, weight=1)

        self.lbl_checklist_status = ctk.CTkLabel(progress_frame, text="Readiness: 0% (0/5 items checked)", font=ctk.CTkFont(size=14, weight="bold"), text_color="#8b949e")
        self.lbl_checklist_status.pack(anchor="w", padx=15, pady=(10, 5))

        self.chk_progress = ctk.CTkProgressBar(progress_frame, progress_color="#00e6a8", fg_color="#21262d", height=10)
        self.chk_progress.pack(fill="x", padx=15, pady=(0, 12))
        self.chk_progress.set(0)

        # Scrollable Checklist Items Area
        self.scroll_items = ctk.CTkScrollableFrame(card, fg_color="transparent")
        self.scroll_items.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 15))

        self.load_checklist_for_type("HnS")

    def load_checklist_for_type(self, trade_type):
        for widget in self.scroll_items.winfo_children():
            widget.destroy()

        items = TRADE_TYPE_CHECKLISTS.get(trade_type, TRADE_TYPE_CHECKLISTS["HnS"])
        self.checklist_vars = []

        for title, subtitle in items:
            item_frame = ctk.CTkFrame(self.scroll_items, fg_color="#0d1117", corner_radius=8, border_width=1, border_color="#21262d")
            item_frame.pack(fill="x", pady=5, padx=2)

            var = ctk.BooleanVar(value=False)
            self.checklist_vars.append(var)

            chk = ctk.CTkCheckBox(
                item_frame,
                text=title,
                variable=var,
                command=self.update_checklist_progress,
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#f0f6fc",
                fg_color="#00e6a8",
                hover_color="#00c993",
                checkmark_color="#0d1117"
            )
            chk.pack(anchor="w", padx=15, pady=(10, 2))

            sub = ctk.CTkLabel(item_frame, text=subtitle, font=ctk.CTkFont(size=12), text_color="#8b949e")
            sub.pack(anchor="w", padx=42, pady=(0, 10))

        self.update_checklist_progress()

    def update_checklist_progress(self):
        total = len(self.checklist_vars)
        checked = sum(1 for v in self.checklist_vars if v.get())
        pct = checked / total if total > 0 else 0
        
        self.chk_progress.set(pct)
        if checked == total:
            self.lbl_checklist_status.configure(text=f"Readiness: 100% ({checked}/{total}) - Fully Validated Entry! 🚀", text_color="#00e6a8")
        else:
            self.lbl_checklist_status.configure(text=f"Readiness: {int(pct * 100)}% ({checked}/{total} items checked)", text_color="#8b949e")

    def reset_checklist(self):
        for var in self.checklist_vars:
            var.set(False)
        self.update_checklist_progress()

    def on_analytics_language_change(self, selected_lang):
        self.txt_analytics_log.delete("1.0", "end")
        if selected_lang == "Dutch":
            self.txt_analytics_log.insert("end", "💡 Selecteer hierboven een trade uit je journaal en klik op 'Run trade review', of klik op 'Paste Chart' om een niet-opgeslagen chart te beoordelen.")
        else:
            self.txt_analytics_log.insert("end", "💡 Select any trade from your journal above and click 'Run trade review', or click 'Paste Chart' to evaluate and rate an un-saved chart setup.")

    def populate_analytics_dropdown(self):
        records = db.fetch_all_trades()
        total_trades = len(records)
        self.analytics_trade_map = {}
        options = []

        for idx, r in enumerate(records):
            display_id = total_trades - idx  # 1 for oldest, N for newest
            pair = clean_pair(r[1])
            direction = clean_direction(r[3])
            status = clean_status(r[8])
            date_val = str(r[9])[:10] if len(str(r[9])) > 10 else r[9]
            
            label = f"#{display_id} | {pair} ({direction}) - Status: {status} [{date_val}]"
            options.append(label)
            self.analytics_trade_map[label] = r

        if options:
            self.opt_analytics_trades.update_options(options)
            self.opt_analytics_trades.set(options[0])
        else:
            self.opt_analytics_trades.update_options(["No Saved Trades Found"])
            self.opt_analytics_trades.set("No Saved Trades Found")

    def run_ai_trade_review(self):
        selected_label = self.opt_analytics_trades.get()
        if not selected_label or selected_label not in self.analytics_trade_map:
            messagebox.showwarning("Analytics Warning", "Please select a valid trade from the dropdown list.")
            return

        trade_record = self.analytics_trade_map[selected_label]
        db_id = trade_record[0]
        image_path = db.get_trade_image_path(db_id)
        selected_lang = self.opt_analytics_lang.get()

        self.btn_run_analytics.configure(text="⏳ Reviewing Setup...", state="disabled", fg_color="#30363d")
        self.txt_analytics_log.delete("1.0", "end")
        
        loading_msg = f"⏳ AI is conducting post-mortem evaluation ({selected_lang}) for Trade {selected_label.split(' | ')[0]} ({clean_pair(trade_record[1])})...\n\n"
        self.txt_analytics_log.insert("end", loading_msg)

        def worker():
            review_text = analyzer.analyze_trade_performance(
                image_path=image_path if image_path else "",
                pair=clean_pair(trade_record[1]),
                direction=clean_direction(trade_record[3]),
                entry=trade_record[4],
                sl=trade_record[5],
                tp=trade_record[6],
                status=clean_status(trade_record[8]),
                trade_type=trade_record[12] if len(trade_record) > 12 and trade_record[12] else "N/A",
                language=selected_lang
            )
            
            def update_ui():
                self.txt_analytics_log.delete("1.0", "end")
                self.txt_analytics_log.insert("end", review_text)
                self.btn_run_analytics.configure(text="Run trade review", state="normal", fg_color="#00e6a8")

            if self.winfo_exists():
                self.after(0, update_ui)

        threading.Thread(target=worker, daemon=True).start()

    def run_ai_pasted_chart_review(self):
        try:
            img = ImageGrab.grabclipboard()
            if not isinstance(img, Image.Image):
                messagebox.showwarning("Clipboard Warning", "No image found in clipboard. Please copy a chart screenshot first.")
                return

            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, f"temp_analytics_{int(time.time())}.png")
            img.save(temp_path)

            selected_lang = self.opt_analytics_lang.get()

            self.btn_analytics_paste.configure(text="⏳ Analyzing...", state="disabled", fg_color="#30363d")
            self.txt_analytics_log.delete("1.0", "end")
            self.txt_analytics_log.insert("end", f"⏳ AI is analyzing and rating pasted chart setup ({selected_lang})...\n\n")

            def worker():
                parsed_data = {}
                try:
                    parsed_data = analyzer.analyze_chart(temp_path)
                except Exception as e:
                    print(f"Chart auto-parse error: {e}")

                # Prompt requesting explicit setup rating score (1-10) with explanation
                lang_prompt = "Rate this trade setup on a scale of 1 to 10 (e.g. ⭐ Overall Setup Rating: 8/10) and explain why based on market structure, liquidity, entry quality, and risk management." if selected_lang == "English" else "Beoordeel deze trade setup op een schaal van 1 tot 10 (bijv. ⭐ Overall Setup Rating: 8/10) en leg uit waarom op basis van marktstructuur, liquiditeit, entry-kwaliteit en risicobeheer."

                review_text = analyzer.analyze_trade_performance(
                    image_path=temp_path,
                    pair=clean_pair(parsed_data.get("pair", "")),
                    direction=clean_direction(parsed_data.get("direction", "")),
                    entry=parsed_data.get("entry_price", ""),
                    sl=parsed_data.get("stop_loss", ""),
                    tp=parsed_data.get("take_profit", ""),
                    status=clean_status(parsed_data.get("status", "OPEN")),
                    trade_type=f"{parsed_data.get('trade_type', 'N/A')} - {lang_prompt}",
                    language=selected_lang
                )

                # Clean temporary image right after processing
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except Exception as clean_err:
                    print(f"Cleanup error: {clean_err}")

                def update_ui():
                    self.txt_analytics_log.delete("1.0", "end")
                    self.txt_analytics_log.insert("end", review_text)
                    self.btn_analytics_paste.configure(text="Paste Chart", state="normal", fg_color="#00e6a8")

                if self.winfo_exists():
                    self.after(0, update_ui)

            threading.Thread(target=worker, daemon=True).start()

        except Exception as e:
            self.btn_analytics_paste.configure(text="Paste Chart", state="normal", fg_color="#00e6a8")
            messagebox.showerror("Paste Review Error", f"Failed to analyze pasted chart: {e}")

    # ------------------ CALCULATOR LOGIC & DROPDOWNS ------------------ #
    def toggle_risk_dropdown(self):
        self.show_custom_popup_menu(self.btn_risk_dropdown, ["Risk %", "Cash $"], self.select_risk_mode)

    def select_risk_mode(self, mode):
        self.calc_risk_mode_var = mode
        symbol = "% ∨" if mode == "Risk %" else "$ ∨"
        self.btn_risk_dropdown.configure(text=symbol)
        self.close_dropdown()
        self.run_lot_calculator()
        self.save_calc_settings()

    def select_pair_option(self, pair):
        self.calc_pair_entry.set(pair)
        self.fetch_live_entry_price()

    def fetch_live_entry_price(self):
        pair_text = self.calc_pair_entry.get().strip()
        if pair_text not in TV_SYMBOL_MAP:
            return

        def run_fetch():
            symbol, exchange, screener = TV_SYMBOL_MAP[pair_text]
            try:
                handler = TA_Handler(symbol=symbol, exchange=exchange, screener=screener, interval=Interval.INTERVAL_1_MINUTE)
                analysis = handler.get_analysis()
                price = analysis.indicators.get("close")

                if price is not None:
                    def update_ui():
                        self.calc_entry_price.delete(0, "end")
                        self.calc_entry_price.insert(0, f"{price}")
                        self.run_lot_calculator()

                    if self.winfo_exists():
                        self.after(0, update_ui)
            except Exception as e:
                print(f"TradingView TA error: {e}")

        threading.Thread(target=run_fetch, daemon=True).start()

    def run_lot_calculator(self):
        try:
            balance = float(self.calc_balance_entry.get().replace(",", "").strip())
            risk_input = float(self.calc_risk_entry.get().replace(",", "").strip())
            entry_p = float(self.calc_entry_price.get().replace(",", "").strip())
            sl_p = float(self.calc_sl_price.get().replace(",", "").strip())

            if self.calc_risk_mode_var == "Risk %":
                cash_risk = balance * (risk_input / 100.0)
            else:
                cash_risk = risk_input

            price_diff = abs(entry_p - sl_p)
            if price_diff <= 0:
                self.calc_res_lots.configure(text="0.00 Lots")
                self.calc_res_cash.configure(text="$0.00")
                return

            pair_str = self.calc_pair_entry.get().upper()
            
            if "JPY" in pair_str:
                pip_diff = price_diff * 100.0
                pip_value_per_lot = (1000.0 / entry_p) if entry_p > 0 else 6.7
                lots = cash_risk / (pip_diff * pip_value_per_lot)
            elif "XAU" in pair_str or "GOLD" in pair_str:
                lots = cash_risk / (price_diff * 100.0)
            elif "BTC" in pair_str or "CRYPTO" in pair_str or "ETH" in pair_str:
                lots = cash_risk / price_diff
            else:
                pip_diff = price_diff * 10000.0
                lots = cash_risk / (pip_diff * 10.0)

            self.calc_res_lots.configure(text=f"{max(0.01, round(lots, 2)):.2f} Lots")
            self.calc_res_cash.configure(text=f"${cash_risk:,.2f}")

        except ValueError:
            self.calc_res_lots.configure(text="0.00 Lots")
            self.calc_res_cash.configure(text="$0.00")

    # ------------------ FORM & IMAGE ACTIONS ------------------ #
    def paste_image(self):
        try:
            img = ImageGrab.grabclipboard()
            if isinstance(img, Image.Image):
                temp_dir = tempfile.gettempdir()
                self.selected_image_path = os.path.join(temp_dir, "pasted_chart.png")
                img.save(self.selected_image_path)
                
                # Show preview image
                preview_img = img.copy()
                preview_img.thumbnail((330, 130))
                self.current_preview_image = ctk.CTkImage(light_image=preview_img, dark_image=preview_img, size=preview_img.size)
                self.img_preview.configure(image=self.current_preview_image, text="")

                # Set dynamic button state to Analyzing
                self.btn_paste.configure(text="⏳ Analyzing...", state="disabled", fg_color="#30363d")

                def run_analysis():
                    try:
                        res = analyzer.analyze_chart(self.selected_image_path)
                        if self.winfo_exists():
                            self.after(0, lambda: self.populate_form(res))
                    except Exception as err:
                        # Clean raw error string so message box displays plain text
                        clean_err = RE_MARKDOWN_LINK.sub(r'\1', str(err)).replace("[", "").replace("]", "").replace("(", "").replace(")", "")
                        
                        def reset_on_err(msg=clean_err):
                            self.btn_paste.configure(text="Paste Chart", state="normal", fg_color="#00e6a8")
                            messagebox.showerror("Analysis Error", msg)

                        if self.winfo_exists():
                            self.after(0, reset_on_err)

                threading.Thread(target=run_analysis, daemon=True).start()
            else:
                messagebox.showwarning("Clipboard Warning", "No image found in clipboard. Please copy a chart screenshot first.")
        except Exception as e:
            messagebox.showerror("Clipboard Error", f"Failed to grab image: {e}")

    def reset_analyzer_form(self):
        self.selected_image_path = None
        self.current_preview_image = None
        self.img_preview.configure(image="", text="No Screenshot Pasted Yet")

        for entry in (self.entry_pair, self.entry_tf, self.entry_direction, self.entry_entry, 
                      self.entry_sl, self.entry_tp, self.entry_rr, 
                      self.entry_notes):
            entry.delete(0, "end")
            
        self.opt_status.set("")
        self.opt_type.set("")

    def populate_form(self, data):
        for entry in (self.entry_pair, self.entry_tf, self.entry_direction, self.entry_entry, 
                      self.entry_sl, self.entry_tp, self.entry_rr, 
                      self.entry_notes):
            entry.delete(0, "end")

        self.entry_pair.insert(0, clean_pair(data.get("pair", "")))
        self.entry_tf.insert(0, format_timeframe(data.get("timeframe", "")))
        self.entry_direction.insert(0, clean_direction(data.get("direction", "")))
        self.entry_entry.insert(0, data.get("entry_price", ""))
        self.entry_sl.insert(0, data.get("stop_loss", ""))
        self.entry_tp.insert(0, data.get("take_profit", ""))
        self.entry_rr.insert(0, data.get("rr_ratio", ""))
        
        # Keep Status and Type blank so the form stays clear for manual selection
        self.opt_status.set("")
        self.opt_type.set("")

        self.btn_paste.configure(text="Paste Chart", state="normal", fg_color="#00e6a8")

    def calculate_live_rr(self, event=None):
        try:
            e = float(self.entry_entry.get().replace(",", "").strip())
            sl = float(self.entry_sl.get().replace(",", "").strip())
            tp = float(self.entry_tp.get().replace(",", "").strip())

            risk = abs(e - sl)
            reward = abs(tp - e)

            if risk > 0:
                self.entry_rr.delete(0, "end")
                self.entry_rr.insert(0, f"1:{reward / risk:.2f}")
        except ValueError:
            pass

    def save_trade(self):
        if not self.selected_image_path or not os.path.exists(self.selected_image_path):
            messagebox.showwarning("Validation Error", "Cannot save trade without an analyzed chart screenshot. Please paste and analyze a chart first.")
            return

        payload = {
            "pair": clean_pair(self.entry_pair.get()),
            "timeframe": self.entry_tf.get(),
            "direction": self.entry_direction.get(),
            "entry_price": self.entry_entry.get(),
            "stop_loss": self.entry_sl.get(),
            "take_profit": self.entry_tp.get(),
            "rr_ratio": self.entry_rr.get(),
            "status": clean_status(self.opt_status.get()),
            "notes": self.entry_notes.get(),
            "trade_type": self.opt_type.get()
        }

        # Match screenshot filename ID directly with new trade ID (oldest = 1, newest = total trades + 1)
        existing_records = db.fetch_all_trades()
        new_trade_id = len(existing_records) + 1
        filename = f"chart_{new_trade_id}.png"
        dest = os.path.join(self.saved_images_dir, filename)
        shutil.copy(self.selected_image_path, dest)
        payload["image_path"] = dest

        success, msg = db.add_trade(payload)
        if success:
            self.reset_analyzer_form()
            self.load_database_records()
        else:
            messagebox.showerror("Database Error", f"Failed to save trade: {msg}")

    def load_database_records(self):
        records = db.fetch_all_trades()
        total_trades = len(records)

        for item in self.tree_dash.get_children():
            self.tree_dash.delete(item)
        for item in self.tree_trades.get_children():
            self.tree_trades.delete(item)

        total_wins = 0
        total_closed = 0
        total_rr = 0.0

        setup_wins = defaultdict(int)
        setup_total = defaultdict(int)

        for idx, r in enumerate(records):
            db_id = r[0]
            display_id = total_trades - idx  # Chronological trade ID: 1 for oldest, total_trades for newest
            tf_val = format_timeframe(r[2])
            trade_type_val = r[12] if len(r) > 12 and r[12] else "HnS"
            date_val = str(r[9])[:10] if len(str(r[9])) > 10 else r[9]

            display_row = [
                display_id, clean_pair(r[1]), tf_val, clean_direction(r[3]), r[4], r[5], r[6], r[7],
                clean_status(r[8]), trade_type_val, date_val
            ]

            self.tree_trades.insert("", "end", values=display_row, tags=(str(db_id),))
            self.tree_dash.insert("", "end", values=display_row, tags=(str(db_id),))

            status = clean_status(r[8])
            if status in ["TP", "SL"]:
                total_closed += 1
                setup_key = f"{trade_type_val} • {tf_val}" if tf_val else trade_type_val
                setup_total[setup_key] += 1

                if status == "TP":
                    total_wins += 1
                    setup_wins[setup_key] += 1

                try:
                    rr_val = float(str(r[7]).replace("1:", ""))
                    total_rr += rr_val
                except ValueError:
                    pass

        winrate = (total_wins / total_closed * 100) if total_closed > 0 else 0.0
        avg_rr = (total_rr / total_closed) if total_closed > 0 else 0.0

        best_setup_str = "N/A"
        best_rate = -1.0
        max_tp_count = -1

        for setup, total_count in setup_total.items():
            if total_count > 0:
                wins = setup_wins[setup]
                rate = (wins / total_count) * 100.0
                if rate > best_rate or (rate == best_rate and wins > max_tp_count):
                    best_rate = rate
                    max_tp_count = wins
                    best_setup_str = f"{setup} / {rate:.1f}%"

        self.card_winrate_val.configure(text=f"{winrate:.1f}%")
        self.card_rr_val.configure(text=f"1:{avg_rr:.2f}")
        self.card_best_trade_val.configure(text=best_setup_str)

    # ------------------ CONTEXT MENUS & TRADE DIALOGS ------------------ #
    def show_dash_context_menu(self, event, tree):
        item = tree.identify_row(event.y)
        if item:
            tree.selection_set(item)
            self.dash_context_menu.post(event.x_root, event.y_root)

    def show_trades_context_menu(self, event, tree):
        item = tree.identify_row(event.y)
        if item:
            current_selection = tree.selection()
            if item not in current_selection:
                tree.selection_set(item)
            self.trades_context_menu.post(event.x_root, event.y_root)

    def delete_selected(self):
        active_tree = self.tree_trades if self.current_active_view == "Trades" else self.tree_dash
        selected_items = active_tree.selection()
        if not selected_items:
            return

        trade_ids = []
        for sel in selected_items:
            item = active_tree.item(sel)
            tags = item.get("tags", [])
            raw_id = tags[0] if tags else item["values"][0]
            try:
                trade_ids.append(int(raw_id))
            except (ValueError, TypeError):
                continue

        if not trade_ids:
            return

        msg = f"Are you sure you want to delete these {len(trade_ids)} trades from your journal?" if len(trade_ids) > 1 else "Are you sure you want to delete this trade from your journal?"

        if messagebox.askyesno("Confirm Delete", msg):
            for tid in trade_ids:
                db.delete_trade(tid)
            self.load_database_records()

    def modify_selected_trade(self):
        active_tree = self.tree_trades if self.current_active_view == "Trades" else self.tree_dash
        selected = active_tree.selection()
        if not selected:
            return

        item = active_tree.item(selected[0])
        tags = item.get("tags", [])
        trade_id = int(tags[0]) if tags else int(item["values"][0])
        values = item["values"]

        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Modify Trade (ID: {values[0]})")
        dialog.geometry("440x480")
        dialog.configure(fg_color="#0d1117")
        dialog.transient(self)
        dialog.focus_force()

        fields = {}
        labels = ["Pair", "Timeframe", "Direction", "Entry", "SL", "TP"]
        val_map = {
            "Pair": clean_pair(values[1]), "Timeframe": values[2], "Direction": values[3],
            "Entry": values[4], "SL": values[5], "TP": values[6]
        }

        for lbl in labels:
            row = ctk.CTkFrame(dialog, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(row, text=f"{lbl}:", width=110, anchor="w", text_color="#8b949e", font=ctk.CTkFont(size=13)).pack(side="left")
            ent = ctk.CTkEntry(row, fg_color="#161b22", text_color="#f0f6fc", font=ctk.CTkFont(size=13))
            ent.pack(side="right", expand=True, fill="x")
            ent.insert(0, str(val_map[lbl]))
            fields[lbl] = ent

        # Status Dropdown identical to Analyzer
        row_s = ctk.CTkFrame(dialog, fg_color="transparent")
        row_s.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(row_s, text="Status:", width=110, anchor="w", text_color="#8b949e", font=ctk.CTkFont(size=13)).pack(side="left")

        opt_status_mod = CustomDropdownButton(
            row_s,
            ["OPEN", "TP", "SL"],
            clean_status(values[8]),
            app_instance=self,
            height=29
        )
        opt_status_mod.pack(side="right", expand=True, fill="x")

        # Type Dropdown
        row_t = ctk.CTkFrame(dialog, fg_color="transparent")
        row_t.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(row_t, text="Type:", width=110, anchor="w", text_color="#8b949e", font=ctk.CTkFont(size=13)).pack(side="left")
        
        opt_type_mod = CustomDropdownButton(
            row_t,
            ["HnS", "i HnS", "FVG", "S & R", "Breakout"],
            str(values[9]) if len(values) > 9 else "",
            app_instance=self,
            height=29
        )
        opt_type_mod.pack(side="right", expand=True, fill="x")

        row_n = ctk.CTkFrame(dialog, fg_color="transparent")
        row_n.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(row_n, text="Notes:", width=110, anchor="w", text_color="#8b949e", font=ctk.CTkFont(size=13)).pack(side="left")
        ent_notes = ctk.CTkEntry(row_n, fg_color="#161b22", text_color="#f0f6fc", font=ctk.CTkFont(size=13))
        ent_notes.pack(side="right", expand=True, fill="x")

        def update():
            updated_data = {
                "pair": clean_pair(fields["Pair"].get()),
                "timeframe": fields["Timeframe"].get(),
                "direction": fields["Direction"].get(),
                "entry_price": fields["Entry"].get(),
                "stop_loss": fields["SL"].get(),
                "take_profit": fields["TP"].get(),
                "status": clean_status(opt_status_mod.get()),
                "notes": ent_notes.get(),
                "trade_type": opt_type_mod.get()
            }
            db.update_trade(trade_id, updated_data)
            dialog.destroy()
            self.load_database_records()

        btn_save = ctk.CTkButton(dialog, text="Save Changes", fg_color="#00e6a8", hover_color="#00c993", text_color="#0d1117", font=ctk.CTkFont(size=13, weight="bold"), command=update)
        btn_save.pack(fill="x", padx=20, pady=16)

    def on_trade_double_click(self, event=None):
        tree = event.widget if event and hasattr(event, "widget") else self.tree_trades
        selected = tree.selection()
        if not selected:
            return

        item = tree.item(selected[0])
        tags = item.get("tags", [])
        raw_id = tags[0] if tags else item["values"][0]
        display_id = item["values"][0]

        try:
            trade_id = int(raw_id)
        except (ValueError, TypeError):
            messagebox.showerror("Error", f"Invalid trade ID: {raw_id}")
            return

        image_path = db.get_trade_image_path(trade_id)

        if image_path and os.path.exists(image_path):
            img_window = ctk.CTkToplevel(self)
            img_window.title(f"Chart Screenshot - Trade #{display_id}")
            
            # Ensure window icon matches main application icon
            icon_file = resource_path("icon.ico")
            if os.path.exists(icon_file):
                img_window.iconbitmap(icon_file)

            img_window.geometry("1200x800")
            img_window.configure(fg_color="#0d1117")
            img_window.resizable(True, True)
            img_window.transient(self)
            img_window.focus_force()

            with Image.open(image_path) as orig_pil_img:
                pil_img = orig_pil_img.copy()

            orig_width, orig_height = pil_img.size

            canvas = tk.Canvas(img_window, bg="#0d1117", highlightthickness=0)
            canvas.pack(fill="both", expand=True)

            zoom_state = {"scale": 1.0, "x": 0, "y": 0, "image_id": None, "photo": None}

            def render_scaled_image():
                win_w = max(canvas.winfo_width(), 100)
                win_h = max(canvas.winfo_height(), 100)
                
                base_scale = min(win_w / orig_width, win_h / orig_height)
                effective_scale = base_scale * zoom_state["scale"]
                
                new_w = max(10, int(orig_width * effective_scale))
                new_h = max(10, int(orig_height * effective_scale))
                
                resized = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                zoom_state["photo"] = ImageTk.PhotoImage(resized)
                
                canvas.delete("all")
                zoom_state["image_id"] = canvas.create_image(
                    win_w // 2 + zoom_state["x"], 
                    win_h // 2 + zoom_state["y"], 
                    image=zoom_state["photo"], 
                    anchor="center"
                )

            def on_resize(e):
                render_scaled_image()

            def on_zoom(event):
                if event.delta > 0 or event.num == 4:
                    zoom_state["scale"] *= 1.15
                elif event.delta < 0 or event.num == 5:
                    zoom_state["scale"] = max(0.2, zoom_state["scale"] / 1.15)
                render_scaled_image()

            pan_start = {"x": 0, "y": 0}

            def start_pan(event):
                pan_start["x"] = event.x
                pan_start["y"] = event.y

            def do_pan(event):
                dx = event.x - pan_start["x"]
                dy = event.y - pan_start["y"]
                zoom_state["x"] += dx
                zoom_state["y"] += dy
                pan_start["x"] = event.x
                pan_start["y"] = event.y
                render_scaled_image()

            canvas.bind("<Configure>", on_resize)
            canvas.bind("<MouseWheel>", on_zoom)
            canvas.bind("<Button-4>", on_zoom)
            canvas.bind("<Button-5>", on_zoom)
            canvas.bind("<ButtonPress-3>", start_pan)
            canvas.bind("<B3-Motion>", do_pan)
            canvas.bind("<ButtonPress-1>", start_pan)
            canvas.bind("<B1-Motion>", do_pan)
        else:
            messagebox.showinfo("Image Viewer", f"No screenshot image stored for Trade #{display_id}.")

if __name__ == "__main__":
    app = TradingJournalApp()
    app.mainloop()