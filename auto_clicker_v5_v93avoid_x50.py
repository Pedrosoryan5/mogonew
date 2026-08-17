
import os
import sys
import time
import json
import queue
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk
import cv2
import numpy as np
import io

APP_TITLE = "LDPlayer Priority Auto Clicker v5 - v9.3 Avoid x50"
CONFIG_FILE = "config.json"
TEMPLATE_DIR = "templates"

DEFAULT_TARGETS = ["RR", "CC", "TOKENS", "LEGENDS", "PICK_UP", "CHANCE", "UTILITY_WATER", "UTILITY_ELECTRICITY", "INCOME_TAX", "LUXURY_TAX", "VISITING_CORNER", "FREE_PARKING_CORNER", "CORNER", "JAIL_CORNER"]

def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

ROOT = app_dir()
CONFIG_PATH = os.path.join(ROOT, CONFIG_FILE)
TEMPLATE_PATH = os.path.join(ROOT, TEMPLATE_DIR)
os.makedirs(TEMPLATE_PATH, exist_ok=True)

def find_adb():
    candidates = [
        os.path.join(ROOT, "adb.exe"),
        r"C:\LDPlayer\LDPlayer9\adb.exe",
        r"C:\Program Files\LDPlayer\LDPlayer9\adb.exe",
        r"C:\Program Files (x86)\LDPlayer\LDPlayer9\adb.exe",
        r"D:\LDPlayer\LDPlayer9\adb.exe",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return "adb"

class Adb:
    def __init__(self, adb_path=None):
        self.adb_path = adb_path or find_adb()
        self.serial = None

    def run(self, args, timeout=15, binary=False):
        cmd = [self.adb_path]
        if self.serial:
            cmd += ["-s", self.serial]
        cmd += args
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            creationflags=creationflags
        )
        if p.returncode != 0:
            err = p.stderr.decode(errors="ignore").strip()
            out = p.stdout.decode(errors="ignore").strip()
            raise RuntimeError(err or out or f"ADB failed: {cmd}")
        return p.stdout if binary else p.stdout.decode(errors="ignore")

    def devices(self):
        out = subprocess.run(
            [self.adb_path, "devices"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        if out.returncode != 0:
            raise RuntimeError(out.stderr.strip() or "Unable to run adb devices")
        devs = []
        for line in out.stdout.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devs.append(parts[0])
        return devs

    def screenshot(self):
        raw = self.run(["exec-out", "screencap", "-p"], timeout=20, binary=True)
        arr = np.frombuffer(raw, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("Could not decode LDPlayer screenshot.")
        return img

    def tap(self, x, y):
        self.run(["shell", "input", "tap", str(int(x)), str(int(y))], timeout=8)

class ScreenshotPicker(tk.Toplevel):
    def __init__(self, parent, bgr_image, mode="point", title="Pick", target_name=None):
        super().__init__(parent)
        self.title(title)
        self.grab_set()
        self.result = None
        self.mode = mode
        self.target_name = target_name
        self.orig_bgr = bgr_image
        self.orig_rgb = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
        self.h, self.w = self.orig_bgr.shape[:2]
        self.start = None
        self.rect = None

        sw = max(700, parent.winfo_screenwidth() - 120)
        sh = max(500, parent.winfo_screenheight() - 180)
        scale = min(sw / self.w, sh / self.h, 1.0)
        self.dw = int(self.w * scale)
        self.dh = int(self.h * scale)
        self.scale = scale

        pil = Image.fromarray(self.orig_rgb).resize((self.dw, self.dh), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(pil)

        msg = "Click the desired point." if mode == "point" else "Drag a box tightly around the clickable target, then release."
        ttk.Label(self, text=msg).pack(pady=(8,4))
        self.canvas = tk.Canvas(self, width=self.dw, height=self.dh, cursor="crosshair")
        self.canvas.pack(padx=8, pady=8)
        self.canvas.create_image(0,0, anchor="nw", image=self.photo)

        if mode == "point":
            self.canvas.bind("<Button-1>", self.on_point)
        else:
            self.canvas.bind("<ButtonPress-1>", self.on_press)
            self.canvas.bind("<B1-Motion>", self.on_drag)
            self.canvas.bind("<ButtonRelease-1>", self.on_release)

        btns = ttk.Frame(self)
        btns.pack(pady=(0,8))
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="left", padx=4)

        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_visibility()
        self.focus_force()

    def on_point(self, e):
        x = min(max(int(e.x / self.scale), 0), self.w-1)
        y = min(max(int(e.y / self.scale), 0), self.h-1)
        self.result = (x, y)
        self.destroy()

    def on_press(self, e):
        self.start = (e.x, e.y)
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(e.x,e.y,e.x,e.y, outline="red", width=2)

    def on_drag(self, e):
        if self.start and self.rect:
            x0,y0 = self.start
            self.canvas.coords(self.rect, x0,y0,e.x,e.y)

    def on_release(self, e):
        if not self.start:
            return
        x0,y0 = self.start
        x1,y1 = e.x,e.y
        left,right = sorted([x0,x1])
        top,bottom = sorted([y0,y1])
        if right-left < 8 or bottom-top < 8:
            messagebox.showwarning("Selection too small", "Drag a larger box around the target.", parent=self)
            return
        ox0 = max(0, int(left / self.scale))
        oy0 = max(0, int(top / self.scale))
        ox1 = min(self.w, int(right / self.scale))
        oy1 = min(self.h, int(bottom / self.scale))
        self.result = (ox0, oy0, ox1, oy1)
        self.destroy()

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1040x760")
        self.minsize(920, 650)

        self.adb = Adb()
        self.running = False
        self.worker = None
        self.log_q = queue.Queue()
        self.last_screen = None

        self.config_data = self.load_config()
        self.build_ui()
        self.refresh_devices()
        self.refresh_templates()
        self.after(120, self.flush_logs)

    def load_config(self):
        cfg = {
            "adb_path": find_adb(),
            "serial": "",
            "fallback": [0,0],
            "roll_points": {"1": [0,0], "5": [0,0], "10": [0,0], "20": [0,0], "50": [0,0]},
            "default_roll_multiplier": 1,
            "avoid_roll_multiplier": 10,
            "threshold": 0.86,
            "scan_delay": 0.7,
            "after_roll_delay": 2.0,
            "after_target_delay": 1.2,
            "prefer_highest_multiplier": True,
            "highest_multiplier_for_all_targets": True,
            "priority": ["RR","TOKENS","CC"],
            "disabled": ["CHANCE"]
        }
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
        return cfg

    def save_config(self):
        self.config_data["adb_path"] = self.adb_path_var.get().strip()
        self.config_data["serial"] = self.device_var.get().strip()
        self.config_data["fallback"] = [int(self.x_var.get() or 0), int(self.y_var.get() or 0)]
        self.config_data["roll_points"] = {
            m: [int(self.roll_x_vars[m].get() or 0), int(self.roll_y_vars[m].get() or 0)]
            for m in ("1","5","10","20","50")
        }
        self.config_data["default_roll_multiplier"] = int(self.default_roll_var.get())
        self.config_data["avoid_roll_multiplier"] = int(self.avoid_roll_var.get())
        self.config_data["threshold"] = float(self.threshold_var.get())
        self.config_data["scan_delay"] = float(self.scan_delay_var.get())
        self.config_data["after_roll_delay"] = float(self.after_roll_var.get())
        self.config_data["after_target_delay"] = float(self.after_target_var.get())
        self.config_data["prefer_highest_multiplier"] = bool(self.prefer_highest_multiplier_var.get())
        self.config_data["highest_multiplier_for_all_targets"] = bool(self.highest_all_targets_var.get())
        self.config_data["priority"] = [self.priority_list.get(i) for i in range(self.priority_list.size())]
        self.config_data["disabled"] = [name for name,var in self.disable_vars.items() if var.get()]
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.config_data, f, indent=2)

    def build_ui(self):
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)

        top = ttk.LabelFrame(outer, text="LDPlayer / ADB", padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="ADB:").grid(row=0,column=0,sticky="w")
        self.adb_path_var = tk.StringVar(value=self.config_data.get("adb_path", find_adb()))
        ttk.Entry(top, textvariable=self.adb_path_var, width=65).grid(row=0,column=1,columnspan=4,sticky="ew",padx=5)
        ttk.Button(top, text="Apply ADB Path", command=self.apply_adb_path).grid(row=0,column=5,padx=5)

        ttk.Label(top, text="Device:").grid(row=1,column=0,sticky="w",pady=(7,0))
        self.device_var = tk.StringVar(value=self.config_data.get("serial",""))
        self.device_combo = ttk.Combobox(top, textvariable=self.device_var, state="readonly", width=40)
        self.device_combo.grid(row=1,column=1,sticky="w",padx=5,pady=(7,0))
        ttk.Button(top, text="Refresh Devices", command=self.refresh_devices).grid(row=1,column=2,padx=5,pady=(7,0))
        ttk.Button(top, text="Capture Screen", command=self.capture_screen).grid(row=1,column=3,padx=5,pady=(7,0))
        ttk.Button(top, text="Open Templates Folder", command=self.open_templates).grid(row=1,column=4,columnspan=2,padx=5,pady=(7,0))
        top.columnconfigure(1, weight=1)

        main = ttk.Frame(outer)
        main.pack(fill="both", expand=True, pady=10)

        left = ttk.Frame(main)
        left.pack(side="left", fill="both", expand=True, padx=(0,6))

        fallback = ttk.LabelFrame(left, text="Roll Fallbacks", padding=8)
        fallback.pack(fill="x")
        roll_cfg = self.config_data.get("roll_points", {})
        legacy = self.config_data.get("fallback",[0,0])
        if not roll_cfg.get("1") or roll_cfg.get("1") == [0,0]:
            roll_cfg["1"] = legacy

        self.roll_x_vars = {}
        self.roll_y_vars = {}
        for r, mult in enumerate(("1","5","10","20","50")):
            pt = roll_cfg.get(mult,[0,0])
            self.roll_x_vars[mult] = tk.StringVar(value=str(pt[0]))
            self.roll_y_vars[mult] = tk.StringVar(value=str(pt[1]))
            ttk.Label(fallback,text=f"x{mult} X:").grid(row=r,column=0,sticky="w")
            ttk.Entry(fallback,textvariable=self.roll_x_vars[mult],width=7).grid(row=r,column=1,padx=3)
            ttk.Label(fallback,text="Y:").grid(row=r,column=2)
            ttk.Entry(fallback,textvariable=self.roll_y_vars[mult],width=7).grid(row=r,column=3,padx=3)
            ttk.Button(fallback,text=f"Pick x{mult}",command=lambda m=mult:self.pick_roll_point(m)).grid(row=r,column=4,padx=4)
            ttk.Button(fallback,text=f"Test x{mult}",command=lambda m=mult:self.test_roll_point(m)).grid(row=r,column=5,padx=4)

        self.x_var = self.roll_x_vars["1"]
        self.y_var = self.roll_y_vars["1"]

        ttk.Label(fallback,text="Normal fallback:").grid(row=0,column=6,padx=(10,2),sticky="e")
        self.default_roll_var = tk.StringVar(value=str(self.config_data.get("default_roll_multiplier",1)))
        ttk.Combobox(fallback,textvariable=self.default_roll_var,values=["1","5","10","20","50"],state="readonly",width=5).grid(row=0,column=7)

        ttk.Label(fallback,text="If avoided target is visible:").grid(row=1,column=6,padx=(10,2),sticky="e")
        self.avoid_roll_var = tk.StringVar(value=str(self.config_data.get("avoid_roll_multiplier",10)))
        ttk.Combobox(fallback,textvariable=self.avoid_roll_var,values=["1","5","10","20","50"],state="readonly",width=5).grid(row=1,column=7)

        templates = ttk.LabelFrame(left, text="Templates", padding=8)
        templates.pack(fill="x", pady=8)

        self.template_target_var = tk.StringVar(value="RR")
        ttk.Label(templates,text="Target:").grid(row=0,column=0,sticky="w")
        self.target_combo = ttk.Combobox(templates,textvariable=self.template_target_var, values=DEFAULT_TARGETS, width=18)
        self.target_combo.grid(row=0,column=1,padx=5)
        ttk.Button(templates,text="Add / Replace Template",command=self.add_template).grid(row=0,column=2,padx=5)
        ttk.Button(templates,text="Delete Template",command=self.delete_template).grid(row=0,column=3,padx=5)
        ttk.Button(templates,text="Test Detection",command=self.test_detection).grid(row=0,column=4,padx=5)

        self.template_status = ttk.Label(templates,text="")
        self.template_status.grid(row=1,column=0,columnspan=5,sticky="w",pady=(7,0))

        priority = ttk.LabelFrame(left, text="Priority Order", padding=8)
        priority.pack(fill="both", expand=True)

        pframe = ttk.Frame(priority)
        pframe.pack(fill="both", expand=True)
        self.priority_list = tk.Listbox(pframe, height=8, exportselection=False)
        self.priority_list.pack(side="left", fill="both", expand=True)
        for name in self.config_data.get("priority",["RR","TOKENS","CC"]):
            self.priority_list.insert("end", name)
        pbtn = ttk.Frame(pframe)
        pbtn.pack(side="left", padx=6)
        ttk.Button(pbtn,text="Add",command=self.priority_add,width=10).pack(pady=2)
        ttk.Button(pbtn,text="Remove",command=self.priority_remove,width=10).pack(pady=2)
        ttk.Button(pbtn,text="Move Up",command=lambda:self.priority_move(-1),width=10).pack(pady=2)
        ttk.Button(pbtn,text="Move Down",command=lambda:self.priority_move(1),width=10).pack(pady=2)

        right = ttk.Frame(main)
        right.pack(side="left", fill="both", expand=True, padx=(6,0))

        disabled = ttk.LabelFrame(right,text="Avoid / Disable Targets",padding=8)
        disabled.pack(fill="x")
        self.disable_vars = {}
        disabled_saved = set(self.config_data.get("disabled",["CHANCE"]))
        for idx,name in enumerate(DEFAULT_TARGETS):
            v = tk.BooleanVar(value=name in disabled_saved)
            self.disable_vars[name] = v
            ttk.Checkbutton(disabled,text=name,variable=v).grid(row=idx//3,column=idx%3,sticky="w",padx=5,pady=2)

        settings = ttk.LabelFrame(right,text="Timing / Detection",padding=8)
        settings.pack(fill="x",pady=8)
        self.threshold_var = tk.StringVar(value=str(self.config_data.get("threshold",0.86)))
        self.scan_delay_var = tk.StringVar(value=str(self.config_data.get("scan_delay",0.7)))
        self.after_roll_var = tk.StringVar(value=str(self.config_data.get("after_roll_delay",2.0)))
        self.after_target_var = tk.StringVar(value=str(self.config_data.get("after_target_delay",1.2)))
        self.prefer_highest_multiplier_var = tk.BooleanVar(value=bool(self.config_data.get("prefer_highest_multiplier", True)))
        self.highest_all_targets_var = tk.BooleanVar(value=bool(self.config_data.get("highest_multiplier_for_all_targets", True)))

        labels = [
            ("Match threshold (0-1):", self.threshold_var),
            ("Scan delay (sec):", self.scan_delay_var),
            ("After x1 roll delay:", self.after_roll_var),
            ("After target click delay:", self.after_target_var)
        ]
        for r,(txt,var) in enumerate(labels):
            ttk.Label(settings,text=txt).grid(row=r,column=0,sticky="w",pady=2)
            ttk.Entry(settings,textvariable=var,width=10).grid(row=r,column=1,sticky="w",padx=5)
        ttk.Checkbutton(
            settings,
            text="Prefer the highest visible multiplier for ALL priority targets",
            variable=self.highest_all_targets_var
        ).grid(row=len(labels), column=0, columnspan=2, sticky="w", pady=(6,2))

        controls = ttk.LabelFrame(right,text="Bot",padding=8)
        controls.pack(fill="x")
        self.start_btn = ttk.Button(controls,text="START",command=self.start_bot)
        self.start_btn.pack(side="left",padx=4)
        self.stop_btn = ttk.Button(controls,text="STOP",command=self.stop_bot,state="disabled")
        self.stop_btn.pack(side="left",padx=4)
        ttk.Button(controls,text="Run One Cycle",command=self.one_cycle_thread).pack(side="left",padx=4)
        ttk.Button(controls,text="Save Settings",command=self.on_save).pack(side="left",padx=4)

        logbox = ttk.LabelFrame(right,text="Activity Log",padding=6)
        logbox.pack(fill="both",expand=True,pady=8)
        self.log_text = tk.Text(logbox,height=15,wrap="word")
        self.log_text.pack(fill="both",expand=True)

    def log(self, text):
        self.log_q.put(f"[{time.strftime('%H:%M:%S')}] {text}")

    def flush_logs(self):
        try:
            while True:
                msg = self.log_q.get_nowait()
                self.log_text.insert("end", msg + "\n")
                self.log_text.see("end")
        except queue.Empty:
            pass
        self.after(120, self.flush_logs)

    def apply_adb_path(self):
        p = self.adb_path_var.get().strip()
        self.adb.adb_path = p or "adb"
        self.log(f"ADB path set to: {self.adb.adb_path}")
        self.refresh_devices()

    def set_device(self):
        serial = self.device_var.get().strip()
        if not serial:
            raise RuntimeError("Select an LDPlayer device first.")
        self.adb.serial = serial

    def refresh_devices(self):
        try:
            self.adb.adb_path = self.adb_path_var.get().strip() if hasattr(self,"adb_path_var") else self.config_data.get("adb_path",find_adb())
            devs = self.adb.devices()
            self.device_combo["values"] = devs
            current = self.device_var.get().strip()
            if current in devs:
                self.device_var.set(current)
            elif devs:
                self.device_var.set(devs[0])
            else:
                self.device_var.set("")
            self.log("Devices: " + (", ".join(devs) if devs else "none detected"))
        except Exception as e:
            self.log("Device refresh error: " + str(e))

    def capture_screen(self):
        try:
            self.set_device()
            img = self.adb.screenshot()
            self.last_screen = img
            out = os.path.join(ROOT,"ldplayer_screen.png")
            cv2.imwrite(out,img)
            self.log(f"Screenshot saved: {out} ({img.shape[1]}x{img.shape[0]})")
            messagebox.showinfo("Captured", f"Saved:\n{out}\n\nResolution: {img.shape[1]} x {img.shape[0]}")
        except Exception as e:
            messagebox.showerror("Capture failed",str(e))

    def pick_roll_point(self, mult):
        try:
            self.set_device()
            img = self.adb.screenshot()
            picker = ScreenshotPicker(self,img,mode="point",title=f"Click the x{mult} roll button")
            self.wait_window(picker)
            if picker.result:
                x,y = picker.result
                self.roll_x_vars[mult].set(str(x))
                self.roll_y_vars[mult].set(str(y))
                self.log(f"x{mult} roll point set to {x},{y}")
        except Exception as e:
            messagebox.showerror(f"Pick x{mult} failed",str(e))

    def test_roll_point(self, mult):
        try:
            self.set_device()
            x = int(self.roll_x_vars[mult].get())
            y = int(self.roll_y_vars[mult].get())
            self.adb.tap(x,y)
            self.log(f"Test x{mult} tap -> {x},{y}")
        except Exception as e:
            messagebox.showerror("Test failed",str(e))

    def pick_fallback(self):
        self.pick_roll_point("1")

    def test_fallback(self):
        self.test_roll_point("1")

    def add_template(self):
        name = self.template_target_var.get().strip().upper().replace(" ","_").replace("/","_")
        if not name:
            return
        try:
            self.set_device()
            img = self.adb.screenshot()
            picker = ScreenshotPicker(self,img,mode="box",title=f"Draw box around {name}",target_name=name)
            self.wait_window(picker)
            if picker.result:
                x0,y0,x1,y1 = picker.result
                crop = img[y0:y1,x0:x1]
                path = os.path.join(TEMPLATE_PATH,f"{name}.png")
                cv2.imwrite(path,crop)
                self.log(f"Saved template {name}: {crop.shape[1]}x{crop.shape[0]} px")
                self.refresh_templates()
        except Exception as e:
            messagebox.showerror("Template failed",str(e))

    def delete_template(self):
        name = self.template_target_var.get().strip().upper().replace(" ","_").replace("/","_")
        path = os.path.join(TEMPLATE_PATH,f"{name}.png")
        if os.path.exists(path):
            os.remove(path)
            self.log(f"Deleted template {name}")
            self.refresh_templates()

    def refresh_templates(self):
        if not hasattr(self,"template_status"): return
        items = sorted([os.path.splitext(f)[0] for f in os.listdir(TEMPLATE_PATH) if f.lower().endswith(".png")])
        self.template_status.config(text="Available templates: " + (", ".join(items) if items else "none"))
        vals = sorted(set(DEFAULT_TARGETS + items))
        self.target_combo["values"] = vals

    def open_templates(self):
        os.makedirs(TEMPLATE_PATH,exist_ok=True)
        if os.name == "nt":
            os.startfile(TEMPLATE_PATH)
        else:
            subprocess.Popen(["xdg-open",TEMPLATE_PATH])

    def priority_add(self):
        name = self.template_target_var.get().strip().upper().replace(" ","_").replace("/","_")
        if not name: return
        existing = [self.priority_list.get(i) for i in range(self.priority_list.size())]
        if name not in existing:
            self.priority_list.insert("end",name)

    def priority_remove(self):
        s = self.priority_list.curselection()
        if s: self.priority_list.delete(s[0])

    def priority_move(self,delta):
        s = self.priority_list.curselection()
        if not s: return
        i = s[0]
        j = i + delta
        if j < 0 or j >= self.priority_list.size(): return
        val = self.priority_list.get(i)
        self.priority_list.delete(i)
        self.priority_list.insert(j,val)
        self.priority_list.selection_set(j)

    def match_all_templates(self, screen, name, threshold):
        """
        Return all non-overlapping matches for a template, not just the strongest one.
        This matters when RR/CC appears more than once on screen.
        """
        path = os.path.join(TEMPLATE_PATH,f"{name}.png")
        if not os.path.exists(path):
            return []
        tpl = cv2.imread(path,cv2.IMREAD_COLOR)
        if tpl is None:
            return []
        sh,sw = screen.shape[:2]
        th,tw = tpl.shape[:2]
        if tw > sw or th > sh:
            return []

        result = cv2.matchTemplate(screen,tpl,cv2.TM_CCOEFF_NORMED)
        ys, xs = np.where(result >= threshold)
        candidates = []
        for x0,y0 in zip(xs.tolist(), ys.tolist()):
            score = float(result[y0,x0])
            candidates.append((score, x0, y0))

        # Strongest first, then suppress nearby duplicates.
        candidates.sort(reverse=True, key=lambda t: t[0])
        kept = []
        min_dx = max(8, int(tw * 0.55))
        min_dy = max(8, int(th * 0.55))
        for score,x0,y0 in candidates:
            cx = x0 + tw//2
            cy = y0 + th//2
            if any(abs(cx-k[0]) < min_dx and abs(cy-k[1]) < min_dy for k in kept):
                continue
            kept.append((cx,cy,score,(x0,y0),(tw,th)))
        return kept

    def match_template(self, screen, name, threshold):
        matches = self.match_all_templates(screen, name, threshold)
        return matches[0] if matches else None

    def _multiplier_candidates_from_roi(self, screen, match, target_name):
        """
        Estimate the visible x-multiplier near a matched RR/CC tile using lightweight OCR-like
        image processing + digit template matching if DIGIT templates exist.
        Recommended naming: DIGIT_0.png ... DIGIT_9.png and MULT_X.png (optional).
        If no digit templates exist, returns None.
        """
        digit_templates = {}
        for d in "0123456789":
            p = os.path.join(TEMPLATE_PATH, f"DIGIT_{d}.png")
            if os.path.exists(p):
                im = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
                if im is not None:
                    digit_templates[d] = im
        if not digit_templates:
            return None

        x,y,score,(x0,y0),(tw,th) = match
        sh,sw = screen.shape[:2]

        # Search a generous area around the RR/CC match for its numeric multiplier.
        pad_x = int(tw * 1.5)
        pad_y = int(th * 1.0)
        rx0 = max(0, x0 - pad_x)
        ry0 = max(0, y0 - pad_y)
        rx1 = min(sw, x0 + tw + pad_x)
        ry1 = min(sh, y0 + th + pad_y)
        roi = cv2.cvtColor(screen[ry0:ry1, rx0:rx1], cv2.COLOR_BGR2GRAY)

        # Collect digit detections.
        dets = []
        for d,tpl in digit_templates.items():
            rh,rw = roi.shape[:2]
            dh,dw = tpl.shape[:2]
            if dw > rw or dh > rh:
                continue
            res = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
            ys,xs = np.where(res >= 0.80)
            local = []
            for xx,yy in zip(xs.tolist(), ys.tolist()):
                sc = float(res[yy,xx])
                local.append((sc,xx,yy,d,dw,dh))
            local.sort(reverse=True, key=lambda t:t[0])
            kept_local=[]
            for item in local:
                sc,xx,yy,dd,dw,dh = item
                cx=xx+dw//2; cy=yy+dh//2
                if any(abs(cx-k[1])<max(5,dw//2) and abs(cy-k[2])<max(5,dh//2) for k in kept_local):
                    continue
                kept_local.append(item)
            dets.extend(kept_local)

        if not dets:
            return None

        # Group digits into approximately horizontal number strings.
        dets.sort(key=lambda t:(t[2],t[1]))
        groups=[]
        for det in dets:
            sc,xx,yy,d,dw,dh = det
            cy=yy+dh/2
            placed=False
            for g in groups:
                if abs(cy-g["cy"]) <= max(8, dh*0.6):
                    g["items"].append(det)
                    g["cy"]=(g["cy"]+cy)/2
                    placed=True
                    break
            if not placed:
                groups.append({"cy":cy,"items":[det]})

        best_num = None
        best_dist = None
        for g in groups:
            items = sorted(g["items"], key=lambda t:t[1])
            # Deduplicate overlapping competing digits by x position, keeping highest score.
            merged=[]
            for item in items:
                sc,xx,yy,d,dw,dh=item
                if merged and abs(xx-merged[-1][1]) < max(4,dw*0.45):
                    if sc > merged[-1][0]:
                        merged[-1]=item
                else:
                    merged.append(item)

            s="".join(i[3] for i in merged)
            if not s.isdigit():
                continue
            try:
                num=int(s)
            except:
                continue

            # Prefer plausible Monopoly-style multipliers and numbers near the matched target.
            if num <= 0 or num > 100000:
                continue
            gx = sum(i[1]+i[4]/2 for i in merged)/len(merged) + rx0
            gy = sum(i[2]+i[5]/2 for i in merged)/len(merged) + ry0
            dist=((gx-x)**2+(gy-y)**2)**0.5
            if best_num is None or dist < best_dist:
                best_num=num
                best_dist=dist

        return best_num

    def choose_best_match(self, screen, name, threshold):
        matches = self.match_all_templates(screen, name, threshold)
        if not matches:
            return None

        if self.highest_all_targets_var.get() and len(matches) > 1:
            scored=[]
            for m in matches:
                mult = self._multiplier_candidates_from_roi(screen, m, name)
                scored.append((mult if mult is not None else -1, m))
            if any(v >= 0 for v,_ in scored):
                scored.sort(key=lambda z:(z[0], z[1][2]), reverse=True)
                chosen_mult, chosen = scored[0]
                self.log(f"{name}: highest detected multiplier = {chosen_mult}x")
                return chosen

        return max(matches, key=lambda m:m[2])

    def detect_best(self, screen):
        threshold = float(self.threshold_var.get())
        disabled = {name for name,var in self.disable_vars.items() if var.get()}
        priorities = [self.priority_list.get(i) for i in range(self.priority_list.size())]

        for name in priorities:
            if name in disabled:
                continue
            hit = self.choose_best_match(screen,name,threshold)
            if hit:
                return name,hit
        return None,None

    def test_detection(self):
        try:
            self.set_device()
            img = self.adb.screenshot()
            threshold = float(self.threshold_var.get())
            disabled = {name for name,var in self.disable_vars.items() if var.get()}
            priorities = [self.priority_list.get(i) for i in range(self.priority_list.size())]

            found = []
            for name in priorities:
                if name in disabled:
                    continue
                hit = self.choose_best_match(img,name,threshold)
                if hit:
                    found.append((name,hit))
            if not found:
                self.log("Test detection: no enabled priority target found.")
                messagebox.showinfo("Detection result","No enabled priority target matched.\nTry lowering threshold slightly or recapturing a tighter template.")
                return
            lines=[]
            for name,(x,y,score,loc,size) in found:
                lines.append(f"{name}: {score*100:.1f}% at ({x},{y})")
            self.log("Test detection -> " + " | ".join(lines))
            messagebox.showinfo("Detection result","\n".join(lines))
        except Exception as e:
            messagebox.showerror("Detection failed",str(e))

    def disabled_roll_slots(self, screen):
        threshold=float(self.threshold_var.get())
        blocked=set()
        details=[]

        roll_points={}
        for mult in ("1","5","10","20","50"):
            try:
                x=int(self.roll_x_vars[mult].get() or 0)
                y=int(self.roll_y_vars[mult].get() or 0)
            except Exception:
                continue
            if x>0 or y>0:
                roll_points[mult]=(x,y)

        if not roll_points:
            return blocked

        top_y=sum(y for x,y in roll_points.values())/len(roll_points)
        screen_h=screen.shape[0] if hasattr(screen,"shape") else 720
        y_tolerance=max(35,int(screen_h*0.11))

        for name,var in self.disable_vars.items():
            if not var.get():
                continue

            try:
                hits=self.match_all_templates(screen,name,threshold)
            except Exception:
                hit=self.match_template(screen,name,threshold)
                hits=[hit] if hit else []

            seen=set()
            for hit in hits:
                if not hit:
                    continue
                tx,ty=hit[0],hit[1]

                # Key fix: ignore bottom-row 100/200/500/1000 matches.
                if abs(ty-top_y)>y_tolerance:
                    continue

                slot=min(roll_points.items(),key=lambda kv:abs(kv[1][0]-tx))[0]
                if slot in seen:
                    continue

                seen.add(slot)
                blocked.add(slot)
                details.append(f"{name}->x{slot}")

        if details:
            self.log("Avoid map (top row only): "+", ".join(details))

        return blocked

    def choose_v93_safe_fallback(self, screen):
        blocked=self.disabled_roll_slots(screen)
        order=["1","5","10","20","50"]

        preferred=str(self.default_roll_var.get())
        if preferred in order:
            order.remove(preferred)
            order.insert(0,preferred)

        for mult in order:
            if mult in blocked:
                continue
            try:
                x=int(self.roll_x_vars[mult].get() or 0)
                y=int(self.roll_y_vars[mult].get() or 0)
            except Exception:
                continue
            if x>0 or y>0:
                return mult

        return None

    def any_disabled_target_visible(self, screen):
        threshold = float(self.threshold_var.get())
        for name,var in self.disable_vars.items():
            if not var.get():
                continue
            if self.match_template(screen, name, threshold):
                self.log(f"Avoided target visible: {name}")
                return True
        return False

    def tap_roll_multiplier(self, mult):
        mult = str(mult)
        if mult not in self.roll_x_vars:
            mult = "1"
        x = int(self.roll_x_vars[mult].get() or 0)
        y = int(self.roll_y_vars[mult].get() or 0)

        if x <= 0 and y <= 0:
            for candidate in ("10","5","1"):
                cx = int(self.roll_x_vars[candidate].get() or 0)
                cy = int(self.roll_y_vars[candidate].get() or 0)
                if cx > 0 or cy > 0:
                    mult = candidate
                    x,y = cx,cy
                    break

        if x <= 0 and y <= 0:
            self.log("No roll fallback point configured.")
            return False

        self.adb.tap(x,y)
        self.log(f"Fallback roll x{mult} -> ({x},{y})")
        return True

    def one_cycle(self):
        self.set_device()
        img = self.adb.screenshot()

        # Keep normal v5 priority detection unchanged.
        name,hit = self.detect_best(img)
        if hit:
            x,y,score,_,_ = hit
            self.adb.tap(x,y)
            self.log(f"{name} detected ({score*100:.1f}%) -> tapped ({x},{y})")
            return "target"

        # ONLY CHANGE FROM ORIGINAL V5:
        # use v9.3-style slot-aware AVOID logic.
        safe_mult = self.choose_v93_safe_fallback(img)

        if safe_mult is None:
            self.log("All configured fallback slots are blocked by Avoid -> waiting")
            return "none"

        if self.tap_roll_multiplier(safe_mult):
            self.log(f"v9.3 AVOID logic -> safe fallback x{safe_mult}")
            return "roll"

        return "none"

    def one_cycle_thread(self):
        def run():
            try: self.one_cycle()
            except Exception as e: self.log("One cycle error: "+str(e))
        threading.Thread(target=run,daemon=True).start()

    def bot_loop(self):
        self.log("Bot started.")
        try:
            self.set_device()
            while self.running:
                action = self.one_cycle()
                if not self.running: break
                if action == "roll":
                    delay = float(self.after_roll_var.get())
                elif action == "target":
                    delay = float(self.after_target_var.get())
                else:
                    delay = float(self.scan_delay_var.get())
                end = time.time() + max(0.05,delay)
                while self.running and time.time() < end:
                    time.sleep(0.05)
        except Exception as e:
            self.log("Bot stopped due to error: "+str(e))
        finally:
            self.running = False
            self.after(0,self.update_buttons)
            self.log("Bot stopped.")

    def update_buttons(self):
        self.start_btn.config(state="disabled" if self.running else "normal")
        self.stop_btn.config(state="normal" if self.running else "disabled")

    def start_bot(self):
        try:
            self.save_config()
            self.set_device()
            for m in ("1","5","10"):
                int(self.roll_x_vars[m].get()); int(self.roll_y_vars[m].get())
            float(self.threshold_var.get())
            float(self.scan_delay_var.get())
            float(self.after_roll_var.get())
            float(self.after_target_var.get())
        except Exception as e:
            messagebox.showerror("Cannot start",str(e)); return
        if self.running: return
        self.running = True
        self.update_buttons()
        self.worker = threading.Thread(target=self.bot_loop,daemon=True)
        self.worker.start()

    def stop_bot(self):
        self.running = False
        self.update_buttons()

    def on_save(self):
        try:
            self.save_config()
            self.log("Settings saved.")
        except Exception as e:
            messagebox.showerror("Save failed",str(e))

    def on_close(self):
        self.running=False
        try:self.save_config()
        except:pass
        self.destroy()

if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
