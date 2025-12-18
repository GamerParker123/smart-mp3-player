import os
import json
import random
import datetime
import time
import math
import vlc
import sys
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
from PIL import Image, ImageTk, ImageDraw, ImageFilter
import io

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

DATA_FILE = resource_path("song_data.json")

# VLC setup
def init_vlc():
    """
    Initialize VLC instance and media player.
    Works for both normal Python and PyInstaller exe.
    """
    vlc_folder = resource_path("VLC")
    if os.path.exists(vlc_folder):
        os.add_dll_directory(vlc_folder)

    try:
        instance = vlc.Instance([
            "--audio-filter=compressor",
            "--compressor-attack=20",
            "--compressor-release=200",
            "--compressor-threshold=-18",
            "--compressor-ratio=3.0",
            "--compressor-knee=6",
            "--compressor-makeup=8"
        ])
        player = instance.media_player_new()
        return instance, player
    except Exception as e:
        messagebox.showerror("VLC Error", f"Failed to initialize VLC: {e}\n"
                                          f"Make sure VLC is included and DLLs are accessible.")
        sys.exit(1)

class RoundedButton(tk.Canvas):
    def __init__(self, parent, text, command, bg, fg, active_bg, width=200, height=40, corner_radius=20):
        super().__init__(parent, width=width, height=height, bg=parent['bg'], highlightthickness=0)
        self.command = command
        self.bg = bg
        self.fg = fg
        self.active_bg = active_bg
        self.corner_radius = corner_radius
        self.text = text
        
        self.draw_button(bg, fg)
        self.bind("<Button-1>", self.on_click)
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
    
    def draw_button(self, bg_color, fg_color):
        self.delete("all")
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        r = self.corner_radius
        
        self.create_arc(0, 0, r*2, r*2, start=90, extent=90, fill=bg_color, outline="")
        self.create_arc(w-r*2, 0, w, r*2, start=0, extent=90, fill=bg_color, outline="")
        self.create_arc(0, h-r*2, r*2, h, start=180, extent=90, fill=bg_color, outline="")
        self.create_arc(w-r*2, h-r*2, w, h, start=270, extent=90, fill=bg_color, outline="")
        self.create_rectangle(r, 0, w-r, h, fill=bg_color, outline="")
        self.create_rectangle(0, r, w, h-r, fill=bg_color, outline="")
        
        self.create_text(w//2, h//2, text=self.text, fill=fg_color, font=("Segoe UI", 11, "bold"))
    
    def on_click(self, event):
        self.command()
    
    def on_enter(self, event):
        self.draw_button(self.active_bg, self.fg)
    
    def on_leave(self, event):
        self.draw_button(self.bg, self.fg)

class MusicPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("♪ Smart MP3 Player")
        self.root.geometry("480x720")
        self.root.resizable(False, False)
        
        self.vlc_instance, self.media_player = init_vlc()

        self.data = self.load_data()
        if self.data:
            self.files = list(self.data.keys())
        else:
            self.files = []

        self.current_song = None
        self.repeat_limit = 150
        self.recent_songs = []
        self.transition_scheduled = False

        self.song_duration = 0
        self.progress_update_interval = 1000
        self.root.after(self.progress_update_interval, self.update_progress)

        # Enhanced Miku color palette
        self.bg_gradient_top = "#0a0e27"
        self.bg_gradient_bottom = "#1a1a2e"
        self.card_bg = "#16213e"
        self.accent_cyan = "#39c5bb"
        self.accent_pink = "#e94560"
        self.text_primary = "#ffffff"
        self.text_secondary = "#a0a8b9"
        self.glow_color = "#00ffff"

        self.setup_ui()
        self.root.after(1000, self.check_song_end)

    def setup_ui(self):
        # Main container with gradient effect
        main_frame = tk.Frame(self.root, bg=self.bg_gradient_bottom)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header section with glow effect
        header_frame = tk.Frame(main_frame, bg=self.bg_gradient_top, height=80)
        header_frame.pack(fill=tk.X, pady=(0, 20))
        header_frame.pack_propagate(False)

        title_label = tk.Label(header_frame, text="♪ MUSIC PLAYER", 
                               font=("Segoe UI", 24, "bold"), 
                               bg=self.bg_gradient_top, 
                               fg=self.accent_cyan)
        title_label.pack(pady=20)

        # Album art section with modern styling
        art_container = tk.Frame(main_frame, bg=self.card_bg, width=200, height=200)
        art_container.pack(pady=10)
        art_container.pack_propagate(False)

        self.album_art_label = tk.Label(art_container, bg=self.card_bg)
        self.album_art_label.pack(expand=True)

        # Song info section
        info_frame = tk.Frame(main_frame, bg=self.bg_gradient_bottom)
        info_frame.pack(pady=10)

        self.label = tk.Label(info_frame, text="Ready to play", 
                             font=("Segoe UI", 13, "bold"), 
                             bg=self.bg_gradient_bottom, 
                             fg=self.text_primary)
        self.label.pack()

        self.artist_label = tk.Label(info_frame, text="", 
                                     font=("Segoe UI", 10), 
                                     bg=self.bg_gradient_bottom, 
                                     fg=self.text_secondary)
        self.artist_label.pack(pady=(5, 0))

        # Progress section
        progress_frame = tk.Frame(main_frame, bg=self.bg_gradient_bottom)
        progress_frame.pack(pady=15, padx=40, fill=tk.X)

        # Custom progress bar style
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Miku.Horizontal.TProgressbar",
                       troughcolor=self.card_bg,
                       background=self.accent_cyan,
                       borderwidth=0,
                       thickness=8)

        self.progress = ttk.Progressbar(progress_frame, 
                                       orient="horizontal", 
                                       length=400, 
                                       mode="determinate",
                                       style="Miku.Horizontal.TProgressbar")
        self.progress.pack(fill=tk.X)
        self.progress.bind("<Button-1>", self.seek)

        self.time_label = tk.Label(progress_frame, text="0:00 / 0:00", 
                                   font=("Segoe UI", 9), 
                                   bg=self.bg_gradient_bottom, 
                                   fg=self.text_secondary)
        self.time_label.pack(pady=(5, 0))

        # Control buttons
        control_frame = tk.Frame(main_frame, bg=self.bg_gradient_bottom)
        control_frame.pack(pady=15)

        btn_width, btn_height = 100, 40

        like_btn = RoundedButton(control_frame, "♥ Like", 
                                lambda: self.vote_current_song(1.1),
                                self.accent_cyan, self.text_primary, self.accent_pink,
                                width=btn_width, height=btn_height)
        like_btn.grid(row=0, column=0, padx=5, pady=5)

        self.pause_button_widget = RoundedButton(control_frame, "⏸ Pause", 
                                                self.toggle_pause,
                                                self.card_bg, self.text_primary, self.accent_cyan,
                                                width=btn_width, height=btn_height)
        self.pause_button_widget.grid(row=0, column=1, padx=5, pady=5)

        dislike_btn = RoundedButton(control_frame, "✗ Dislike", 
                                   lambda: self.vote_current_song(0.9),
                                   self.accent_pink, self.text_primary, self.accent_cyan,
                                   width=btn_width, height=btn_height)
        dislike_btn.grid(row=0, column=2, padx=5, pady=5)

        play_btn = RoundedButton(control_frame, "▶ Play Next", 
                                self.play_next_song,
                                self.accent_cyan, self.text_primary, self.accent_pink,
                                width=220, height=50)
        play_btn.grid(row=1, column=0, columnspan=3, pady=10)

        # Volume control
        volume_frame = tk.Frame(main_frame, bg=self.bg_gradient_bottom)
        volume_frame.pack(pady=10)

        vol_label = tk.Label(volume_frame, text="🔊", 
                            font=("Segoe UI", 12), 
                            bg=self.bg_gradient_bottom, 
                            fg=self.text_secondary)
        vol_label.pack(side=tk.LEFT, padx=(0, 10))

        style.configure("Miku.Horizontal.TScale",
                       background=self.bg_gradient_bottom,
                       troughcolor=self.card_bg,
                       borderwidth=0,
                       sliderthickness=18)

        self.volume_slider = ttk.Scale(volume_frame,
                                      from_=0,
                                      to=100,
                                      orient="horizontal",
                                      command=self.set_volume,
                                      length=250,
                                      style="Miku.Horizontal.TScale")
        self.volume_slider.set(self.media_player.audio_get_volume())
        self.volume_slider.pack(side=tk.LEFT)

        # Management buttons
        mgmt_frame = tk.Frame(main_frame, bg=self.bg_gradient_bottom)
        mgmt_frame.pack(pady=15)

        add_btn = RoundedButton(mgmt_frame, "+ Add Songs", 
                               self.add_songs,
                               self.card_bg, self.text_primary, self.accent_cyan,
                               width=140, height=35)
        add_btn.grid(row=0, column=0, padx=5)

        folder_btn = RoundedButton(mgmt_frame, "📁 Add Folder", 
                                  self.add_folder,
                                  self.card_bg, self.text_primary, self.accent_cyan,
                                  width=140, height=35)
        folder_btn.grid(row=0, column=1, padx=5)

        remove_btn = RoundedButton(mgmt_frame, "✗ Remove", 
                                  self.remove_songs,
                                  self.card_bg, self.text_primary, self.accent_pink,
                                  width=140, height=35)
        remove_btn.grid(row=1, column=0, padx=5, pady=5)

        reset_btn = RoundedButton(mgmt_frame, "↻ Reset Votes", 
                                 self.reset_vote_weights,
                                 self.card_bg, self.text_primary, self.accent_cyan,
                                 width=140, height=35)
        reset_btn.grid(row=1, column=1, padx=5, pady=5)

    def show_song_info(self, filepath):
        try:
            audio = MP3(filepath, ID3=ID3)
            tags = audio.tags

            artist_tag = tags.get("TPE1")
            artist_name = artist_tag.text[0] if artist_tag else "Unknown Artist"
            self.artist_label.config(text=artist_name)

            apic_key = next((k for k in tags.keys() if k.startswith("APIC")), None)
            if apic_key:
                img_data = tags[apic_key].data
                image = Image.open(io.BytesIO(img_data))
            else:
                image = self.create_default_art()

            # Round corners and add shadow effect
            image = image.resize((180, 180))
            image = self.add_rounded_corners(image, 20)
            
            self.album_art = ImageTk.PhotoImage(image)
            self.album_art_label.config(image=self.album_art)

        except Exception as e:
            print(f"Failed to load song info: {e}")
            self.artist_label.config(text="Unknown Artist")
            image = self.create_default_art()
            image = self.add_rounded_corners(image, 20)
            self.album_art = ImageTk.PhotoImage(image)
            self.album_art_label.config(image=self.album_art)

    def create_default_art(self):
        """Create a gradient default album art"""
        img = Image.new("RGB", (180, 180), color="#16213e")
        draw = ImageDraw.Draw(img)
        
        # Draw gradient circles
        for i in range(0, 180, 20):
            alpha = int(255 * (1 - i/180))
            color = f"#{57:02x}{197:02x}{187:02x}"  # Cyan
            draw.ellipse([90-i, 90-i, 90+i, 90+i], outline=color, width=2)
        
        return img

    def add_rounded_corners(self, image, radius):
        """Add rounded corners to image"""
        mask = Image.new('L', image.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([(0, 0), image.size], radius, fill=255)
        
        result = Image.new('RGBA', image.size)
        result.paste(image, (0, 0))
        result.putalpha(mask)
        
        return result
    
    def set_volume(self, val):
        volume = int(float(val))
        if self.media_player is not None:
            self.media_player.audio_set_volume(volume)

    def load_data(self):
        if not os.path.exists(DATA_FILE):
            return {}
        if os.path.getsize(DATA_FILE) == 0:
            return {}
        try:
            with open(DATA_FILE, "r", encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def save_data(self, data):
        with open(DATA_FILE, "w", encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

    def add_songs(self):
        files = filedialog.askopenfilenames(
            title="Select MP3 files",
            filetypes=[("MP3 Files", "*.mp3")]
        )
        if files:
            for f in files:
                filename = os.path.basename(f)
                if filename not in self.data:
                    self.data[filename] = {
                        "last_played": "2000-01-01",
                        "vote_weight": 1.0,
                        "path": f
                    }
            self.files = [f for f in self.data]
            self.save_data(self.data)
            messagebox.showinfo("✓ Added", f"{len(files)} song(s) added.")

    def add_folder(self):
        folder = filedialog.askdirectory(title="Select Music Folder")
        if folder:
            new_files = [f for f in os.listdir(folder) if f.endswith(".mp3")]
            for f in new_files:
                filename = os.path.basename(f)
                full_path = os.path.join(folder, f)
                if filename not in self.data:
                    self.data[filename] = {
                        "last_played": "2000-01-01",
                        "vote_weight": 1.0,
                        "path": full_path
                    }
            self.files = [f for f in self.data]
            self.save_data(self.data)
            messagebox.showinfo("✓ Added", f"{len(new_files)} song(s) added from folder.")
    
    def remove_songs(self):
        if not self.data:
            messagebox.showinfo("No Songs", "No songs to remove.")
            return

        remove_window = tk.Toplevel(self.root)
        remove_window.title("Remove Songs")
        remove_window.geometry("400x500")
        remove_window.configure(bg=self.bg_gradient_bottom)

        header = tk.Label(remove_window, text="Remove Songs", 
                         font=("Segoe UI", 16, "bold"),
                         bg=self.bg_gradient_bottom, fg=self.accent_cyan)
        header.pack(pady=15)

        search_frame = tk.Frame(remove_window, bg=self.bg_gradient_bottom)
        search_frame.pack(pady=10, padx=20, fill=tk.X)

        tk.Label(search_frame, text="🔍", font=("Segoe UI", 12),
                bg=self.bg_gradient_bottom, fg=self.text_secondary).pack(side=tk.LEFT, padx=(0, 5))

        search_var = tk.StringVar()
        search_entry = tk.Entry(search_frame, textvariable=search_var, 
                               font=("Segoe UI", 10),
                               bg=self.card_bg, fg=self.text_primary,
                               insertbackground=self.accent_cyan,
                               relief=tk.FLAT, borderwidth=2)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)

        listbox_frame = tk.Frame(remove_window, bg=self.card_bg)
        listbox_frame.pack(expand=True, fill=tk.BOTH, padx=20, pady=10)

        scrollbar = tk.Scrollbar(listbox_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        listbox = tk.Listbox(listbox_frame, selectmode=tk.MULTIPLE,
                           bg=self.card_bg, fg=self.text_primary,
                           selectbackground=self.accent_cyan,
                           selectforeground=self.text_primary,
                           font=("Segoe UI", 9),
                           relief=tk.FLAT,
                           yscrollcommand=scrollbar.set)
        listbox.pack(expand=True, fill=tk.BOTH)
        scrollbar.config(command=listbox.yview)

        for song in self.data:
            listbox.insert(tk.END, song)

        def update_listbox(*args):
            search_text = search_var.get().lower()
            listbox.delete(0, tk.END)
            for song in self.data:
                if search_text in song.lower():
                    listbox.insert(tk.END, song)

        search_var.trace_add("write", update_listbox)

        def confirm_removal():
            selected_indices = listbox.curselection()
            if not selected_indices:
                return
            for index in reversed(selected_indices):
                song = listbox.get(index)
                if song == self.current_song:
                    self.media_player.stop()
                    self.current_song = None
                del self.data[song]
                if song in self.files:
                    self.files.remove(song)
                if song in self.recent_songs:
                    self.recent_songs.remove(song)
                listbox.delete(index)
            self.save_data(self.data)
            messagebox.showinfo("✓ Removed", "Selected songs removed.")

        btn_frame = tk.Frame(remove_window, bg=self.bg_gradient_bottom)
        btn_frame.pack(pady=15)

        remove_btn = RoundedButton(btn_frame, "✗ Remove Selected", 
                                  confirm_removal,
                                  self.accent_pink, self.text_primary, 
                                  self.accent_cyan,
                                  width=180, height=40)
        remove_btn.pack()

    def drift_toward_one(self, vote_weight, hours_since_played, half_life_hours=100):
        if vote_weight == 1.0:
            return 1.0
        decay_factor = 0.5 ** (hours_since_played / half_life_hours)
        return 1.0 + (vote_weight - 1.0) * decay_factor

    def get_scores(self):
        scores = {}
        now = datetime.datetime.now()
        for song, meta in self.data.items():
            delta = now - datetime.datetime.fromisoformat(meta["last_played"])
            hours = delta.total_seconds() / 3600

            original_weight = meta["vote_weight"]
            adjusted_weight = self.drift_toward_one(original_weight, hours)
            adjusted_weight = self.clamp_weight(adjusted_weight)

            time_score = math.log1p(max(hours, 0.1))
            score = time_score * adjusted_weight
            scores[song] = score

        return scores
    
    def clamp_weight(self, weight):
        return min(max(weight, 0.5), 2.0)

    def reset_vote_weights(self):
        for song in self.data:
            self.data[song]["vote_weight"] = 1.0
        self.save_data(self.data)
        messagebox.showinfo("✓ Reset", "All vote weights reset to 1.0")

    def vote_current_song(self, multiplier):
        if not self.current_song:
            return
        self.data[self.current_song]["vote_weight"] = self.clamp_weight(
            self.data[self.current_song]["vote_weight"] * multiplier
        )
        weight = self.data[self.current_song]['vote_weight']
        self.label.config(text=f"♪ {self.current_song[:30]}... (×{weight:.2f})")
        self.save_data(self.data)

    def pick_song(self, scores):
        if not scores:
            return None

        limit = min(self.repeat_limit, len(scores))
        available_songs = {song: score for song, score in scores.items() 
                          if song not in self.recent_songs}

        if not available_songs:
            available_songs = scores

        total = sum(available_songs.values())
        if total == 0:
            song = random.choice(list(available_songs.keys()))
        else:
            r = random.uniform(0, total)
            cumulative = 0
            for song, score in available_songs.items():
                cumulative += score
                if r <= cumulative:
                    break

        self.recent_songs.append(song)
        if len(self.recent_songs) > limit:
            self.recent_songs.pop(0)

        return song

    def play_song(self, path):
        media = self.vlc_instance.media_new(path)
        self.media_player.set_media(media)
        self.media_player.play()
        self.playback_started_time = datetime.datetime.now()
        self.root.after(100, self.set_song_duration)
    
    def set_song_duration(self):
        duration = self.media_player.get_length() / 1000
        if duration > 0:
            self.song_duration = duration
        else:
            self.root.after(100, self.set_song_duration)
    
    def format_time(self, seconds):
        minutes = int(seconds) // 60
        sec = int(seconds) % 60
        return f"{minutes}:{sec:02d}"

    def update_progress(self):
        try:
            if self.song_duration > 0:
                current_pos = self.media_player.get_time() / 1000
                percent = min((current_pos / self.song_duration) * 100, 100)
                self.progress["value"] = percent

                elapsed = self.format_time(current_pos)
                total = self.format_time(self.song_duration)
                self.time_label.config(text=f"{elapsed} / {total}")
            else:
                self.progress["value"] = 0
                self.time_label.config(text="0:00 / 0:00")
        except Exception as e:
            print(f"Progress update error: {e}")
            self.progress["value"] = 0
            self.time_label.config(text="0:00 / 0:00")

        self.root.after(self.progress_update_interval, self.update_progress)

    def seek(self, event):
        if not self.current_song or self.song_duration <= 0:
            return

        click_x = event.x
        total_width = self.progress.winfo_width()
        fraction = click_x / total_width
        new_time = int(fraction * self.song_duration * 1000)

        self.media_player.set_time(new_time)

    def check_song_end(self):
        if self.current_song:
            state = self.media_player.get_state()
            if state == vlc.State.Ended and not self.transition_scheduled:
                self.transition_scheduled = True
                self.root.after(1000, self._transition_to_next)
        self.root.after(1000, self.check_song_end)

    def _transition_to_next(self):
        self.play_next_song()
        self.transition_scheduled = False

    def toggle_pause(self):
        if not self.current_song:
            return
        if self.media_player.is_playing():
            self.media_player.pause()
            self.pause_button_widget.text = "▶ Resume"
            self.pause_button_widget.draw_button(self.pause_button_widget.bg, 
                                                 self.pause_button_widget.fg)
        else:
            self.media_player.play()
            self.pause_button_widget.text = "⏸ Pause"
            self.pause_button_widget.draw_button(self.pause_button_widget.bg, 
                                                 self.pause_button_widget.fg)

    def play_next_song(self):
        scores = self.get_scores()
        song = self.pick_song(scores)
        
        self.pause_button_widget.text = "⏸ Pause"
        self.pause_button_widget.draw_button(self.pause_button_widget.bg, 
                                            self.pause_button_widget.fg)
        
        if song is None:
            self.label.config(text="No songs to play")
            return

        path = self.data[song]["path"]
        
        if not os.path.exists(path):
            self.label.config(text=f"File not found: {song}")
            del self.data[song]
            if song in self.files:
                self.files.remove(song)
            self.save_data(self.data)
            self.root.after(100, self.play_next_song)
            return
            
        self.play_song(path)
        self.current_song = song
        
        # Truncate long song names
        display_name = song if len(song) <= 35 else song[:32] + "..."
        self.label.config(text=f"♪ {display_name}")
        
        self.data[song]["last_played"] = datetime.datetime.now().isoformat()
        self.save_data(self.data)
        self.show_song_info(path)

if __name__ == "__main__":
    root = tk.Tk()
    app = MusicPlayer(root)
    root.mainloop()