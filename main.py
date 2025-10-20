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
from PIL import Image, ImageTk
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
    # Try to find VLC dlls relative to exe/script
    vlc_folder = resource_path("VLC")  # Include VLC folder in your project
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

class MusicPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("Smart MP3 Player")
        self.root.geometry("400x300")
        
        self.vlc_instance, self.media_player = init_vlc()

        self.data = self.load_data()
        self.files = [song for song, meta in self.data.items() if os.path.exists(meta.get("path", ""))]
        # Remove any songs that no longer exist
        removed = set(self.data.keys()) - set(self.files)
        for song in removed:
            del self.data[song]

        self.save_data(self.data)

        self.current_song = None
        self.repeat_limit = 150  # hard limit for repeats
        self.recent_songs = []  # tracks recently played songs

        self.song_duration = 0
        self.progress_update_interval = 1000  # ms
        self.root.after(self.progress_update_interval, self.update_progress)

        self.root.configure(bg="#1a1a2e")  # Dark navy background

        # Theme colors
        self.primary_bg = "#1a1a2e"   # background
        self.secondary_bg = "#162447" # darker panels/buttons
        self.accent_color = "#00d4ff" # Miku cyan/aqua
        self.text_color = "#ffffff"   # white text
        self.highlight_color = "#f29ca3"  # optional pink accent

        # Update all widgets to match theme
        def themed_label(text):
            return tk.Label(self.root, text=text, bg=self.primary_bg, fg=self.accent_color, font=("Helvetica", 11))

        def themed_button(text, command):
            return tk.Button(self.root, text=text, command=command, bg=self.secondary_bg, fg=self.text_color,
                            activebackground=self.accent_color, activeforeground=self.primary_bg, relief=tk.FLAT)

        # Replace your widgets with themed ones
        self.label = themed_label("Welcome to Smart MP3 Player")
        self.label.pack(pady=10)

        self.upload_file_button = themed_button("Add Song(s)", self.add_songs)
        self.upload_file_button.pack(pady=5)

        self.upload_folder_button = themed_button("Select Folder", self.add_folder)
        self.upload_folder_button.pack(pady=5)

        self.remove_button = themed_button("Remove Song(s)", self.remove_songs)
        self.remove_button.pack(pady=5)

        self.play_button = themed_button("Play Next Song", self.play_next_song)
        self.play_button.pack(pady=5)

        self.like_button = themed_button("+ (Like)", lambda: self.vote_current_song(1.1))
        self.like_button.pack(pady=5)

        self.dislike_button = themed_button("- (Dislike)", lambda: self.vote_current_song(0.9))
        self.dislike_button.pack(pady=5)

        self.reset_button = themed_button("Reset Votes", self.reset_vote_weights)
        self.reset_button.pack(pady=5)

        self.pause_button = themed_button("Pause", self.toggle_pause)
        self.pause_button.pack(pady=5)

        # Progress bar with custom style
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TProgressbar",
                        troughcolor=self.secondary_bg,
                        background=self.accent_color,
                        thickness=20)
        self.progress = ttk.Progressbar(self.root, orient="horizontal", length=300, mode="determinate", style="TProgressbar")
        self.progress.pack(pady=5)
        self.progress.bind("<Button-1>", self.seek)

        self.time_label = themed_label("0:00 / 0:00")
        self.time_label.pack()

        self.root.after(1000, self.check_song_end)

        # In __init__ after defining your theme colors
        style = ttk.Style(self.root)
        style.theme_use("default")

        # Custom style for volume slider
        style.configure(
            "TScale",
            background=self.primary_bg,      # background behind trough
            troughcolor=self.secondary_bg,   # the bar background
        )

        style.map(
            "TScale",
            sliderrelief=[("active", "flat"), ("!active", "flat")]
        )

        # Now create the volume slider with the style
        self.volume_slider = ttk.Scale(
            self.root,
            from_=0,
            to=100,
            orient="horizontal",
            command=self.set_volume,
            length=200,
            style="TScale"
        )
        self.volume_slider.set(self.media_player.audio_get_volume())
        self.volume_slider.pack(pady=5)

        self.album_art_label = tk.Label(self.root, bg=self.primary_bg)
        self.album_art_label.pack(pady=5)
        
        self.artist_label = tk.Label(self.root, text="", bg=self.primary_bg, fg=self.accent_color, font=("Helvetica", 10))
        self.artist_label.pack(pady=2)

    def show_song_info(self, filepath):
        try:
            audio = MP3(filepath, ID3=ID3)
            tags = audio.tags

            # Artist
            artist_tag = tags.get("TPE1")
            artist_name = artist_tag.text[0] if artist_tag else "Unknown Artist"
            self.artist_label.config(text=artist_name)

            # Album art
            apic_key = next((k for k in tags.keys() if k.startswith("APIC")), None)
            if apic_key:
                img_data = tags[apic_key].data
                image = Image.open(io.BytesIO(img_data))
            else:
                image = Image.new("RGB", (150, 150), color=self.secondary_bg)

            image = image.resize((150, 150))
            self.album_art = ImageTk.PhotoImage(image)
            self.album_art_label.config(image=self.album_art)

        except Exception as e:
            print(f"Failed to load song info: {e}")
            self.artist_label.config(text="Unknown Artist")
            image = Image.new("RGB", (150, 150), color=self.secondary_bg)
            self.album_art = ImageTk.PhotoImage(image)
            self.album_art_label.config(image=self.album_art)
    
    # Function to update volume
    def set_volume(self, val):
        volume = int(float(val))  # Tkinter passes strings
        if self.media_player is not None:
            self.media_player.audio_set_volume(volume)

    def load_data(self):
        if not os.path.exists(DATA_FILE):
            return {}
        if os.path.getsize(DATA_FILE) == 0:  # empty file
            return {}
        with open(DATA_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}  # fallback if file is corrupted

    def save_data(self, data):
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def init_song_data(self, files, data):
        for file in files:
            if file not in data:
                data[file] = {
                    "last_played": "2000-01-01",
                    "vote_weight": 1.0
                }
            else:
                data[file]["vote_weight"] = self.clamp_weight(data[file].get("vote_weight", 1.0))

        for song in list(data.keys()):
            if song not in files:
                print(f"⚠️ Removing missing song from data: {song}")
                del data[song]
        
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
                        "path": f  # store full path
                    }
            self.files = [f for f in self.data]  # refresh playlist
            self.save_data(self.data)
            messagebox.showinfo("Added", f"{len(files)} song(s) added.")

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
            self.files = [f for f in self.data]  # refresh playlist
            self.save_data(self.data)
            messagebox.showinfo("Added", f"{len(new_files)} song(s) added from folder.")
    
    def remove_songs(self):
        if not self.data:
            messagebox.showinfo("No Songs", "No songs to remove.")
            return

        remove_window = tk.Toplevel(self.root)
        remove_window.title("Remove Songs")
        remove_window.geometry("350x450")

        tk.Label(remove_window, text="Search song to remove:").pack(pady=5)
        search_var = tk.StringVar()
        search_entry = tk.Entry(remove_window, textvariable=search_var)
        search_entry.pack(pady=5, padx=10, fill=tk.X)

        listbox = tk.Listbox(remove_window, selectmode=tk.MULTIPLE)
        listbox.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)

        # Populate listbox initially
        for song in self.data:
            listbox.insert(tk.END, song)

        # Update listbox based on search
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
            for index in reversed(selected_indices):  # remove from end to avoid index shift
                song = listbox.get(index)
                if song == self.current_song:
                    self.media_player.stop()
                    self.current_song = None
                # Remove from data, files, and recently played queue
                del self.data[song]
                if song in self.files:
                    self.files.remove(song)
                if song in self.recent_songs:
                    self.recent_songs.remove(song)
                listbox.delete(index)
            self.save_data(self.data)
            messagebox.showinfo("Removed", "Selected songs have been removed.")

        tk.Button(remove_window, text="Remove Selected", command=confirm_removal).pack(pady=5)

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
            meta["vote_weight"] = adjusted_weight

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
        messagebox.showinfo("Reset", "✅ All vote weights reset to 1.0.")

    def vote_current_song(self, multiplier):
        if not self.current_song:
            return
        self.data[self.current_song]["vote_weight"] = self.clamp_weight(self.data[self.current_song]["vote_weight"] * multiplier)
        self.label.config(text=f"{self.current_song} weight: {self.data[self.current_song]['vote_weight']:.2f}")
        self.save_data(self.data)

    def pick_song(self, scores):
        if not scores:
            return None

        # Determine actual repeat limit (cannot exceed song count)
        limit = min(self.repeat_limit, len(scores))

        # Exclude songs in the recent_songs queue
        available_songs = {song: score for song, score in scores.items() if song not in self.recent_songs}

        if not available_songs:
            # If all songs are in recent_songs, reset the available list
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

        # Update recent songs queue
        self.recent_songs.append(song)
        if len(self.recent_songs) > limit:
            self.recent_songs.pop(0)  # remove oldest entry

        return song

    def play_song(self, path):
        media = self.vlc_instance.media_new(path)
        self.media_player.set_media(media)
        self.media_player.play()

        self.playback_started_time = datetime.datetime.now()  # mark when started

        self.root.after(100, self.set_song_duration)
    
    def set_song_duration(self):
        duration = self.media_player.get_length() / 1000  # milliseconds to seconds
        if duration > 0:
            self.song_duration = duration
        else:
            # Try again shortly if metadata hasn't loaded yet
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
        new_time = int(fraction * self.song_duration * 1000)  # ms

        self.media_player.set_time(new_time)

    def check_song_end(self):
        if self.current_song:
            state = self.media_player.get_state()
            # Only move to next song if actually ended
            if state == vlc.State.Ended:
                self.root.after(1000, self.play_next_song)
        self.root.after(1000, self.check_song_end)

    def toggle_pause(self):
        if not self.current_song:
            return
        if self.media_player.is_playing():
            self.media_player.pause()
            self.pause_button.config(text="Resume")
        else:
            self.media_player.play()
            self.pause_button.config(text="Pause")

    def play_next_song(self):
        scores = self.get_scores()
        song = self.pick_song(scores)
        self.pause_button.config(text="Pause")
        if song is None:
            self.label.config(text="No songs to play.")
            return

        path = self.data[song]["path"]
        self.play_song(path)
        self.current_song = song
        self.label.config(text=f"Playing: {song}")
        self.data[song]["last_played"] = datetime.datetime.now().isoformat()
        self.save_data(self.data)

        # Update album art and artist info
        self.show_song_info(path)

if __name__ == "__main__":
    root = tk.Tk()
    app = MusicPlayer(root)
    root.mainloop()