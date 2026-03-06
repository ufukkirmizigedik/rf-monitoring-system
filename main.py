#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import signal
import time
import queue
import threading
import subprocess
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from datetime import datetime, timedelta

# ---------- Seriyal No Kontrolü ----------
import subprocess as _sp

def get_serial():
    try:
        out = _sp.check_output(
            "cat /proc/cpuinfo | grep -i '^Serial'", shell=True
        ).decode()
        return out.strip().split(":")[1].strip()
    except Exception:
        return None

AUTHORIZED_SERIAL = None  # Set your Raspberry Pi serial number here
if get_serial() != AUTHORIZED_SERIAL:
    print("⛔ Неразрешённое устройство! Запуск заблокирован.")
    raise SystemExit(1)

# ---------- Sabitler ve Yardımcılar ----------
ALPHA_FREQ = 0.4
BETA_PWR = 0.5
LOG_RATE_MS = 100

NUM_RE = re.compile(r"^[+-]?\d+$")
FLT_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")

HISTORY_DIR = os.path.expanduser("~/.local/share/efir_history")
os.makedirs(HISTORY_DIR, exist_ok=True)
MAX_HISTORY_DAYS = 5

def cleanup_history():
    try:
        now = datetime.now().date()
        for name in os.listdir(HISTORY_DIR):
            if not name.startswith("history_") or not name.endswith(".csv"):
                continue
            date_str = name[len("history_"):-4]
            try:
                d = datetime.strptime(date_str, "%Y%m%d").date()
            except Exception:
                continue
            if (now - d).days >= MAX_HISTORY_DAYS:
                try:
                    os.remove(os.path.join(HISTORY_DIR, name))
                except:
                    pass
    except:
        pass

def parts_are_valid(parts):
    if len(parts) < 7:
        return False
    if ("sweeps/second" in parts[0]) or (len(parts) > 1 and "sweeps/second" in parts[1]):
        return False
    return True

# ---------- GPIO Röle Sınıfı ----------
try:
    import RPi.GPIO as GPIO
except Exception:
    class MockGPIO:
        BCM=1; OUT=0; IN=1; LOW=0; HIGH=1
        def setwarnings(self, s): pass
        def setmode(self, m): pass
        def setup(self, p, m, initial=0): pass
        def output(self, p, v): pass
        def cleanup(self, p): pass
    GPIO = MockGPIO()

class OpenDrainRelay:
    def __init__(self, bcm_pin=17):
        self.pin = bcm_pin
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        self.off()

    def on(self):
        GPIO.setup(self.pin, GPIO.OUT, initial=GPIO.LOW)
        GPIO.output(self.pin, GPIO.LOW)

    def off(self):
        GPIO.setup(self.pin, GPIO.IN)

    def close(self):
        try:
            self.off()
        except:
            pass
        try:
            GPIO.cleanup(self.pin)
        except:
            pass

# ---------- Renk Teması ----------
THEME = {
    "BG_MAIN": "#1e2530",
    "BG_PANEL": "#282c34",
    "BG_INPUT": "#15181e",
    "FG_TEXT": "#abb2bf",
    "FG_HEADER": "#e5c07b",
    "ACCENT_GREEN": "#98c379",
    "ACCENT_RED": "#e06c75",
    "ACCENT_CYAN": "#56b6c2",
    "ACCENT_ORANGE": "#d19a66", # Reset butonu için
    "BTN_BG": "#3b4048",
    "BTN_ACT": "#4b5263"
}

# ---------- Fullscreen hard-fix helper ----------
def apply_fullscreen_exact(win: tk.Tk):
    try:
        win.update_idletasks()
        w = win.winfo_screenwidth()
        h = win.winfo_screenheight()
        win.geometry(f"{w}x{h}+0+0")
        win.attributes("-fullscreen", True)
        win.update_idletasks()
        win.geometry(f"{w}x{h}+0+0")
    except:
        pass

# ---------- AYARLAR PENCERESİ ----------
def run_settings_then_launch():
    cleanup_history()

    default_ranges = [
        {"active": True,  "start": 400.0,  "end": 500.0},
        {"active": False, "start": 1200.0, "end": 1300.0},
        {"active": False, "start": 2400.0, "end": 2500.0},
        {"active": False, "start": 5700.0, "end": 5900.0},
    ]

    cfg = {
        "RANGES": default_ranges,
        "THRESHOLD_DB": -40.0,
        "TREND_K": 3,
        "RELAY_HOLD_SEC": 5,
        "FREQ_TOL_MHZ_MIN": 5.0,
    }

    sroot = tk.Tk()
    sroot.title("Настройки системы")
    sroot.configure(bg=THEME["BG_MAIN"])

    apply_fullscreen_exact(sroot)

    FONT_LBL = ("Arial", 12)
    FONT_INP = ("Arial", 14, "bold")
    FONT_BTN = ("Arial", 14, "bold")
    FONT_HDR = ("Arial", 16, "bold")

    main_frame = tk.Frame(sroot, bg=THEME["BG_MAIN"])
    main_frame.pack(fill="both", expand=True, padx=20, pady=20)

    tk.Label(main_frame, text="НАСТРОЙКИ СИСТЕМЫ (RF SCANNER)",
             bg=THEME["BG_MAIN"], fg=THEME["FG_HEADER"], font=FONT_HDR).pack(pady=(0, 20))

    content_frame = tk.Frame(main_frame, bg=THEME["BG_MAIN"])
    content_frame.pack(fill="both", expand=True)

    # Sol Taraf
    left_frame = tk.Frame(content_frame, bg=THEME["BG_PANEL"], bd=1, relief="ridge")
    left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

    tk.Label(left_frame, text="Целевые диапазоны частот (MHz)",
             bg=THEME["BG_PANEL"], fg="white", font=FONT_LBL).grid(row=0, column=0, columnspan=4, pady=10)

    headers = ["Вкл", "Старт (MHz)", "Конец (MHz)"]
    for c, h in enumerate(headers):
        tk.Label(left_frame, text=h, bg=THEME["BG_PANEL"], fg=THEME["FG_TEXT"],
                 font=("Arial", 10)).grid(row=1, column=c+1, pady=5)

    range_vars = []

    def validate_float(P):
        if P == "" or P == "-": return True
        try: float(P); return True
        except ValueError: return False
    vcmd = (sroot.register(validate_float), '%P')

    for i in range(4):
        tk.Label(left_frame, text=f"#{i+1}", bg=THEME["BG_PANEL"],
                 fg=THEME["ACCENT_CYAN"], font=FONT_LBL).grid(row=i+2, column=0, padx=5, pady=5)

        var_act = tk.BooleanVar(value=cfg["RANGES"][i]["active"])
        chk = tk.Checkbutton(left_frame, variable=var_act,
                             bg=THEME["BG_PANEL"], activebackground=THEME["BG_PANEL"],
                             selectcolor="white", bd=0)
        chk.grid(row=i+2, column=1)

        e_start = tk.Entry(left_frame, width=8, bg=THEME["BG_INPUT"], fg="white",
                           font=FONT_INP, insertbackground="white", justify="center",
                           validate="key", validatecommand=vcmd)
        e_start.insert(0, str(cfg["RANGES"][i]["start"]))
        e_start.grid(row=i+2, column=2, padx=5, pady=10)

        e_end = tk.Entry(left_frame, width=8, bg=THEME["BG_INPUT"], fg="white",
                         font=FONT_INP, insertbackground="white", justify="center",
                         validate="key", validatecommand=vcmd)
        e_end.insert(0, str(cfg["RANGES"][i]["end"]))
        e_end.grid(row=i+2, column=3, padx=5, pady=10)

        range_vars.append((var_act, e_start, e_end))

    param_frame = tk.Frame(left_frame, bg=THEME["BG_PANEL"])
    param_frame.grid(row=7, column=0, columnspan=4, sticky="ew", pady=20, padx=10)

    tk.Label(param_frame, text="Порог (dB):", bg=THEME["BG_PANEL"], fg=THEME["FG_TEXT"],
             font=FONT_LBL).grid(row=0, column=0, sticky="e")
    e_thresh = tk.Entry(param_frame, width=6, bg=THEME["BG_INPUT"], fg="white",
                        font=FONT_INP, justify="center")
    e_thresh.insert(0, str(cfg["THRESHOLD_DB"]))
    e_thresh.grid(row=0, column=1, padx=5)

    tk.Label(param_frame, text="Тренд (K):", bg=THEME["BG_PANEL"], fg=THEME["FG_TEXT"],
             font=FONT_LBL).grid(row=0, column=2, sticky="e")
    e_k = tk.Entry(param_frame, width=6, bg=THEME["BG_INPUT"], fg="white",
                   font=FONT_INP, justify="center")
    e_k.insert(0, str(cfg["TREND_K"]))
    e_k.grid(row=0, column=3, padx=5)

    tk.Label(param_frame, text="Реле (сек):", bg=THEME["BG_PANEL"], fg=THEME["FG_TEXT"],
             font=FONT_LBL).grid(row=0, column=4, sticky="e")
    e_hold = tk.Entry(param_frame, width=6, bg=THEME["BG_INPUT"], fg="white",
                      font=FONT_INP, justify="center")
    e_hold.insert(0, str(cfg["RELAY_HOLD_SEC"]))
    e_hold.grid(row=0, column=5, padx=5)

    info_text = (
        "Подсказка: Система ищет устойчивый рост мощности сигнала (K измерений).\n"
        "Если сигнал в выбранном диапазоне растет K раз подряд выше порога — срабатывает реле."
    )
    lbl_info = tk.Label(left_frame, text=info_text, bg=THEME["BG_PANEL"], fg="#7f848e",
                        font=("Arial", 10, "italic"), justify="left", wraplength=450)
    lbl_info.grid(row=8, column=0, columnspan=4, pady=20, sticky="w", padx=10)

    # Sağ Taraf (Klavye)
    right_frame = tk.Frame(content_frame, bg=THEME["BG_MAIN"], width=300)
    right_frame.pack(side="right", fill="y")

    kb_frame = tk.Frame(right_frame, bg=THEME["BG_MAIN"])
    kb_frame.pack(pady=10)

    def _focused_entry():
        w = sroot.focus_get()
        return w if isinstance(w, tk.Entry) else None

    def _ins(t):
        e = _focused_entry()
        if e: e.insert(tk.INSERT, t)

    def _backspace():
        e = _focused_entry()
        if e:
            pos = e.index(tk.INSERT)
            if pos > 0: e.delete(pos-1)

    keys = [('7', '8', '9'), ('4', '5', '6'), ('1', '2', '3'), ('.', '0', '-')]
    for row_keys in keys:
        row_f = tk.Frame(kb_frame, bg=THEME["BG_MAIN"])
        row_f.pack()
        for k in row_keys:
            tk.Button(row_f, text=k, command=lambda x=k: _ins(x),
                      bg=THEME["BTN_BG"], fg="white", activebackground=THEME["BTN_ACT"],
                      font=("Arial", 18, "bold"), width=4, height=1, bd=0).pack(side="left", padx=2, pady=2)

    tk.Button(kb_frame, text="⌫ Backspace", command=_backspace,
              bg="#d19a66", fg="black", font=("Arial", 12, "bold"), width=14, bd=0).pack(pady=5)

    def save_and_exit():
        new_ranges = []
        for i in range(4):
            v_act, v_s, v_e = range_vars[i]
            try:
                s_val = float(v_s.get().strip())
                e_val = float(v_e.get().strip())
                if s_val > e_val: s_val, e_val = e_val, s_val
                new_ranges.append({"active": v_act.get(), "start": s_val, "end": e_val})
            except:
                new_ranges.append(cfg["RANGES"][i])
        cfg["RANGES"] = new_ranges
        try:
            cfg["THRESHOLD_DB"] = float(e_thresh.get())
            cfg["TREND_K"] = int(e_k.get())
            cfg["RELAY_HOLD_SEC"] = int(e_hold.get())
        except: pass
        sroot.destroy()
        launch_main(cfg)

    tk.Button(right_frame, text="СОХРАНИТЬ И ЗАПУСК", command=save_and_exit,
              bg=THEME["ACCENT_GREEN"], fg="black", font=FONT_BTN,
              height=2, width=20, bd=0).pack(side="bottom", pady=10)

    tk.Button(right_frame, text="ВЫХОД", command=sroot.destroy,
              bg=THEME["ACCENT_RED"], fg="black", font=FONT_BTN,
              height=1, width=20, bd=0).pack(side="bottom", pady=5)

    sroot.mainloop()

# ---------- ANA UYGULAMA ----------
def launch_main(cfg):
    relay = OpenDrainRelay(17)

    relay_state = {"v": False}
    relay_timer = {"t": None}
    state_lock = threading.Lock()

    proc = {"p": None}
    running = {"v": False}
    last_line_ts = {"v": 0.0}

    freq_stats = {}
    freq_stats_lock = threading.Lock()

    active_ranges = [r for r in cfg["RANGES"] if r["active"]]
    if not active_ranges:
        active_ranges = [{"active": True, "start": 100.0, "end": 6000.0}]

    global_start = min(r["start"] for r in active_ranges)
    global_end = max(r["end"] for r in active_ranges)
    if global_end - global_start < 10: global_end = global_start + 10

    def is_in_active_range(mhz):
        for r in active_ranges:
            if r["start"] <= mhz <= r["end"]: return True
        return False

    root = tk.Tk()
    root.title("RF MONITORING SYSTEM")
    root.configure(bg=THEME["BG_MAIN"])

    apply_fullscreen_exact(root)

    top_frame = tk.Frame(root, bg=THEME["BG_PANEL"], height=200)
    top_frame.pack(side="top", fill="x", padx=10, pady=10)
    top_frame.pack_propagate(False)

    bottom_frame = tk.Frame(root, bg=THEME["BG_MAIN"])
    bottom_frame.pack(side="bottom", fill="both", expand=True, padx=10, pady=(0, 10))

    dash_left = tk.Frame(top_frame, bg=THEME["BG_PANEL"])
    dash_left.pack(side="left", fill="both", expand=True)

    tk.Label(dash_left, text="ПОСЛЕДНИЙ СИГНАЛ (LAST DETECTED)",
             bg=THEME["BG_PANEL"], fg=THEME["FG_TEXT"], font=("Arial", 10)).pack(pady=(10, 0))

    lbl_detect_val = tk.Label(dash_left, text="--- MHz",
                              bg=THEME["BG_PANEL"], fg="white", font=("Arial", 42, "bold"))
    lbl_detect_val.pack(expand=True)

    lbl_detect_db = tk.Label(dash_left, text="-- dB",
                             bg=THEME["BG_PANEL"], fg=THEME["ACCENT_CYAN"], font=("Arial", 24, "bold"))
    lbl_detect_db.pack(pady=(0, 10))

    dash_right = tk.Frame(top_frame, bg=THEME["BG_PANEL"], width=260)
    dash_right.pack(side="right", fill="y", padx=10)
    dash_right.pack_propagate(False)

    lbl_status_text = tk.Label(dash_right, text="РЕЛЕ: ОТКЛ",
                               bg=THEME["ACCENT_RED"], fg="white", font=("Arial", 16, "bold"))
    lbl_status_text.pack(fill="x", pady=10, ipady=10)

    log_q = queue.Queue(maxsize=2000)

    def qlog(msg, tag="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        try: log_q.put_nowait((f"[{ts}] {msg}", tag))
        except: pass

    frame_logs = tk.Frame(bottom_frame, bg="black")
    frame_logs.pack(side="left", fill="both", expand=True)

    frame_ctrl = tk.Frame(bottom_frame, bg=THEME["BG_MAIN"], width=240)
    frame_ctrl.pack(side="right", fill="y", padx=(10, 0))
    frame_ctrl.pack_propagate(False)

    log_area = ScrolledText(frame_logs, font=("Consolas", 12), bg="#0f111a", fg="#a0a8b7", bd=0)
    log_area.pack(fill="both", expand=True)
    log_area.tag_config("trigger", foreground=THEME["ACCENT_GREEN"])
    log_area.tag_config("signal", foreground="#d19a66")
    log_area.tag_config("error", foreground=THEME["ACCENT_RED"])

    def pump_logs():
        processed = 0
        while processed < 80:
            try: line, tag = log_q.get_nowait()
            except queue.Empty: break
            log_area.insert(tk.END, line + "\n", tag)
            processed += 1
        if processed: log_area.see(tk.END)
        root.after(LOG_RATE_MS, pump_logs)

    # --- RAPORLAMA ---
    def load_history_rows():
        rows = []
        now = datetime.now().date()
        for i in range(MAX_HISTORY_DAYS):
            d = now - timedelta(days=i)
            fname = f"history_{d.strftime('%Y%m%d')}.csv"
            fpath = os.path.join(HISTORY_DIR, fname)
            if not os.path.exists(fpath): continue
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    for line in f:
                        parts = line.strip().split(";")
                        if len(parts) < 3: continue
                        triggered = False
                        if len(parts) >= 4: triggered = (parts[3] == "1")
                        rows.append((parts[0], float(parts[1]), float(parts[2]), triggered))
            except: pass
        rows.sort(key=lambda x: x[0], reverse=True)
        return rows

    def show_report():
        if running["v"]: stop_sys()

        with freq_stats_lock: curr_items = list(freq_stats.items())
        hist_rows = load_history_rows()

        freq_hist = {}
        for dt_str, mhz, db, trig in hist_rows:
            key = round(mhz, 3)
            st = freq_hist.get(key)
            if not st: freq_hist[key] = {"cnt": 1, "max": db, "last": dt_str, "trig": trig}
            else:
                st["cnt"] += 1
                st["max"] = max(st["max"], db)
                if dt_str > st["last"]: st["last"] = dt_str
                if trig: st["trig"] = True

        win = tk.Toplevel(root)
        win.title("ОТЧЁТ")
        win.configure(bg=THEME["BG_MAIN"])
        win.geometry("900x600")

        win.transient(root)
        win.lift()
        win.focus_force()
        win.attributes("-topmost", True)
        win.after(200, lambda: win.attributes("-topmost", False))
        win.grab_set()

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        def create_tree(parent, data_source):
            fr = tk.Frame(parent, bg=THEME["BG_PANEL"])
            fr.pack(fill="both", expand=True)
            cols = ("dt", "freq", "db", "cnt")
            tree = ttk.Treeview(fr, columns=cols, show="headings")
            tree.heading("dt", text="Время")
            tree.heading("freq", text="Частота (MHz)")
            tree.heading("db", text="Max dB")
            tree.heading("cnt", text="Кол-во")
            tree.column("dt", width=220, anchor="center")
            tree.column("freq", width=140, anchor="center")
            tree.column("db", width=120, anchor="center")
            tree.column("cnt", width=100, anchor="center")
            tree.pack(side="left", fill="both", expand=True)
            sb = tk.Scrollbar(fr, orient="vertical", command=tree.yview)
            sb.pack(side="right", fill="y")
            tree.configure(yscrollcommand=sb.set)
            tree.tag_configure("trig", foreground="green")

            if data_source == 'curr':
                items = sorted(curr_items, key=lambda x: x[1]['max_db'], reverse=True)
            else:
                items = sorted(freq_hist.items(), key=lambda x: x[1]['max'], reverse=True)

            for key, v in items:
                if data_source == 'curr':
                    vals = (v['last_dt'].strftime("%H:%M:%S"), f"{v['mhz']:.3f}", f"{v['max_db']:.1f}", v['count'])
                    tg = ("trig",) if v['trig'] else ()
                else:
                    vals = (v['last'], f"{key:.3f}", f"{v['max']:.1f}", v['cnt'])
                    tg = ("trig",) if v['trig'] else ()
                tree.insert("", "end", values=vals, tags=tg)

        t1 = tk.Frame(nb)
        nb.add(t1, text="Текущая сессия")
        create_tree(t1, 'curr')

        t2 = tk.Frame(nb)
        nb.add(t2, text="История (5 дней)")
        create_tree(t2, 'hist')

        def close_report():
            try: win.grab_release()
            except: pass
            win.destroy()

        tk.Button(win, text="ЗАКРЫТЬ", command=close_report,
                  bg=THEME["BTN_BG"], fg="white", font=("Arial", 12, "bold"),
                  height=2).pack(fill="x", padx=10, pady=(0, 10))

    # --- LOGIC ---
    def update_dashboard_trigger(mhz, db, is_on):
        lbl_detect_val.config(text=f"{mhz:.3f} MHz")
        lbl_detect_db.config(text=f"{db:.1f} dB")
        if is_on:
            lbl_detect_val.config(fg=THEME["ACCENT_GREEN"], bg="#1c3323")
            lbl_detect_db.config(bg="#1c3323")
            dash_left.config(bg="#1c3323")
        else:
            lbl_detect_val.config(fg="white", bg=THEME["BG_PANEL"])
            lbl_detect_db.config(bg=THEME["BG_PANEL"])
            dash_left.config(bg=THEME["BG_PANEL"])

    def set_relay_visual(on):
        if on:
            lbl_status_text.config(text="РЕЛЕ: ВКЛ", bg=THEME["ACCENT_GREEN"])
        else:
            lbl_status_text.config(text="РЕЛЕ: ОТКЛ", bg=THEME["ACCENT_RED"])
            dash_left.config(bg=THEME["BG_PANEL"])
            lbl_detect_val.config(bg=THEME["BG_PANEL"])
            lbl_detect_db.config(bg=THEME["BG_PANEL"])

    def _accumulate_freq(trig_hz, peak, bin_hz):
        key_hz = int(round(trig_hz / bin_hz) * bin_hz)
        mhz = key_hz / 1e6
        now = datetime.now()
        with freq_stats_lock:
            st = freq_stats.get(key_hz)
            if st is None:
                freq_stats[key_hz] = {"count": 1, "max_db": peak, "mhz": mhz, "last_dt": now, "trig": False}
            else:
                st["count"] += 1
                st["max_db"] = max(st["max_db"], peak)
                st["last_dt"] = now

    def _mark_trigger_session(mhz):
        with freq_stats_lock:
            best_key = None; best_df = None
            for key_hz, st in freq_stats.items():
                df = abs(st["mhz"] - mhz)
                if best_df is None or df < best_df:
                    best_df = df; best_key = key_hz
            if best_key: freq_stats[best_key]["trig"] = True

    hist_lock = threading.Lock()
    def _append_history(mhz, db, triggered):
        try:
            now = datetime.now()
            fname = f"history_{now.strftime('%Y%m%d')}.csv"
            fpath = os.path.join(HISTORY_DIR, fname)
            line = f"{now.strftime('%Y-%m-%d %H:%M:%S')};{mhz:.6f};{db:.1f};{1 if triggered else 0}\n"
            with hist_lock:
                with open(fpath, "a", encoding="utf-8") as f: f.write(line)
        except: pass

    def auto_on(mhz, peak_db):
        with state_lock:
            t_old = relay_timer.get("t")
            if t_old:
                try: t_old.cancel()
                except: pass

            update_dashboard_trigger(mhz, peak_db, True)
            _mark_trigger_session(mhz)
            _append_history(mhz, peak_db, True)

            if not relay_state["v"]:
                try: relay.on()
                except: pass
                relay_state["v"] = True
                set_relay_visual(True)
                qlog(f"!!! ТРЕВОГА: {mhz:.2f} MHz | {peak_db:.1f} dB", tag="trigger")

            def auto_off():
                with state_lock:
                    if relay_state["v"]:
                        try: relay.off()
                        except: pass
                        relay_state["v"] = False
                        set_relay_visual(False)
                        qlog("--- РЕЛЕ ВЫКЛЮЧЕНО ---", tag="info")
                    relay_timer["t"] = None

            t = threading.Timer(cfg["RELAY_HOLD_SEC"], auto_off)
            t.daemon = True
            t.start()
            relay_timer["t"] = t

    class Track:
        __slots__ = ("f_mhz", "p_ewma", "hist", "last_seen_ts", "triggered", "first_db")
        def __init__(self, f_mhz, p_db):
            self.f_mhz = f_mhz; self.p_ewma = p_db; self.hist = [p_db]
            self.last_seen_ts = time.time(); self.triggered = False; self.first_db = p_db
        def update(self, f_mhz, p_db):
            self.f_mhz = ALPHA_FREQ * f_mhz + (1 - ALPHA_FREQ) * self.f_mhz
            self.p_ewma = BETA_PWR * p_db + (1 - BETA_PWR) * self.p_ewma
            self.hist.append(p_db)
            self.last_seen_ts = time.time()
            if len(self.hist) > 48: self.hist = self.hist[-48:]
        def ok_trend(self, K):
            if len(self.hist) < K: return False
            w = self.hist[-K:]
            return all(w[i] < w[i+1] for i in range(len(w)-1))

    def reader_loop():
        tracks_local = []
        K = cfg["TREND_K"]
        cmd = ["hackrf_sweep", "-f", f"{global_start:.0f}:{global_end:.0f}"]

        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, bufsize=1, preexec_fn=os.setsid)
            proc["p"] = p
            qlog(f"СКАН СТАРТ: {global_start}-{global_end} MHz", "info")
        except Exception as e:
            qlog(f"Ошибка: {e}", "error"); return

        for raw in p.stdout:
            if not running["v"]: break
            line = raw.strip()
            if not line: continue
            last_line_ts["v"] = time.time()
            if "sweeps" in line: continue
            parts = [x.strip() for x in line.split(",")]
            if not parts_are_valid(parts): continue

            try:
                hz_low = int(parts[2])
                bin_hz = float(parts[4])
                if bin_hz <= 0: continue
                bins = [float(x) for x in parts[6:] if x]
                peak = -999.0; peak_idx = -1
                for k, v in enumerate(bins):
                    if v > peak: peak = v; peak_idx = k
                if peak <= cfg["THRESHOLD_DB"]: continue
                trig_hz = hz_low + int((float(peak_idx) + 0.5) * bin_hz)
                mhz = trig_hz / 1e6
                if not is_in_active_range(mhz): continue

                _accumulate_freq(trig_hz, peak, bin_hz)
                f_tol = max(2.0 * (bin_hz / 1e6), cfg["FREQ_TOL_MHZ_MIN"])
                now_ts = time.time()
                tracks_local = [t for t in tracks_local if (now_ts - t.last_seen_ts) < 10.0]

                best = -1; best_df = None
                for i, t in enumerate(tracks_local):
                    df = abs(t.f_mhz - mhz)
                    if df <= f_tol and (best_df is None or df < best_df):
                        best = i; best_df = df

                if best >= 0:
                    t = tracks_local[best]
                    prev_db = t.hist[-1]
                    t.update(mhz, peak)
                    curr_db = t.hist[-1]
                    if curr_db > prev_db:
                        qlog(f"📈 Наблюдение: {t.f_mhz:.2f} MHz | {curr_db:.1f} dB (Рост)", "signal")
                    elif abs(curr_db - prev_db) > 2.0:
                        qlog(f"ℹ Обновление: {t.f_mhz:.2f} MHz | {curr_db:.1f} dB", "info")
                else:
                    t = Track(mhz, peak)
                    tracks_local.append(t)
                    qlog(f"📡 Обнаружен сигнал: {t.f_mhz:.2f} MHz | {t.hist[-1]:.1f} dB", "signal")
                    _append_history(mhz, peak, False)

                if t.ok_trend(K):
                    t.triggered = True
                    auto_on(t.f_mhz, t.hist[-1])

                if len(tracks_local) > 64: tracks_local = tracks_local[-64:]

            except: pass
        kill_proc()

    def kill_proc():
        p = proc["p"]
        if p:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
                try: p.wait(timeout=1.0)
                except:
                    try: os.killpg(os.getpgid(p.pid), signal.SIGKILL)
                    except: pass
            except: pass
        proc["p"] = None

    def supervisor():
        while running["v"]:
            if proc["p"] is None or proc["p"].poll() is not None:
                threading.Thread(target=reader_loop, daemon=True).start()
                time.sleep(1)
            else:
                if time.time() - last_line_ts["v"] > 5.0: kill_proc()
            time.sleep(1)

    def start_sys():
        if running["v"]: return
        with freq_stats_lock: freq_stats.clear()
        running["v"] = True
        threading.Thread(target=supervisor, daemon=True).start()
        lbl_status_text.config(text="СКАНИРОВАНИЕ...", bg="#c59f12")

    def stop_sys():
        running["v"] = False
        kill_proc()
        lbl_status_text.config(text="ОСТАНОВЛЕНО", bg=THEME["BG_PANEL"])
        qlog("Система остановлена.", "info")

    def reset_all_data():
        if running["v"]: stop_sys()
        with freq_stats_lock: freq_stats.clear()
        try:
            for f in os.listdir(HISTORY_DIR):
                if f.startswith("history_") and f.endswith(".csv"):
                    os.remove(os.path.join(HISTORY_DIR, f))
        except: pass
        qlog("История и статистика полностью очищены.", "info")

    def on_exit():
        stop_sys()
        try: relay.close()
        except: pass
        root.destroy()

    BTN_FONT = ("Arial", 16, "bold")
    BIG_FONT = ("Arial", 22, "bold")

    btn_start = tk.Button(frame_ctrl, text="ЗАПУСК", command=start_sys,
                          bg=THEME["ACCENT_GREEN"], fg="black", font=BIG_FONT, height=2, bd=0)
    btn_start.pack(fill="x", pady=6)

    btn_stop = tk.Button(frame_ctrl, text="ОСТАНОВКА", command=stop_sys,
                         bg=THEME["ACCENT_RED"], fg="black", font=("Arial", 16, "bold"), height=2, bd=0)
    btn_stop.pack(fill="x", pady=6)

    btn_rep = tk.Button(frame_ctrl, text="ОТЧЁТ", command=show_report,
                        bg=THEME["ACCENT_CYAN"], fg="black", font=BIG_FONT, height=2, bd=0)
    btn_rep.pack(fill="x", pady=6)

    btn_reset = tk.Button(frame_ctrl, text="СБРОС", command=reset_all_data,
                        bg=THEME["ACCENT_ORANGE"], fg="black", font=BIG_FONT, height=2, bd=0)
    btn_reset.pack(fill="x", pady=6)

    btn_exit = tk.Button(frame_ctrl, text="ВЫХОД", command=on_exit,
                         bg=THEME["BTN_BG"], fg="white", font=BTN_FONT, height=2, bd=0)
    btn_exit.pack(fill="x", pady=(20, 6))

    root.after(500, pump_logs)
    root.protocol("WM_DELETE_WINDOW", on_exit)
    qlog("Готов к работе. Нажмите ЗАПУСК.", "info")

    root.mainloop()

if __name__ == "__main__":
    run_settings_then_launch()
