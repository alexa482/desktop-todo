import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageOps, ImageTk
except ImportError as error:
    PILLOW_IMPORT_ERROR = str(error)
    Image = ImageDraw = ImageEnhance = ImageOps = ImageTk = None

def resource_path(*parts):
    """Resolve read-only resources in source runs and PyInstaller bundles."""
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    return base.joinpath(*parts)


def task_data_path():
    if getattr(sys, 'frozen', False):
        return Path.home() / 'Library' / 'Application Support' / 'My To Do List' / 'tasks.json'
    return Path(__file__).resolve().with_name('tasks.json')


def initialize_user_data(path):
    """Copy the build-time task snapshot once; never overwrite user data."""
    if not getattr(sys, 'frozen', False):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    seed = resource_path('seed', 'tasks.json')
    if seed.exists():
        original = seed.read_bytes()
        normalize_data(json.loads(original.decode('utf-8')))  # Validate before copying.
        try:
            with path.open('xb') as file:
                file.write(original)
        except FileExistsError:
            pass


# Visual and timing settings (milliseconds unless otherwise noted).
BACKGROUNDS_DIR = resource_path("assets", "backgrounds")
BACKGROUND_DURATION_MS = 240_000
BACKGROUND_FADE_MS = 900
BACKGROUND_FADE_STEPS = 12
BACKGROUND_DIMMING = 0.22  # 0 = original brightness, 1 = black
QUOTE_DURATION_MS = 240_000
QUOTE_FADE_MS = 800  # duration of EACH fade out / fade in
QUOTE_FADE_STEPS = 24
RESIZE_DEBOUNCE_MS = 180
FALLBACK_BACKGROUND = "#777e73"
PANEL_OPACITY = 0.65  # 0 = clear, 1 = solid black
PANEL_CORNER_RADIUS = 24
PANEL_COLOR = "#000000"
PANEL_BORDER_COLOR = "#666a70"
TEXT_COLOR = "#f4f2ec"
MUTED_TEXT_COLOR = "#afb5bb"
QUOTE_COLOR = "#e5e0d6"
WIDGET_COLOR = "#202429"  # Native interactive widgets remain honestly opaque.
BORDER_COLOR = "#41474d"
CONTROL_COLOR = "#30363d"
ENTRY_COLOR = "#252a30"
SELECTION_COLOR = "#48586a"

TASKS_FILE = task_data_path()


# Built-in macOS font families. Change these two lines to experiment.
PRIMARY_FONT = "Avenir Next"
DISPLAY_FONT = "Baskerville"
APP_TITLE_FONT = (DISPLAY_FONT, 26, "bold")
QUOTE_FONT = (DISPLAY_FONT, 17, "italic")
SECTION_TITLE_FONT = (PRIMARY_FONT, 12, "bold")
SECTION_FONT = (PRIMARY_FONT, 13)
TASK_FONT = (PRIMARY_FONT, 14)
SUBTASK_FONT = (PRIMARY_FONT, 13)
SMALL_FONT = (PRIMARY_FONT, 12)
FONTS = {
    "app_title": APP_TITLE_FONT,
    "motivational_quote": QUOTE_FONT,
    "section_headings": SECTION_TITLE_FONT,
    "section_text": SECTION_FONT,
    "task_text": TASK_FONT,
    "small_sidebar": SMALL_FONT,
}

def configure_typography(root):
    style = ttk.Style(root)
    for target, base, role in (
        ("AppTitle.TLabel", "TLabel", "app_title"),
        ("Quote.TLabel", "TLabel", "motivational_quote"),
        ("SectionHeading.TLabel", "TLabel", "section_headings"),
        ("Tasks.Treeview", "Treeview", "task_text"),
        ("Task.TEntry", "TEntry", "task_text"),
        ("Section.Task.TEntry", "Task.TEntry", "section_text"),
        ("Sidebar.Treeview", "Treeview", "section_text"),
        ("Small.TButton", "TButton", "small_sidebar"),
    ):
        font = FONTS[role]
        if font is None:
            font = style.lookup(base, "font")
        style.configure(target, font=font)
    style.configure("Tasks.Treeview", rowheight=30)


MAX_DEPTH = 3
MESSAGES = (
    "Get the hardest thing done first!",
    "When you can't imagine life any other way, then you know you have a life worth living.",
    "It's a good day to have a day!",
    "Who cares? You're thriving.",
    "If we wait until we're ready, we'll be waiting the rest of our lives.",
    "Less thinking, more doing.",
)


def mix_color(start, end, amount):
    channels = [round(int(start[i:i + 2], 16) * (1 - amount)
                      + int(end[i:i + 2], 16) * amount) for i in (1, 3, 5)]
    return '#' + ''.join(f'{channel:02x}' for channel in channels)


def discover_photos(folder):
    try:
        return sorted(path for path in folder.iterdir()
                      if path.is_file() and path.suffix.lower() in {'.jpg', '.jpeg', '.png'})
    except OSError:
        return []


def validate_backgrounds(folder):
    print(f"[background] Directory: {folder.resolve()}", flush=True)
    print(f"[background] Python: {sys.executable}", flush=True)
    paths = discover_photos(folder)
    for path in paths:
        print(f"[background] Discovered: {path.name}", flush=True)
    print(f"[background] Supported files discovered: {len(paths)}", flush=True)
    if Image is None:
        print(f"[background] Pillow unavailable: {PILLOW_IMPORT_ERROR}. "
              f"Install with: {sys.executable} -m pip install Pillow", flush=True)
        print("[background] Valid background images: 0 (Pillow unavailable)", flush=True)
        return []
    valid = []
    for path in paths:
        try:
            with Image.open(path) as photo:
                photo.load()  # Decode pixels, not just the file header.
            valid.append(path)
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            print(f"[background] Skipping {path.name}: {error}", flush=True)
    print(f"[background] Valid background images: {len(valid)}", flush=True)
    return valid


def prepare_photo(path, size):
    # This runs in a worker; Tk objects are created only on the UI thread.
    with Image.open(path) as original:
        photo = ImageOps.exif_transpose(original).convert('RGB')
        photo = ImageOps.fit(photo, size, method=Image.Resampling.LANCZOS)
        return ImageEnhance.Brightness(photo).enhance(1 - BACKGROUND_DIMMING)


def find_photo(paths, size):
    for path in paths:
        try:
            return path, prepare_photo(path, size)
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            print(f"[background] Could not load {path.name}: {error}", flush=True)
            continue
    return None, None


def panel_bounds(size):
    width, height = size
    return ((24, 28, 274, height - 28), (290, 28, width - 24, height - 28))


def compose_panels(photo):
    overlay = Image.new('RGBA', photo.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rgb = tuple(int(PANEL_COLOR[i:i+2], 16) for i in (1, 3, 5))
    border = tuple(int(PANEL_BORDER_COLOR[i:i+2], 16) for i in (1, 3, 5))
    for bounds in panel_bounds(photo.size):
        draw.rounded_rectangle(bounds, radius=PANEL_CORNER_RADIUS,
                               fill=(*rgb, round(255 * PANEL_OPACITY)),
                               outline=(*border, 110), width=1)
    return Image.alpha_composite(photo.convert('RGBA'), overlay).convert('RGB')


class CanvasText:
    """Canvas text shows the composed photograph without a rectangular label."""
    def __init__(self, canvas, text='', font=None, foreground=TEXT_COLOR):
        self.canvas = canvas
        self.item = canvas.create_text(0, 0, text=text, font=font, fill=foreground,
                                       anchor='nw', justify='left')

    def configure(self, **options):
        if 'foreground' in options:
            options['fill'] = options.pop('foreground')
        self.canvas.itemconfigure(self.item, **options)

    def place(self, x, y, width):
        self.canvas.coords(self.item, x, y)
        self.canvas.itemconfigure(self.item, width=width)


class PhotoBackground:
    def __init__(self, root):
        self.root = root
        self.label = tk.Canvas(root, background=FALLBACK_BACKGROUND, borderwidth=0, highlightthickness=0)
        self.image_item = self.label.create_image(0, 0, anchor="nw")
        self.label.place(x=0, y=0, relwidth=1, relheight=1)
        self.label.tk.call("lower", self.label._w)
        self.executor = ThreadPoolExecutor(max_workers=1) if Image else None
        self.closed = False
        self.current_path = None
        self.current_image = None
        self.photo = None
        self.future = None
        self.pending = False
        self.timers = {}
        self.size = (900, 650)
        root.bind('<Configure>', self.resize, add='+')
        # Decode and display the first photo before the window is shown.
        paths = validate_backgrounds(BACKGROUNDS_DIR)
        if paths:
            self.current_path, self.current_image = find_photo(paths, self.size)
            if self.current_image is not None:
                self.display(self.current_image)
        if self.current_image is None and Image:
            self.display(Image.new('RGB', self.size, FALLBACK_BACKGROUND))
        self.schedule('rotate', BACKGROUND_DURATION_MS, self.request)

    def schedule(self, key, delay, callback):
        previous = self.timers.pop(key, None)
        if previous is not None:
            self.root.after_cancel(previous)
        def run():
            self.timers.pop(key, None)
            if not self.closed:
                callback()
        self.timers[key] = self.root.after(delay, run)

    def resize(self, event):
        if event.widget is self.root:
            # A withdrawn macOS window can report a transient 1x1 Configure.
            # Measure the actual window after layout instead of trusting that event.
            self.schedule('resize', RESIZE_DEBOUNCE_MS, self.resize_to_window)

    def resize_to_window(self):
        size = (self.root.winfo_width(), self.root.winfo_height())
        if min(size) <= 1 or size == self.size:
            return
        self.size = size
        self.request(resize=True)

    def request(self, resize=False):
        if self.closed or self.executor is None:
            return
        if self.future is not None:
            self.pending = True
            return
        paths = discover_photos(BACKGROUNDS_DIR)
        if self.current_path in paths:
            index = paths.index(self.current_path) + (0 if resize else 1)
            paths = paths[index:] + paths[:index]
        self.request_size = self.size
        self.future = self.executor.submit(find_photo, paths, self.size)
        self.schedule('poll', 40, self.poll)

    def poll(self):
        if not self.future.done():
            self.schedule('poll', 40, self.poll)
            return
        try:
            path, image = self.future.result()
        except Exception as error:
            print(f"[background] Rendering failed: {error}", flush=True)
            path, image = None, None
        self.future = None
        if self.pending or self.request_size != self.size:
            self.pending = False
            self.request(resize=True)
            return
        old = self.current_image
        changed = path != self.current_path
        self.current_path = path
        self.current_image = image
        if image is None:
            self.display(Image.new('RGB', self.size, FALLBACK_BACKGROUND))
        elif changed and old is not None and old.size == image.size:
            self.fade(old, image, 0)
        else:
            self.display(image)
        if changed or 'rotate' not in self.timers:
            self.schedule('rotate', BACKGROUND_DURATION_MS, self.request)

    def display(self, image):
        self.photo = ImageTk.PhotoImage(compose_panels(image), master=self.root)
        self.label.itemconfigure(self.image_item, image=self.photo)
        self.label.tag_lower(self.image_item)
        self.label.image = self.photo  # Retain a Tk image reference on both owners.
        self.label.tk.call("lower", self.label._w)  # Keep it behind the sidebar and task panels.

    def fade(self, old, new, step):
        # A few bounded frames keep this gentle without preallocating an animation.
        if new is not self.current_image:
            return
        self.display(Image.blend(old, new, step / BACKGROUND_FADE_STEPS))
        if step < BACKGROUND_FADE_STEPS:
            self.schedule('fade', BACKGROUND_FADE_MS // BACKGROUND_FADE_STEPS,
                          lambda: self.fade(old, new, step + 1))

    def close(self):
        self.closed = True
        for timer in self.timers.values():
            self.root.after_cancel(timer)
        self.timers.clear()
        if self.executor:
            self.executor.shutdown(wait=False, cancel_futures=True)


def configure_palette(root):
    style = ttk.Style(root)
    # Clam honors panel and control colors consistently across platforms.
    style.theme_use('clam')
    style.configure('Panel.TFrame', background=WIDGET_COLOR, bordercolor=BORDER_COLOR,
                    relief='solid', borderwidth=1)
    style.configure('Inner.TFrame', background=WIDGET_COLOR)
    for name in ('AppTitle.TLabel', 'Quote.TLabel', 'SectionHeading.TLabel'):
        style.configure(name, background=WIDGET_COLOR, foreground=TEXT_COLOR)
    style.configure('Quote.TLabel', foreground=QUOTE_COLOR)
    style.configure('TScrollbar', background=CONTROL_COLOR, troughcolor=WIDGET_COLOR,
                    bordercolor=BORDER_COLOR, arrowcolor=MUTED_TEXT_COLOR)
    for name in ('Tasks.Treeview', 'Sidebar.Treeview'):
        style.configure(name, background=WIDGET_COLOR, fieldbackground=WIDGET_COLOR,
                        foreground=TEXT_COLOR, borderwidth=0, rowheight=30)
        style.map(name, background=[('selected', SELECTION_COLOR)],
                  foreground=[('selected', TEXT_COLOR)])
    style.configure('Small.TButton', background=CONTROL_COLOR, foreground=TEXT_COLOR,
                    padding=(10, 7), bordercolor=BORDER_COLOR)
    style.map('Small.TButton', background=[('active', SELECTION_COLOR)],
              foreground=[('disabled', MUTED_TEXT_COLOR)])
    style.configure('Task.TEntry', fieldbackground=ENTRY_COLOR, foreground=TEXT_COLOR,
                    insertcolor=TEXT_COLOR, padding=7, bordercolor=BORDER_COLOR)


def new_task(text):
    return {"text": text, "completed": False, "subtasks": []}


def normalize_data(data):
    """Validate saved data and migrate both previous string-based formats."""
    if isinstance(data, list):
        data = {"sections": {"General": data}}
    if not isinstance(data, dict) or data.get("version", 1) not in (1, 2, 3):
        raise ValueError("Unsupported task file format.")
    sections = data.get("sections")
    if not isinstance(sections, dict) or not sections:
        raise ValueError("The task file must contain at least one section.")

    def normalize_task(task, depth):
        if isinstance(task, str):
            completed = task.startswith("✓ ")
            result = new_task(task[2:] if completed else task)
            result["completed"] = completed
            return result
        if not isinstance(task, dict) or not isinstance(task.get("text"), str):
            raise ValueError("Each task must have text.")
        if not isinstance(task.get("completed"), bool):
            raise ValueError("Each task must have a boolean completion state.")
        result = {"text": task["text"], "completed": task["completed"]}
        children = task.get("subtasks", [])
        if not isinstance(children, list):
            raise ValueError("Subtasks must be a list.")
        if depth >= MAX_DEPTH and children:
            raise ValueError("Tasks cannot be nested beyond three levels.")
        result["subtasks"] = [normalize_task(child, depth + 1) for child in children]
        return result

    result = {}
    for name, tasks in sections.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(tasks, list):
            raise ValueError("Invalid section name or task list.")
        result[name] = [normalize_task(task, 1) for task in tasks]
    selected = data.get("selected_section")
    if not isinstance(selected, str) or selected not in result:
        selected = next(iter(result))
    # Older files have no explicit order: preserve their existing visible order
    # once, then use the saved list for all future display and reordering.
    saved_order = data.get('section_order', [])
    order = []
    if isinstance(saved_order, list):
        for name in saved_order:
            if isinstance(name, str) and name in result and name not in order:
                order.append(name)
    order.extend(name for name in result if name not in order)
    return {"version": 3, "sections": result, "selected_section": selected,
            "section_order": order}


def write_data(path, data):
    temporary_file = path.with_suffix(path.suffix + ".tmp")
    with temporary_file.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary_file.replace(path)


def load_data(path):
    if not path.exists():
        data = normalize_data({"sections": {"General": []}})
        write_data(path, data)
        return data
    original = path.read_bytes()
    raw = json.loads(original.decode("utf-8")) if original.strip() else []
    data = normalize_data(raw)
    if data != raw:
        # Exclusive creation preserves any earlier backup on subsequent runs.
        backup = path.with_suffix(path.suffix + ".bak")
        if backup.exists():
            backup = path.with_suffix(path.suffix + ".pre-v3.bak")
        try:
            with backup.open("xb") as file:
                file.write(original)
        except FileExistsError:
            pass
        write_data(path, data)
    return data


class TaskModel:
    def __init__(self, data):
        self.data = data

    @property
    def tasks(self):
        return self.data["sections"][self.data["selected_section"]]

    def add_section(self, name):
        name = name.strip()
        if not name:
            raise ValueError("Please enter a section name.")
        if name.casefold() in (existing.casefold() for existing in self.data["sections"]):
            raise ValueError("That section already exists.")
        self.data["sections"][name] = []
        self.data['section_order'].append(name)
        self.data["selected_section"] = name

    def reorder_sections(self, order):
        if len(order) != len(self.data['sections']) or set(order) != set(self.data['sections']):
            raise ValueError('Section order must contain every section exactly once.')
        self.data['section_order'] = list(order)

    def rename_section(self, old_name, new_name):
        new_name = new_name.strip()
        if not new_name:
            raise ValueError('Please enter a section name.')
        sections = self.data['sections']
        if old_name not in sections:
            raise ValueError('That section no longer exists.')
        if any(name != old_name and name.casefold() == new_name.casefold() for name in sections):
            raise ValueError('That section already exists.')
        if new_name == old_name:
            return False
        # Preserve the task objects and update every stored name reference together.
        self.data['sections'] = {
            new_name if name == old_name else name: tasks for name, tasks in sections.items()
        }
        self.data['section_order'] = [
            new_name if name == old_name else name for name in self.data['section_order']
        ]
        if self.data['selected_section'] == old_name:
            self.data['selected_section'] = new_name
        return True

    def add_task(self, text, parent=None):
        text = text.strip()
        if not text:
            return None
        if parent is None:
            self.tasks.append(new_task(text))
            return (len(self.tasks) - 1,)
        if len(parent) >= MAX_DEPTH:
            raise ValueError("Tasks cannot be nested beyond three levels.")
        children = self.item(parent)["subtasks"]
        children.append(new_task(text))
        return (*parent, len(children) - 1)

    def item(self, location):
        if not 1 <= len(location) <= MAX_DEPTH:
            raise ValueError("Invalid task location.")
        children = self.tasks
        for index in location:
            task = children[index]
            children = task["subtasks"]
        return task

    def complete(self, location):
        self.item(location)["completed"] = True

    def toggle(self, location):
        task = self.item(location)
        task["completed"] = not task["completed"]

    def delete(self, location):
        children = self.tasks if len(location) == 1 else self.item(location[:-1])["subtasks"]
        del children[location[-1]]

    def incomplete_count(self, section):
        return sum(not task["completed"] for task in self.data["sections"][section])


def task_label(task):
    return ("✓ " if task["completed"] else "• ") + task["text"]


def task_row_layout(quote_bottom, panel_bottom):
    """Fixed content rows and gaps; only the task-list row absorbs extra height.

    Keep native controls directly on the root so no opaque container obscures
    the photograph. This provides a weighted-row layout without a visible Frame.
    """
    quote_to_input = 25
    input_to_list = 18
    list_to_actions = 20
    bottom_padding = 22
    input_height = 36
    action_height = 36
    scrollbar_height = 14

    input_top = quote_bottom + quote_to_input
    list_top = input_top + input_height + input_to_list
    actions_top = panel_bottom - bottom_padding - action_height
    list_bottom = actions_top - list_to_actions
    return {
        'input_top': input_top,
        'input_height': input_height,
        'list_top': list_top,
        'list_height': max(1, list_bottom - scrollbar_height - list_top),
        'scrollbar_top': list_bottom - scrollbar_height,
        'scrollbar_height': scrollbar_height,
        'actions_top': actions_top,
        'action_height': action_height,
    }


class TodoApp:
    def __init__(self, root, data):
        self.root = root
        configure_palette(root)
        configure_typography(root)
        root.title("My To Do List")
        root.geometry("900x650")
        root.minsize(820, 620)
        self.background = PhotoBackground(root)
        self.model = TaskModel(data)
        self.locations = {}
        canvas = self.background.label
        self.section_heading = CanvasText(canvas, text="SECTIONS", font=SECTION_TITLE_FONT)
        self.heading = CanvasText(canvas, font=APP_TITLE_FONT)
        self.message_index = 0
        self.message_label = CanvasText(canvas, text=MESSAGES[0], font=QUOTE_FONT,
                                        foreground=QUOTE_COLOR)
        self.section_list = ttk.Treeview(root, columns=("count",), show="tree",
                                         selectmode="browse", style="Sidebar.Treeview")
        self.section_list.column("#0", width=160, minwidth=80)
        self.section_list.column("count", width=36, minwidth=36, stretch=False, anchor="e")
        self.section_scroll = ttk.Scrollbar(root, command=self.section_list.yview)
        self.section_list.configure(yscrollcommand=self.section_scroll.set)
        self.section_list.bind("<<TreeviewSelect>>", self.select_section)
        self.section_drag = None
        self.section_editor = None
        self.section_list.bind('<ButtonPress-1>', self.section_drag_start)
        self.section_list.bind('<B1-Motion>', self.section_drag_motion)
        self.section_list.bind('<ButtonRelease-1>', self.section_drag_end)
        self.section_list.bind('<Double-Button-1>', self.begin_section_rename)
        root.bind('<ButtonPress-1>', self.section_editor_outside_click, add='+')
        self.new_section_button = ttk.Button(root, style="Small.TButton", text="+ New Section", command=self.new_section)
        self.task_entry = ttk.Entry(root, style="Task.TEntry")
        self.add_button = ttk.Button(root, style="Small.TButton", text="Add", command=self.add_task)
        self.task_entry.bind("<Return>", lambda event: self.add_task())
        self.task_tree = ttk.Treeview(root, show="tree", selectmode="browse", style="Tasks.Treeview")
        self.task_tree.column("#0", width=340, minwidth=180)
        self.task_tree.tag_configure('subtask', font=SUBTASK_FONT)
        self.scroll = ttk.Scrollbar(root, command=self.task_tree.yview)
        self.horizontal = ttk.Scrollbar(root, orient="horizontal", command=self.task_tree.xview)
        self.task_tree.configure(yscrollcommand=self.scroll.set, xscrollcommand=self.horizontal.set)
        self.task_tree.bind("<Double-Button-1>", self.double_click)
        self.subtask_button = ttk.Button(root, style="Small.TButton", text="+ Subtask", command=self.add_subtask)
        self.complete_button = ttk.Button(root, style="Small.TButton", text="✓ Complete", command=self.complete_task)
        self.delete_button = ttk.Button(root, style="Small.TButton", text="Delete", command=self.delete_task)
        self.task_tree.bind("<<TreeviewSelect>>", self.update_actions)
        root.bind('<Configure>', self.layout, add='+')
        self.layout()
        self.message_timer = root.after(QUOTE_DURATION_MS, self.rotate_message)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh_sections()
        self.show_section()
        self.task_entry.focus_set()

    def layout(self, event=None):
        if event is not None and event.widget is not self.root:
            return
        width, height = self.root.winfo_width(), self.root.winfo_height()
        if width <= 1 or height <= 1:
            width, height = 900, 650
        sidebar, main = panel_bounds((width, height))
        sx, sy, sr, sb = sidebar
        mx, my, mr, mb = main
        self.section_heading.place(sx + 20, sy + 22, sr - sx - 40)
        self.heading.place(mx + 22, my + 20, mr - mx - 44)
        self.message_label.place(mx + 22, my + 76, mr - mx - 44)
        self.section_list.place(x=sx + 18, y=sy + 65, width=sr-sx-50, height=sb-sy-145)
        self.section_scroll.place(x=sr-32, y=sy+65, width=14, height=sb-sy-145)
        self.new_section_button.place(x=sx+18, y=sb-58, width=sr-sx-36, height=36)
        # Measure wrapped text so short quotes don't reserve several empty lines.
        quote_box = self.message_label.canvas.bbox(self.message_label.item)
        if quote_box is not None:
            self.quote_bottom = quote_box[3]
        quote_bottom = getattr(self, 'quote_bottom', my + 106)
        rows = task_row_layout(quote_bottom, mb)
        self.task_entry.place(x=mx+22, y=rows['input_top'], width=mr-mx-124, height=rows['input_height'])
        self.add_button.place(x=mr-92, y=rows['input_top'], width=70, height=rows['input_height'])
        self.task_tree.place(x=mx+22, y=rows['list_top'], width=mr-mx-58, height=rows['list_height'])
        self.scroll.place(x=mr-36, y=rows['list_top'], width=14, height=rows['list_height'])
        self.horizontal.place(x=mx+22, y=rows['scrollbar_top'], width=mr-mx-58, height=rows['scrollbar_height'])
        for offset, button in enumerate((self.subtask_button, self.complete_button, self.delete_button)):
            button.place(x=mx+22+offset*112, y=rows['actions_top'], width=104, height=rows['action_height'])

    def save_tasks(self):
        try:
            write_data(TASKS_FILE, self.model.data)
        except OSError as error:
            messagebox.showerror("Could not save tasks", str(error), parent=self.root)

    def rotate_message(self):
        self.fade_message(fading_out=True)

    def fade_message(self, fading_out, step=0):
        amount = step / QUOTE_FADE_STEPS
        start, end = (QUOTE_COLOR, PANEL_COLOR) if fading_out else (PANEL_COLOR, QUOTE_COLOR)
        self.message_label.configure(foreground=mix_color(start, end, amount))
        self.message_label.configure(state='hidden' if fading_out and step == QUOTE_FADE_STEPS else 'normal')
        if step < QUOTE_FADE_STEPS:
            self.message_timer = self.root.after(
                max(1, QUOTE_FADE_MS // QUOTE_FADE_STEPS),
                lambda: self.fade_message(fading_out, step + 1))
        elif fading_out:
            self.message_index = (self.message_index + 1) % len(MESSAGES)
            self.message_label.configure(text=MESSAGES[self.message_index])
            self.fade_message(fading_out=False)
            self.layout()  # Reflow spacing for the new quote's wrapped height.
        else:
            self.message_timer = self.root.after(QUOTE_DURATION_MS, self.rotate_message)

    def close(self):
        if getattr(self, 'section_editor', None) is not None:
            self.finish_section_rename()
        self.root.after_cancel(self.message_timer)
        self.background.close()
        self.root.destroy()

    def refresh_sections(self):
        # Update existing rows in place so counts never disturb sidebar selection.
        self.section_names = {}
        for index, name in enumerate(self.model.data['section_order']):
            row = f"section-{index}"
            self.section_names[row] = name
            values = (self.model.incomplete_count(name),)
            if self.section_list.exists(row):
                self.section_list.item(row, text=name, values=values)
            else:
                self.section_list.insert("", "end", iid=row, text=name, values=values)
            self.section_list.move(row, '', index)
            if name == self.model.data["selected_section"]:
                if self.section_list.selection() != (row,):
                    self.section_list.selection_set(row)
                self.section_list.see(row)

    def section_drag_start(self, event):
        if getattr(self, 'section_editor', None) is not None:
            self.finish_section_rename()
        row = self.section_list.identify_row(event.y)
        self.section_drag = {'row': row, 'y': event.y, 'active': False} if row else None
        # Let Treeview's normal click handling select and switch the section.

    def section_drag_motion(self, event):
        if getattr(self, 'section_editor', None) is not None:
            return 'break'
        drag = self.section_drag
        if drag is None:
            return
        if not drag['active'] and abs(event.y - drag['y']) < 5:
            return 'break'
        drag['active'] = True
        tree = self.section_list
        if event.y < 16:
            tree.yview_scroll(-1, 'units')
        elif event.y > tree.winfo_height() - 16:
            tree.yview_scroll(1, 'units')
        target = tree.identify_row(event.y)
        others = [row for row in tree.get_children() if row != drag['row']]
        if target and target != drag['row']:
            box = tree.bbox(target)
            if box:
                index = others.index(target) + (event.y >= box[1] + box[3] / 2)
                tree.move(drag['row'], '', index)
        elif not target and others:
            tree.move(drag['row'], '', 0 if event.y < 16 else len(others))
        # The selected row moves live: this previews the exact drop position.
        return 'break'

    def section_drag_end(self, event):
        drag = self.section_drag
        self.section_drag = None
        if drag and drag['active']:
            order = [self.section_names[row] for row in self.section_list.get_children()]
            if order != self.model.data['section_order']:
                self.model.reorder_sections(order)
                self.save_tasks()
            return 'break'

    def begin_section_rename(self, event):
        self.section_drag = None  # A double-click must never become a drag.
        tree = self.section_list
        row = tree.identify_row(event.y)
        if not row or tree.identify_column(event.x) != '#0':
            return 'break'
        if self.section_editor is not None:
            self.finish_section_rename()
        box = tree.bbox(row, '#0')
        if not box:
            return 'break'
        self.section_edit_name = self.section_names[row]
        editor = ttk.Entry(tree, style='Section.Task.TEntry')
        self.section_editor = editor
        editor.insert(0, self.section_edit_name)
        x, y, width, height = box
        editor.place(x=x, y=y, width=width, height=height)
        editor.selection_range(0, tk.END)
        editor.focus_set()
        editor.bind('<Return>', self.finish_section_rename)
        editor.bind('<Escape>', lambda event: self.finish_section_rename(cancel=True))
        editor.bind('<FocusOut>', self.finish_section_rename)
        return 'break'

    def section_editor_outside_click(self, event):
        editor = self.section_editor
        if editor is not None and event.widget is not editor:
            self.finish_section_rename()

    def finish_section_rename(self, event=None, cancel=False):
        editor = self.section_editor
        if editor is None:
            return 'break'
        name = editor.get()
        self.section_editor = None  # Guard against FocusOut during destruction.
        editor.destroy()
        if not cancel:
            try:
                changed = self.model.rename_section(self.section_edit_name, name)
            except ValueError:
                self.root.bell()  # Invalid edits leave the original data untouched.
            else:
                if changed:
                    self.refresh_sections()
                    self.heading.configure(text=self.model.data['selected_section'])
                    self.save_tasks()
        return 'break'

    def select_section(self, event=None):
        selected = self.section_list.selection()
        if not selected:
            return
        name = self.section_names[selected[0]]
        if name != self.model.data["selected_section"]:
            self.model.data["selected_section"] = name
            self.show_section()
            self.save_tasks()

    def new_section(self):
        name = simpledialog.askstring("New Section", "Section name:", parent=self.root)
        if name is None:
            return
        try:
            self.model.add_section(name)
        except ValueError as error:
            messagebox.showwarning("New Section", str(error), parent=self.root)
            return
        self.refresh_sections()
        self.show_section()
        self.save_tasks()
        self.task_entry.focus_set()

    def show_section(self, selected=None):
        self.heading.configure(text=self.model.data["selected_section"])
        for row in self.task_tree.get_children():
            self.task_tree.delete(row)
        self.locations.clear()
        def insert_tasks(tasks, parent_row="", parent_path=()):
            for index, task in enumerate(tasks):
                location = (*parent_path, index)
                row = self.task_tree.insert(parent_row, "end", text=task_label(task), open=True,
                                            tags=("subtask",) if parent_path else ())
                self.locations[row] = location
                insert_tasks(task["subtasks"], row, location)

        insert_tasks(self.model.tasks)
        self.refresh_sections()
        for row, location in self.locations.items():
            if location == selected:
                self.task_tree.selection_set(row)
                self.task_tree.focus(row)
                self.task_tree.see(row)
                break
        self.update_actions()

    def selected_location(self):
        selection = self.task_tree.selection()
        return self.locations.get(selection[0]) if selection else None

    def update_actions(self, event=None):
        location = self.selected_location()
        self.subtask_button.configure(state="normal" if location and len(location) < MAX_DEPTH else "disabled")
        for button in (self.complete_button, self.delete_button):
            button.configure(state="normal" if location else "disabled")

    def add_task(self):
        location = self.model.add_task(self.task_entry.get())
        if location is not None:
            self.task_entry.delete(0, tk.END)
            self.show_section(location)
            self.save_tasks()

    def add_subtask(self):
        location = self.selected_location()
        if location is None or len(location) >= MAX_DEPTH:
            return
        text = simpledialog.askstring("New Subtask", "Subtask:", parent=self.root)
        if text is not None:
            new_location = self.model.add_task(text, parent=location)
            if new_location is not None:
                self.show_section(new_location)
                self.save_tasks()

    def complete_task(self, toggle=False):
        location = self.selected_location()
        if location is not None:
            if toggle:
                self.model.toggle(location)
            else:
                self.model.complete(location)
            self.refresh_sections()
            self.task_tree.item(self.task_tree.selection()[0], text=task_label(self.model.item(location)))
            self.save_tasks()

    def delete_task(self):
        location = self.selected_location()
        if location is not None:
            self.model.delete(location)
            self.show_section()
            self.save_tasks()

    def double_click(self, event):
        row = self.task_tree.identify_row(event.y)
        # Arrow clicks only expand/collapse; blank space never completes a task.
        element = self.task_tree.identify_element(event.x, event.y)
        if row and "indicator" not in element:
            self.task_tree.selection_set(row)
            self.complete_task(toggle=True)
            return "break"


def main():
    root = tk.Tk()
    root.withdraw()
    try:
        initialize_user_data(TASKS_FILE)
        data = load_data(TASKS_FILE)
    except (OSError, ValueError) as error:
        messagebox.showerror("Could not load tasks",
                             f"Your saved file was left intact.\n\n{error}", parent=root)
        root.destroy()
        return
    TodoApp(root, data)
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
