#!/usr/bin/env python3
"""GUI do generowania ikon .ico/.png dla aplikacji RM."""

import os
import re
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageFont, ImageTk


DEFAULT_BG_COLOR = "#dc3545"
DEFAULT_TEXT_COLOR = (255, 255, 255)
DEFAULT_ICON_SIZE = 256
ICON_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def hex_to_rgb(color_hex):
    color_hex = color_hex.lstrip("#")
    return tuple(int(color_hex[index:index + 2], 16) for index in (0, 2, 4))


def get_default_font_path():
    candidates = [
        "arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        if os.path.isabs(candidate):
            if os.path.exists(candidate):
                return candidate
            continue
        try:
            ImageFont.truetype(candidate, 32)
            return candidate
        except OSError:
            continue
    return None


def load_font(font_size, font_path=None):
    if font_path:
        try:
            return ImageFont.truetype(font_path, font_size)
        except OSError:
            pass

    default_font_path = get_default_font_path()
    if default_font_path:
        try:
            return ImageFont.truetype(default_font_path, font_size)
        except OSError:
            pass

    return ImageFont.load_default()


def render_icon_image(text, font_size, bg_color, font_path=None, size=DEFAULT_ICON_SIZE):
    clean_text = (text or "?").strip() or "?"
    img = Image.new("RGBA", (size, size), hex_to_rgb(bg_color))
    draw = ImageDraw.Draw(img)
    font = load_font(font_size, font_path)

    bbox = draw.textbbox((0, 0), clean_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (size - text_width) // 2 - bbox[0]
    y = (size - text_height) // 2 - bbox[1]
    draw.text((x, y), clean_text, fill=DEFAULT_TEXT_COLOR, font=font)
    return img


def create_icon(text, output_path, font_size, bg_color=DEFAULT_BG_COLOR, font_path=None, size=DEFAULT_ICON_SIZE):
    img = render_icon_image(text, font_size, bg_color, font_path=font_path, size=size)
    img.save(output_path, format="ICO", sizes=ICON_SIZES)

    png_path = str(Path(output_path).with_suffix(".png"))
    img.save(png_path, format="PNG")
    return output_path, png_path


class IconGeneratorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Generator ikon RM")
        self.root.resizable(False, False)

        self.script_dir = Path(__file__).resolve().parent
        self.default_font_path = get_default_font_path()
        self.selected_font_path = self.default_font_path
        self.preview_photo = None

        self.text_var = tk.StringVar(value="IMP")
        self.font_size_var = tk.StringVar(value="148")
        self.bg_color_var = tk.StringVar(value=DEFAULT_BG_COLOR)
        self.output_path_var = tk.StringVar(value=str(self.script_dir / "rm_imp_icon.ico"))
        self.font_label_var = tk.StringVar(value=self._font_label_text())
        self.status_var = tk.StringVar(value="Gotowe")

        self._build_ui()
        self._bind_events()
        self.update_preview()

    def _font_label_text(self):
        if self.selected_font_path:
            return Path(self.selected_font_path).name
        return "Domyślna PIL"

    def _build_ui(self):
        frame = ttk.Frame(self.root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frame, text="Tekst:").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self.text_var, width=24).grid(row=0, column=1, columnspan=2, sticky="ew", pady=(0, 8))

        ttk.Label(frame, text="Wysokość czcionki:").grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self.font_size_var, width=10).grid(row=1, column=1, sticky="w", pady=(0, 8))
        ttk.Label(frame, text="px").grid(row=1, column=2, sticky="w", pady=(0, 8))

        ttk.Label(frame, text="Czcionka:").grid(row=2, column=0, sticky="w", pady=(0, 8))
        ttk.Label(frame, textvariable=self.font_label_var).grid(row=2, column=1, sticky="w", pady=(0, 8))
        ttk.Button(frame, text="Wybierz .ttf/.otf", command=self.choose_font).grid(row=2, column=2, sticky="e", pady=(0, 8))

        ttk.Label(frame, text="Kolor tła:").grid(row=3, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self.bg_color_var, width=12).grid(row=3, column=1, sticky="w", pady=(0, 8))
        ttk.Button(frame, text="Wybierz kolor", command=self.choose_color).grid(row=3, column=2, sticky="e", pady=(0, 8))

        ttk.Label(frame, text="Plik wynikowy:").grid(row=4, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self.output_path_var, width=40).grid(row=4, column=1, columnspan=2, sticky="ew", pady=(0, 8))

        button_row = ttk.Frame(frame)
        button_row.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(4, 12))
        ttk.Button(button_row, text="Zapisz jako...", command=self.choose_output).pack(side="left")
        ttk.Button(button_row, text="Przywróć domyślne", command=self.reset_defaults).pack(side="left", padx=(8, 0))
        ttk.Button(button_row, text="Generuj ikonę", command=self.generate_icon).pack(side="right")

        preview_frame = ttk.LabelFrame(frame, text="Podgląd", padding=12)
        preview_frame.grid(row=6, column=0, columnspan=3, sticky="ew")
        self.preview_label = ttk.Label(preview_frame)
        self.preview_label.pack()

        ttk.Label(frame, textvariable=self.status_var, foreground="#666666").grid(row=7, column=0, columnspan=3, sticky="w", pady=(10, 0))

        frame.columnconfigure(1, weight=1)

    def _bind_events(self):
        self.text_var.trace_add("write", self._on_text_change)
        self.font_size_var.trace_add("write", self._on_preview_change)
        self.bg_color_var.trace_add("write", self._on_preview_change)

    def _on_text_change(self, *_args):
        self._sync_output_name()
        self.update_preview()

    def _on_preview_change(self, *_args):
        self.update_preview()

    def _sync_output_name(self):
        text = (self.text_var.get() or "icon").strip().lower()
        slug = re.sub(r"[^a-z0-9]+", "_", text).strip("_") or "icon"
        current_path = Path(self.output_path_var.get())
        if not self.output_path_var.get() or current_path.parent == self.script_dir:
            self.output_path_var.set(str(self.script_dir / f"rm_{slug}_icon.ico"))

    def choose_font(self):
        font_path = filedialog.askopenfilename(
            title="Wybierz czcionkę",
            initialdir=str(Path(self.default_font_path).parent) if self.default_font_path and os.path.isabs(self.default_font_path) else str(self.script_dir),
            filetypes=[("Fonty", "*.ttf *.otf"), ("Wszystkie pliki", "*.*")],
        )
        if not font_path:
            return

        self.selected_font_path = font_path
        self.font_label_var.set(self._font_label_text())
        self.update_preview()

    def choose_color(self):
        selected = colorchooser.askcolor(color=self.bg_color_var.get(), title="Wybierz kolor tła")
        if selected and selected[1]:
            self.bg_color_var.set(selected[1])

    def choose_output(self):
        output_path = filedialog.asksaveasfilename(
            title="Zapisz ikonę jako",
            initialdir=str(self.script_dir),
            initialfile=Path(self.output_path_var.get()).name,
            defaultextension=".ico",
            filetypes=[("Ikona Windows", "*.ico")],
        )
        if output_path:
            self.output_path_var.set(output_path)

    def reset_defaults(self):
        self.text_var.set("IMP")
        self.font_size_var.set("148")
        self.bg_color_var.set(DEFAULT_BG_COLOR)
        self.selected_font_path = self.default_font_path
        self.font_label_var.set(self._font_label_text())
        self.output_path_var.set(str(self.script_dir / "rm_imp_icon.ico"))
        self.status_var.set("Przywrócono ustawienia domyślne")
        self.update_preview()

    def _parse_font_size(self):
        try:
            font_size = int(self.font_size_var.get())
        except ValueError:
            raise ValueError("Wysokość czcionki musi być liczbą całkowitą.")

        if not 8 <= font_size <= 240:
            raise ValueError("Wysokość czcionki musi być w zakresie 8-240 px.")
        return font_size

    def _validate_bg_color(self):
        color = self.bg_color_var.get().strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("Kolor tła musi mieć format #RRGGBB.")
        return color

    def update_preview(self):
        try:
            img = render_icon_image(
                text=self.text_var.get(),
                font_size=self._parse_font_size(),
                bg_color=self._validate_bg_color(),
                font_path=self.selected_font_path,
            )
        except Exception as exc:
            self.status_var.set(str(exc))
            return

        preview_image = img.resize((128, 128), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(preview_image)
        self.preview_label.configure(image=self.preview_photo)
        self.status_var.set("Podgląd zaktualizowany")

    def generate_icon(self):
        try:
            font_size = self._parse_font_size()
            bg_color = self._validate_bg_color()
            text = (self.text_var.get() or "").strip()
            output_path = self.output_path_var.get().strip()

            if not text:
                raise ValueError("Wpisz tekst ikony.")
            if not output_path:
                raise ValueError("Podaj plik wynikowy .ico.")

            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            ico_path, png_path = create_icon(
                text=text,
                output_path=str(output),
                font_size=font_size,
                bg_color=bg_color,
                font_path=self.selected_font_path,
            )
        except Exception as exc:
            messagebox.showerror("Błąd", str(exc))
            self.status_var.set(f"Błąd: {exc}")
            return

        messagebox.showinfo("Gotowe", f"Zapisano:\n{ico_path}\n{png_path}")
        self.status_var.set(f"Zapisano {Path(ico_path).name} i {Path(png_path).name}")
        self.update_preview()


def main():
    root = tk.Tk()
    IconGeneratorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
