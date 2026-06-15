import sys
import ctypes
import os
import glob
import time
import threading
import tkinter as tk
import json
import tkinter.messagebox as messagebox


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


FONT       = "Arial"
BG         = "#161616"    # Background
FG         = "#cccccc"    # Primary text
FG_DIM     = "#696969"    # footer / About-lenke
SELECT     = "#333333"    # Checkbox (selected)
TOOLTIP_BG = "#333333"    # Tooltip background
TOOLTIP_FG = "#cccccc"    # Tooltip text
# Statusfarger
ST_WAIT    = "#C7C7D6"    # Waiting for match
ST_ACCEPT  = "#3FB950"    # Match Accepted
ST_PAUSE   = "#E3B341"    # In match - paused
ST_IDLE    = "#8A8A99"    # CS2 not launched
ST_STOP    = "#F85149"    # Stopped


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background=TOOLTIP_BG, foreground=TOOLTIP_FG, relief=tk.SOLID, borderwidth=1,
                         font=("tahoma", 10, "normal"))
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()

class AutoAcceptApp:
    def __init__(self):
        self.SETTINGS_FILE = os.path.join(os.path.expanduser("~/Documents"), "AutoAccept_settings.json")
        self.ICON_FILE = resource_path(os.path.join('assets', 'icons', 'icon1.png'))
        self.UPDATE_URL = "https://kimsec.net/apps/autoaccept_update.json"
        self.RELEASE_NOTES_URL = "https://kimsec.net/AutoAccept-CS2/"
        self.CHECK_INTERVAL = 3
        self.ACCEPT_LABEL_SECONDS = 10

        self.GSI_PORT = 3100
        self.GSI_TOKEN = "autoaccept"
        self.GSI_STALE_SECONDS = 20
        self._gsi_state = None
        self._gsi_time = 0.0
        self._last_accept_time = None
        self._last_in_match = False
        self.GSI_CFG_TEMPLATE = (
            '"Auto Accept Integration"\n'
            '{\n'
            '    "uri"           "http://127.0.0.1:' + str(self.GSI_PORT) + '"\n'
            '    "timeout"       "5.0"\n'
            '    "buffer"        "0.1"\n'
            '    "throttle"      "0.5"\n'
            '    "heartbeat"     "10.0"\n'
            '    "auth"\n'
            '    {\n'
            '        "token"     "' + self.GSI_TOKEN + '"\n'
            '    }\n'
            '    "data"\n'
            '    {\n'
            '        "map"                   "1"\n'
            '        "round"                 "1"\n'
            '        "player_id"             "1"\n'
            '        "player_state"          "1"\n'
            '        "player_match_stats"    "1"\n'
            '        "provider"              "1"\n'
            '    }\n'
            '}\n'
        )

        self.running = threading.Event()

        self.set_dpi_awareness()
        self.load_settings()
        self.create_gui()

    def set_dpi_awareness(self):
        if sys.platform.startswith("win"):
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()

    def load_settings(self):
        if os.path.exists(self.SETTINGS_FILE):
            try:
                with open(self.SETTINGS_FILE, "r") as settings_file:
                    settings = json.load(settings_file)
                    self.start_minimized_val = settings.get("start_minimized", False)
                    self.minimize_to_tray_val = settings.get("minimize_to_tray", False)
                    self.pause_in_match_val = settings.get("pause_in_match", True)
                    self.start_with_windows_val = settings.get("start_with_windows", False)
                    self.win_x = settings.get("win_x")
                    self.win_y = settings.get("win_y")
            except Exception as e:
                print(f"Error loading settings: {e}")
                self.start_minimized_val = False
                self.minimize_to_tray_val = False
                self.pause_in_match_val = True
                self.start_with_windows_val = False
                self.win_x = None
                self.win_y = None
        else:
            self.start_minimized_val = False
            self.minimize_to_tray_val = False
            self.pause_in_match_val = True
            self.start_with_windows_val = False
            self.win_x = None
            self.win_y = None

    def save_settings(self):
        settings = {
            "start_minimized": self.start_minimized_var.get(),
            "minimize_to_tray": self.minimize_to_tray_var.get(),
            "pause_in_match": self.pause_in_match_var.get(),
            "start_with_windows": self.start_with_windows_var.get()
        }
        try:
            with open(self.SETTINGS_FILE, "w") as settings_file:
                json.dump(settings, settings_file)
        except Exception as e:
            print(f"Error saving settings: {e}")
        self.set_autostart(self.start_with_windows_var.get())

    def set_autostart(self, enable):
        if not sys.platform.startswith("win"):
            return
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_SET_VALUE)
            try:
                if enable:
                    if getattr(sys, "frozen", False):
                        cmd = f'"{sys.executable}"'
                    else:
                        exe = sys.executable
                        if exe.lower().endswith("python.exe"):
                            pyw = exe[:-len("python.exe")] + "pythonw.exe"
                            if os.path.exists(pyw):
                                exe = pyw
                        cmd = f'"{exe}" "{os.path.abspath(__file__)}"'
                    winreg.SetValueEx(key, "AutoAccept", 0, winreg.REG_SZ, cmd)
                else:
                    try:
                        winreg.DeleteValue(key, "AutoAccept")
                    except FileNotFoundError:
                        pass
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            print(f"Autostart error: {e}")

    def save_position(self):
        try:
            data = {}
            if os.path.exists(self.SETTINGS_FILE):
                with open(self.SETTINGS_FILE, "r") as f:
                    data = json.load(f)
            data["win_x"] = self.root.winfo_x()
            data["win_y"] = self.root.winfo_y()
            with open(self.SETTINGS_FILE, "w") as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Error saving position: {e}")

    def start_gsi_server(self):
        try:
            from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
            app = self

            class GSIHandler(BaseHTTPRequestHandler):
                def do_POST(self):
                    try:
                        length = int(self.headers.get("Content-Length", 0))
                        body = self.rfile.read(length) if length else b""
                        payload = json.loads(body.decode("utf-8"))
                        if payload.get("auth", {}).get("token") == app.GSI_TOKEN:
                            app._gsi_state = payload
                            app._gsi_time = time.time()
                    except Exception:
                        pass
                    self.send_response(200)
                    self.end_headers()

                def log_message(self, format, *args):
                    pass

            server = ThreadingHTTPServer(("127.0.0.1", self.GSI_PORT), GSIHandler)
            self._gsi_server = server
            server.serve_forever()
        except Exception as e:
            print(f"GSI server not started: {e}")

    def gsi_active(self):
        return self._gsi_state is not None and (time.time() - self._gsi_time) <= self.GSI_STALE_SECONDS

    def cs2_running(self):
        if self.gsi_active():
            return True
        if not sys.platform.startswith("win"):
            return True
        try:
            from ctypes import wintypes
            k = ctypes.windll.kernel32

            class ENTRY(ctypes.Structure):
                _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                            ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                            ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                            ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                            ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_char * 260)]

            k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
            k.Process32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(ENTRY)]
            k.Process32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(ENTRY)]
            k.CloseHandle.argtypes = [wintypes.HANDLE]

            snap = k.CreateToolhelp32Snapshot(0x00000002, 0)
            if not snap or snap == ctypes.c_void_p(-1).value:
                return True
            try:
                e = ENTRY()
                e.dwSize = ctypes.sizeof(ENTRY)
                ok = k.Process32First(snap, ctypes.byref(e))
                while ok:
                    if e.szExeFile.lower() == b"cs2.exe":
                        return True
                    ok = k.Process32Next(snap, ctypes.byref(e))
                return False
            finally:
                k.CloseHandle(snap)
        except Exception:
            return True

    def is_in_match(self):
        if self.gsi_active():
            state = self._gsi_state or {}
            self._last_in_match = bool(state.get("map"))
            return self._last_in_match
        return self._last_in_match

    def _update_status(self, in_match, cs2_running):
        if not (self.running.is_set() and hasattr(self, 'status_label') and self.status_label.winfo_exists()):
            return
        if not cs2_running:
            text, color = "CS2 not launched", ST_IDLE
        elif in_match:
            text, color = "In match - paused", ST_PAUSE
        elif self._last_accept_time is not None and (time.time() - self._last_accept_time) < self.ACCEPT_LABEL_SECONDS:
            text, color = "Match Accepted", ST_ACCEPT
        else:
            text, color = "Waiting for match", ST_WAIT
        if self.status_label.cget("text") != text:
            self.status_label.config(text=text, fg=color)

    def install_gsi_config(self):
        try:
            if not sys.platform.startswith("win"):
                return
            import winreg

            steam_path = None
            for hive, key, val in (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            ):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        steam_path = winreg.QueryValueEx(k, val)[0]
                        if steam_path:
                            break
                except Exception:
                    continue
            if not steam_path:
                return

            library_roots = [steam_path]
            vdf = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
            if os.path.exists(vdf):
                try:
                    import re
                    with open(vdf, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    for match in re.findall(r'"path"\s+"([^"]+)"', content):
                        library_roots.append(match.replace("\\\\", "\\"))
                except Exception:
                    pass

            cfg_dir = None
            for root in library_roots:
                candidate = os.path.join(
                    root, "steamapps", "common",
                    "Counter-Strike Global Offensive", "game", "csgo", "cfg"
                )
                if os.path.isdir(candidate):
                    cfg_dir = candidate
                    break
            if not cfg_dir:
                return

            cfg_path = os.path.join(cfg_dir, "gamestate_integration_autoaccept.cfg")
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        if f.read() == self.GSI_CFG_TEMPLATE:
                            return
                except Exception:
                    pass
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write(self.GSI_CFG_TEMPLATE)
        except Exception as e:
            print(f"GSI config not installed: {e}")

    def search_accept_button(self):
        import pyautogui
        buttons_dir = resource_path(os.path.join('assets', 'buttons'))
        button_images = sorted(glob.glob(os.path.join(buttons_dir, '*.png')))
        if not button_images:
            print(f"Advarsel: ingen knapp-bilder funnet i {buttons_dir}")

        while self.running.is_set():
            cs2 = self.cs2_running()
            if not cs2:
                self._last_in_match = False
            in_match = self.pause_in_match_var.get() and self.is_in_match()
            self.root.after(0, lambda im=in_match, c=cs2: self._update_status(im, c))

            if not cs2 or in_match:
                time.sleep(self.CHECK_INTERVAL)
                continue

            screen_width, screen_height = pyautogui.size()
            region = (
                (screen_width - int(screen_width * 0.4)) // 2,
                (screen_height - int(screen_height * 0.4)) // 2,
                int(screen_width * 0.4),
                int(screen_height * 0.4)
            )

            for image in button_images:
                try:
                    location = pyautogui.locateOnScreen(image, region=region, confidence=0.65)
                    if location:
                        pyautogui.click(location)
                        x, y = pyautogui.center(location)
                        pyautogui.moveTo(x, y - 250)
                        self._last_accept_time = time.time()
                        self.root.after(0, lambda: self.status_label.config(text="Match Accepted", fg=ST_ACCEPT))
                        break
                except Exception:
                    continue

            time.sleep(self.CHECK_INTERVAL)

    def start_search(self):
        self.start_button.config(state=tk.DISABLED)
        if not self.running.is_set():
            self.running.set()
            self.status_label.config(text="Waiting for match", fg=ST_WAIT, font=(FONT, 12, "bold"))
            self.start_button.config(text="Stop", command=self.stop_search)
            threading.Thread(target=self.search_accept_button, daemon=True).start()
        else:
            self.stop_search()
        self.root.after(200, lambda: self.start_button.config(state=tk.NORMAL))

    def stop_search(self):
        self.start_button.config(state=tk.DISABLED)
        self.running.clear()
        self.status_label.config(text="Stopped", fg=ST_STOP)
        self.start_button.config(text="Start", command=self.start_search)
        self.root.after(200, lambda: self.start_button.config(state=tk.NORMAL))

    def create_checkbutton(self, parent, text, variable):
        return tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            onvalue=True,
            offvalue=False,
            bg=BG,
            fg=FG,
            selectcolor=SELECT,
            activebackground=BG,
            activeforeground=FG
        )

    def clear_main_frame(self, exclude=[]):
        for widget in self.root.winfo_children():
            if widget.winfo_name() not in exclude:
                widget.destroy()

    def show_main_buttons(self):
        self.status_label.pack(pady=15)

        button_frame = tk.Frame(self.root, bg=BG)
        button_frame.pack(pady=5)

        self.start_button = tk.Button(
            button_frame,
            text="Start",
            command=self.start_search,
            fg=FG,
            bg=BG,
            font=(FONT, 12, "bold"),
            width=6,
            height=1
        )
        self.start_button.pack(side=tk.LEFT, padx=5)

        settings_button = tk.Button(
            button_frame,
            text="Settings",
            command=self.show_settings,
            fg=FG,
            bg=BG,
            font=(FONT, 12, "bold"),
            width=8,
            height=1
        )
        settings_button.pack(side=tk.LEFT, padx=5)

        about_label = tk.Label(self.root, text="About", fg=FG_DIM, bg=BG, font=(FONT, 10, "underline"), cursor="hand2")
        about_label.place(relx=0.0, rely=1.0, x=5, y=-5, anchor='sw')
        about_label.bind("<Button-1>", lambda e: self.show_about())

        footer_label = tk.Label(self.root, text="Made by Kimsec.net", fg=FG_DIM, bg=BG)
        footer_label.place(relx=1.0, rely=1.0, x=-5, y=-5, anchor='se')

    def close_settings(self, settings_frame):
        self.save_settings()
        settings_frame.destroy()
        self.root.geometry("300x130")
        self.root.title("Auto Accept")
        self.show_main_buttons()
        if self.running.is_set():
            self.start_button.config(text="Stop")

    def show_settings(self):
        self.clear_main_frame(exclude=["status_label"])
        self.status_label.pack_forget()
        self.root.geometry("300x175")
        self.root.title("Settings")

        settings_frame = tk.Frame(self.root, bg=BG)
        settings_frame.pack(fill=tk.BOTH, expand=True)

        pause_frame = tk.Frame(settings_frame, bg=BG)
        pause_frame.pack(pady=(10, 2), padx=(80, 10), anchor='w')
        self.create_checkbutton(pause_frame, "Pause search in match", self.pause_in_match_var).pack(side=tk.LEFT)
        pause_help = tk.Label(pause_frame, text="(?)", fg=FG, bg=BG, font=(FONT, 9, "normal"), cursor="hand2")
        pause_help.pack(side=tk.LEFT)
        ToolTip(pause_help, "Uses CS2 Game State Integration to detect when you're in a match.\nWhile in a match the accept-button search is paused.\nThe config file is installed automatically.")

        minimized_frame = tk.Frame(settings_frame, bg=BG)
        minimized_frame.pack(pady=2, padx=(80, 10), anchor='w')
        self.create_checkbutton(minimized_frame, "Start minimized", self.start_minimized_var).pack(side=tk.LEFT)

        tray_frame = tk.Frame(settings_frame, bg=BG)
        tray_frame.pack(pady=2, padx=(80, 10), anchor='w')
        self.create_checkbutton(tray_frame, "Exit to tray", self.minimize_to_tray_var).pack(side=tk.LEFT)

        startup_frame = tk.Frame(settings_frame, bg=BG)
        startup_frame.pack(pady=2, padx=(80, 10), anchor='w')
        self.create_checkbutton(startup_frame, "Start with Windows", self.start_with_windows_var).pack(side=tk.LEFT)

        save_button = tk.Button(
            settings_frame,
            text="Save",
            command=lambda: self.close_settings(settings_frame),
            fg=FG,
            bg=BG,
            font=(FONT, 12, "bold"),
            width=8,
            height=1
        )
        save_button.pack(pady=10)

    def close_about(self, about_frame):
        about_frame.destroy()
        self.root.geometry("300x130")
        self.root.title("Auto Accept")
        self.status_label.pack(pady=15)
        self.show_main_buttons()
        if self.running.is_set():
            self.start_button.config(text="Stop")

    def show_about(self):
        self.clear_main_frame(exclude=["status_label"])
        self.status_label.pack_forget()
        self.root.geometry("300x250")
        self.root.title("About")
        about_frame = tk.Frame(self.root, bg=BG)
        about_frame.pack(fill=tk.BOTH, expand=True)

        version = "1.0"
        author = "Kim AH"
        supported_res = "960p - 1080p - 1440p\n"
        supported_formats = "4:3 & 16:9"

        about_text = (
            f"Author: {author}\n"
            f"Version: {version}\n\n"
            f"Supported Screen Resolution: \n{supported_res}\n"
            f"Formats:\n{supported_formats}\n"
        )

        label = tk.Label(about_frame, text=about_text, fg=FG, bg=BG, font=(FONT, 10))
        label.pack(pady=10)

        update_button = tk.Button(
            about_frame,
            text="Check for update",
            fg=FG,
            bg=BG,
            font=(FONT, 10, "bold"),
            command=lambda: threading.Thread(target=self.check_update, args=(about_frame, version), daemon=True).start()
        )
        update_button.pack(pady=0)

        close_button = tk.Button(
            about_frame,
            text="Close",
            fg=FG,
            bg=BG,
            font=(FONT, 10, "bold"),
            command=lambda: self.close_about(about_frame)
        )
        close_button.pack(pady=10)

    def check_update(self, about_window, current_version):
        import requests
        try:
            response = requests.get(self.UPDATE_URL, timeout=5)
            data = response.json()
            latest_version = data.get("latest_version", current_version)
            download_url = data.get("download_url", "")
            changelog = data.get("changelog", "No changelog provided.")
            if latest_version != current_version:
                self.root.after(0, lambda: self.update_about_window(about_window, latest_version, changelog, download_url))
            else:
                self.root.after(0, lambda: messagebox.showinfo("Update", "You have the latest version!"))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Update Error", f"Error checking for update:\n{e}"))
            self.root.after(0, lambda: about_window.lift())

    def update_about_window(self, about_window, latest_version, changelog, download_url):
        import webbrowser
        for widget in about_window.winfo_children():
            widget.destroy()
        info = f"Newest version online: {latest_version}\nChangelog:\n{changelog}"
        info_label = tk.Label(about_window, text=info, fg=FG, bg=BG, font=(FONT, 10))
        info_label.pack(pady=10)
        notes_button = tk.Button(
            about_window,
            text="View release notes",
            fg=FG,
            bg=BG,
            font=(FONT, 10, "bold"),
            command=lambda: webbrowser.open(self.RELEASE_NOTES_URL)
        )
        notes_button.pack(pady=5)
        dl_button = tk.Button(
            about_window,
            text="Download",
            fg=FG,
            bg=BG,
            font=(FONT, 10, "bold"),
            command=lambda: threading.Thread(target=self.download_update, args=(download_url, latest_version), daemon=True).start()
        )
        dl_button.pack(pady=5)
        close_button = tk.Button(
            about_window,
            text="Close",
            fg=FG,
            bg=BG,
            font=(FONT, 10, "bold"),
            command=lambda: self.close_about(about_window)
        )
        close_button.pack(pady=5)

    def download_update(self, download_url, latest_version):
        import requests
        try:
            response = requests.get(download_url, stream=True)
            response.raise_for_status()
            filename = f"Auto Accept v{latest_version}.exe"
            with open(filename, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)
            self.root.after(0, lambda: messagebox.showinfo("Download Complete", f"The latest version has been downloaded successfully as {filename}."))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Download Error", f"Failed to download the update:\n{e}"))

    def create_tray_icon(self, icon_path):
        import pystray
        from PIL import Image
        image = Image.open(icon_path)

        def on_show(icon, item):
            self.root.deiconify()
            icon.stop()

        def on_exit(icon, item):
            self.root.destroy()
            icon.stop()

        menu = pystray.Menu(
            pystray.MenuItem("Show", on_show, default=True),
            pystray.MenuItem("Exit", on_exit)
        )
        tray_icon = pystray.Icon("auto_accept", image, "Auto Accept", menu)
        tray_icon.run()

    def minimize_to_tray(self, icon_path):
        self.root.withdraw()
        tray_thread = threading.Thread(target=self.create_tray_icon, args=(icon_path,), daemon=True)
        tray_thread.start()

    def create_gui(self):
        self.root = tk.Tk()
        self.root.tk.call("tk", "scaling", 1.30)
        self.root.title("Auto Accept")
        self.root.geometry("300x130")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        if os.path.exists(self.ICON_FILE):
            self.icon_image = tk.PhotoImage(file=self.ICON_FILE)
            self.root.iconphoto(False, self.icon_image)
        else:
            print(f"Ikonfil ikke funnet: {self.ICON_FILE}")

        if self.win_x is not None and self.win_y is not None:
            self.root.geometry(f"+{self.win_x}+{self.win_y}")
        else:
            self.root.eval('tk::PlaceWindow . center')
        self.status_label = tk.Label(self.root, text="Stopped", fg=ST_STOP, bg=BG, font=(FONT, 12, "bold"), name="status_label")
        self.status_label.pack(pady=20)

        self.start_minimized_var = tk.BooleanVar(value=self.start_minimized_val)
        self.minimize_to_tray_var = tk.BooleanVar(value=self.minimize_to_tray_val)
        self.pause_in_match_var = tk.BooleanVar(value=self.pause_in_match_val)
        self.start_with_windows_var = tk.BooleanVar(value=self.start_with_windows_val)

        self.show_main_buttons()

        def on_closing():
            self.save_position()
            if self.minimize_to_tray_var.get():
                self.minimize_to_tray(self.ICON_FILE)
            else:
                self.root.destroy()

        self.root.protocol("WM_DELETE_WINDOW", on_closing)

        if self.start_minimized_var.get():
            if self.minimize_to_tray_var.get():
                self.root.after(100, lambda: self.minimize_to_tray(self.ICON_FILE))
            else:
                self.root.after(100, self.root.iconify)

        threading.Thread(target=self.start_gsi_server, daemon=True).start()
        threading.Thread(target=self.install_gsi_config, daemon=True).start()

        self.root.after(200, self.start_search)
        self.root.mainloop()

if __name__ == "__main__":
    import ctypes
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "AutoAcceptAppMutex")
    if ctypes.windll.kernel32.GetLastError() == 183:
        ctypes.windll.user32.MessageBoxW(0, "Auto Accept is already running.", "Error", 0x10)
        sys.exit(0)
    AutoAcceptApp()
