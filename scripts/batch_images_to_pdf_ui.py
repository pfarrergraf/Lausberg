from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from PIL import Image, ImageOps
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}

WM_DROPFILES = 0x0233
GWL_WNDPROC = -4
LONG_PTR = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
WNDPROC = ctypes.WINFUNCTYPE(LONG_PTR, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

shell32 = ctypes.windll.shell32
user32 = ctypes.windll.user32


@dataclass(slots=True)
class ImageEntry:
    path: Path
    name: str
    size: int
    created_at: float
    modified_at: float
    added_index: int


def supported_files_from_paths(paths: list[Path]) -> tuple[list[Path], list[Path]]:
    supported: list[Path] = []
    rejected: list[Path] = []

    for raw_path in paths:
        path = raw_path.expanduser()
        if not path.exists():
            rejected.append(path)
            continue
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    if child.suffix.lower() in SUPPORTED_EXTENSIONS:
                        supported.append(child)
                    else:
                        rejected.append(child)
            continue
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            supported.append(path)
        else:
            rejected.append(path)

    unique: list[Path] = []
    seen: set[str] = set()
    for path in supported:
        key = str(path.resolve()).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique, rejected


def format_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024
    return f"{size} B"


def format_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")


def build_image_entry(path: Path, added_index: int) -> ImageEntry:
    stat = path.stat()
    return ImageEntry(
        path=path,
        name=path.name,
        size=stat.st_size,
        created_at=stat.st_ctime,
        modified_at=stat.st_mtime,
        added_index=added_index,
    )


def prepare_pdf_image(path: Path) -> Image.Image:
    with Image.open(path) as image:
        image.load()
        normalized = ImageOps.exif_transpose(image)
        if normalized.mode in {"RGBA", "LA"}:
            background = Image.new("RGB", normalized.size, "white")
            alpha = normalized.getchannel("A")
            background.paste(normalized.convert("RGB"), mask=alpha)
            return background
        if normalized.mode == "P":
            return normalized.convert("RGB")
        if normalized.mode != "RGB":
            return normalized.convert("RGB")
        return normalized.copy()


def convert_images_to_pdf(image_paths: list[Path], output_path: Path) -> Path:
    if not image_paths:
        raise ValueError("No image files were provided.")

    pages = [prepare_pdf_image(path) for path in image_paths]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    first, rest = pages[0], pages[1:]
    try:
        first.save(output_path, "PDF", save_all=True, append_images=rest, resolution=100.0)
    finally:
        for image in pages:
            image.close()
    return output_path


class WindowsDropHandler:
    def __init__(self, widget: tk.Misc, on_drop: Callable[[list[Path]], None]) -> None:
        self.widget = widget
        self.on_drop = on_drop
        self.hwnd = wintypes.HWND(widget.winfo_id())
        self._original_wndproc: int | None = None
        self._new_wndproc = WNDPROC(self._wndproc)
        self._install()

    def _install(self) -> None:
        shell32.DragAcceptFiles(self.hwnd, True)
        setter = user32.SetWindowLongPtrW if hasattr(user32, "SetWindowLongPtrW") else user32.SetWindowLongW
        setter.restype = LONG_PTR
        setter.argtypes = [wintypes.HWND, ctypes.c_int, LONG_PTR]
        self._original_wndproc = setter(self.hwnd, GWL_WNDPROC, LONG_PTR(ctypes.cast(self._new_wndproc, ctypes.c_void_p).value))
        self.widget.bind("<Destroy>", self._on_destroy, add="+")

    def _on_destroy(self, _event: tk.Event[tk.Misc]) -> None:
        if self._original_wndproc is None:
            return
        setter = user32.SetWindowLongPtrW if hasattr(user32, "SetWindowLongPtrW") else user32.SetWindowLongW
        setter.restype = LONG_PTR
        setter.argtypes = [wintypes.HWND, ctypes.c_int, LONG_PTR]
        setter(self.hwnd, GWL_WNDPROC, LONG_PTR(self._original_wndproc))
        self._original_wndproc = None

    def _wndproc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == WM_DROPFILES:
            dropped = wintypes.HANDLE(wparam)
            count = shell32.DragQueryFileW(dropped, 0xFFFFFFFF, None, 0)
            paths: list[Path] = []
            for index in range(count):
                length = shell32.DragQueryFileW(dropped, index, None, 0)
                buffer = ctypes.create_unicode_buffer(length + 1)
                shell32.DragQueryFileW(dropped, index, buffer, length + 1)
                paths.append(Path(buffer.value))
            shell32.DragFinish(dropped)
            self.on_drop(paths)
            return 0
        return self._call_original(hwnd, msg, wparam, lparam)

    def _call_original(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        call_proc = user32.CallWindowProcW
        call_proc.restype = LONG_PTR
        call_proc.argtypes = [LONG_PTR, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        if self._original_wndproc is None:
            return call_proc(0, hwnd, msg, wparam, lparam)
        return call_proc(LONG_PTR(self._original_wndproc), hwnd, msg, wparam, lparam)


class BatchImagesToPdfApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Batch Images to PDF")
        self.root.geometry("1220x760")
        self.root.minsize(980, 620)

        self.entries: list[ImageEntry] = []
        self.next_added_index = 1

        self.sort_by_var = tk.StringVar(value="added")
        self.sort_dir_var = tk.StringVar(value="asc")
        self.status_var = tk.StringVar(value="Drop image files here or use Add Files.")

        self._configure_styles()
        self._build_layout()
        self.drop_handler = WindowsDropHandler(self.root, self.handle_drop)

    def _reindex_entries(self) -> None:
        for index, entry in enumerate(self.entries, start=1):
            entry.added_index = index
        self.next_added_index = len(self.entries) + 1

    def _configure_styles(self) -> None:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Drop.TFrame", background="#f5f7fb")
        style.configure("Drop.TLabel", background="#f5f7fb", foreground="#1f2a44")

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        header = ttk.Frame(self.root, padding=16)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(
            header,
            text="Batch image merge to a single PDF",
            font=("Segoe UI", 16, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Drag files or folders into the window, review the order, then export one PDF.",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.drop_frame = ttk.Frame(self.root, padding=16, style="Drop.TFrame")
        self.drop_frame.grid(row=1, column=0, sticky="ew", padx=16)
        self.drop_frame.columnconfigure(0, weight=1)

        ttk.Label(
            self.drop_frame,
            text="Drop JPG, PNG, TIFF, BMP, or WEBP files here",
            style="Drop.TLabel",
            font=("Segoe UI", 13, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            self.drop_frame,
            text="Folders are scanned recursively. Unsupported files are ignored and reported in the status line.",
            style="Drop.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        controls = ttk.Frame(self.root, padding=(16, 14))
        controls.grid(row=2, column=0, sticky="nsew")
        controls.columnconfigure(0, weight=1)
        controls.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(controls)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        toolbar.columnconfigure(9, weight=1)

        ttk.Button(toolbar, text="Add Files", command=self.add_files).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(toolbar, text="Add Folder", command=self.add_folder).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(toolbar, text="Remove Selected", command=self.remove_selected).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(toolbar, text="Move Up", command=lambda: self.move_selected(-1)).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(toolbar, text="Move Down", command=lambda: self.move_selected(1)).grid(row=0, column=4, padx=(0, 12))

        ttk.Label(toolbar, text="Sort by").grid(row=0, column=5, padx=(0, 6))
        sort_box = ttk.Combobox(
            toolbar,
            textvariable=self.sort_by_var,
            values=("added", "name", "created", "modified", "size", "type"),
            state="readonly",
            width=12,
        )
        sort_box.grid(row=0, column=6, padx=(0, 8))
        sort_box.bind("<<ComboboxSelected>>", lambda _event: self.apply_sort())

        direction_box = ttk.Combobox(
            toolbar,
            textvariable=self.sort_dir_var,
            values=("asc", "desc"),
            state="readonly",
            width=8,
        )
        direction_box.grid(row=0, column=7, padx=(0, 8))
        direction_box.bind("<<ComboboxSelected>>", lambda _event: self.apply_sort())

        ttk.Button(toolbar, text="Clear List", command=self.clear_entries).grid(row=0, column=8, padx=(0, 8))
        ttk.Button(toolbar, text="Create PDF", command=self.export_pdf).grid(row=0, column=10)

        columns = ("order", "name", "type", "size", "created", "modified", "path")
        self.tree = ttk.Treeview(controls, columns=columns, show="headings", selectmode="extended")
        self.tree.grid(row=1, column=0, sticky="nsew")

        headings = {
            "order": ("#", 55),
            "name": ("Name", 230),
            "type": ("Type", 70),
            "size": ("Size", 90),
            "created": ("Created", 155),
            "modified": ("Modified", 155),
            "path": ("Path", 430),
        }
        for key, (label, width) in headings.items():
            self.tree.heading(key, text=label)
            anchor = "e" if key in {"order", "size"} else "w"
            self.tree.column(key, width=width, anchor=anchor)

        scrollbar = ttk.Scrollbar(controls, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        status = ttk.Label(self.root, textvariable=self.status_var, padding=(16, 0, 16, 16))
        status.grid(row=3, column=0, sticky="ew")

    def add_files(self) -> None:
        selected = filedialog.askopenfilenames(
            title="Select image files",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp"),
                ("All files", "*.*"),
            ],
        )
        if selected:
            self.add_paths([Path(item) for item in selected])

    def add_folder(self) -> None:
        selected = filedialog.askdirectory(title="Select a folder with images")
        if selected:
            self.add_paths([Path(selected)])

    def handle_drop(self, paths: list[Path]) -> None:
        self.add_paths(paths)

    def add_paths(self, paths: list[Path]) -> None:
        supported, rejected = supported_files_from_paths(paths)
        added = 0
        existing = {str(entry.path.resolve()).lower() for entry in self.entries}
        for path in supported:
            key = str(path.resolve()).lower()
            if key in existing:
                continue
            self.entries.append(build_image_entry(path, self.next_added_index))
            self.next_added_index += 1
            existing.add(key)
            added += 1

        self._reindex_entries()
        self.refresh_tree()

        message = f"Added {added} file(s)."
        if rejected:
            message += f" Ignored {len(rejected)} unsupported or missing item(s)."
        if not self.entries:
            message = "No supported image files are loaded."
        self.status_var.set(message)

    def clear_entries(self) -> None:
        self.entries.clear()
        self.refresh_tree()
        self.status_var.set("List cleared.")

    def remove_selected(self) -> None:
        selected = {item for item in self.tree.selection()}
        if not selected:
            self.status_var.set("Select one or more rows to remove.")
            return
        self.entries = [entry for index, entry in enumerate(self.entries) if str(index) not in selected]
        self._reindex_entries()
        self.refresh_tree()
        self.status_var.set(f"Removed {len(selected)} file(s).")

    def move_selected(self, offset: int) -> None:
        selected_indexes = sorted(int(item) for item in self.tree.selection())
        if not selected_indexes:
            self.status_var.set("Select one or more rows to move.")
            return
        if self.sort_by_var.get() != "added":
            self.status_var.set("Manual move works on the current displayed order. Switch sort to 'added' if needed.")
        if offset < 0:
            for index in selected_indexes:
                if index == 0:
                    continue
                self.entries[index - 1], self.entries[index] = self.entries[index], self.entries[index - 1]
        else:
            for index in reversed(selected_indexes):
                if index >= len(self.entries) - 1:
                    continue
                self.entries[index + 1], self.entries[index] = self.entries[index], self.entries[index + 1]
        self._reindex_entries()
        self.refresh_tree(selection=[max(0, min(len(self.entries) - 1, index + offset)) for index in selected_indexes])

    def apply_sort(self) -> None:
        sort_by = self.sort_by_var.get()
        reverse = self.sort_dir_var.get() == "desc"

        key_map = {
            "added": lambda item: item.added_index,
            "name": lambda item: item.name.lower(),
            "created": lambda item: item.created_at,
            "modified": lambda item: item.modified_at,
            "size": lambda item: item.size,
            "type": lambda item: item.path.suffix.lower(),
        }
        self.entries.sort(key=key_map[sort_by], reverse=reverse)
        self.refresh_tree()
        self.status_var.set(f"Sorted by {sort_by} ({self.sort_dir_var.get()}).")

    def refresh_tree(self, selection: list[int] | None = None) -> None:
        self.tree.delete(*self.tree.get_children())
        for index, entry in enumerate(self.entries):
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    index + 1,
                    entry.name,
                    entry.path.suffix.lower().lstrip("."),
                    format_size(entry.size),
                    format_timestamp(entry.created_at),
                    format_timestamp(entry.modified_at),
                    str(entry.path),
                ),
            )
        if selection:
            valid = [str(index) for index in selection if 0 <= index < len(self.entries)]
            self.tree.selection_set(valid)

    def export_pdf(self) -> None:
        if not self.entries:
            messagebox.showwarning("No images", "Add at least one supported image file before exporting.")
            return

        output = filedialog.asksaveasfilename(
            title="Save merged PDF",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile="merged_images.pdf",
        )
        if not output:
            return

        image_paths = [entry.path for entry in self.entries]
        try:
            pdf_path = convert_images_to_pdf(image_paths, Path(output))
        except Exception as exc:
            messagebox.showerror("Export failed", f"Could not create the PDF.\n\n{exc}")
            self.status_var.set(f"PDF export failed: {exc}")
            return

        self.status_var.set(f"Created PDF: {pdf_path}")
        messagebox.showinfo("PDF created", f"Created:\n{pdf_path}")


def launch_ui() -> None:
    root = tk.Tk()
    BatchImagesToPdfApp(root)
    root.mainloop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge multiple image files into a single PDF with a Windows drag-and-drop UI."
    )
    parser.add_argument("inputs", nargs="*", type=Path, help="Optional image files or folders for CLI mode")
    parser.add_argument("--output", type=Path, default=None, help="PDF path for CLI mode")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.inputs and args.output is not None:
        supported, rejected = supported_files_from_paths(args.inputs)
        if rejected:
            print(f"Ignored {len(rejected)} unsupported or missing item(s).")
        if not supported:
            print("No supported image files were found.")
            return 2
        convert_images_to_pdf(supported, args.output)
        print(f"Created PDF: {args.output}")
        return 0

    launch_ui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
