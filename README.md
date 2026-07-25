# tkinter-utils

Lean, reusable building blocks extracted from tkinter-based robotics and
engineering tools. The package removes repeated UI plumbing without imposing an
application architecture or owning domain state.

## Components

| Component | Purpose | Extra dependency |
| --- | --- | --- |
| `BackgroundTaskRunner` | Run blocking work with Tk-thread callbacks, latest-only progress, errors, and cooperative cancellation | None |
| `TaskStatusPanel` | Present determinate or indeterminate progress and cancellation | None |
| `TkDebouncer` | Coalesce keyed `after()` callbacks and cancel them safely | None |
| `ScrollableFrame` | Vertically scrollable `ttk.Frame` with safe cross-platform wheel handling | None |
| `DataTable` / `ColumnSpec` | Refresh-stable, sortable `Treeview` records with selection and copy support | None |
| `ValidatedEntry` | Typed entry parsing, ranges, custom validation, and ttk invalid state | None |
| `WorldCanvas` | Pan/zoom 2D world coordinates, fit-to-bounds, transforms, and hit testing | None |
| `ImageViewer` | Fit-to-window Pillow images with pan, cursor zoom, transforms, and overlays | Pillow |
| `LiveImageViewer` | Latest-frame camera/sensor display with dropped-frame and FPS status | Pillow |
| `MatplotlibPanel` | Embedded figure, axes, Tk canvas, toolbar, and event connection | Matplotlib |
| `load_theme` / `set_theme` | Vendored Azure light/dark ttk theme | None |

Python 3.10 or newer is supported. tkinter must be present in the Python
installation.

## Add it to a project

This repository is designed to be used as a Git submodule:

```console
git submodule add <repository-url> vendor/tkinter_utils
python -m pip install -e "vendor/tkinter_utils[all]"
```

Install only what the project needs:

```console
python -m pip install -e vendor/tkinter_utils
python -m pip install -e "vendor/tkinter_utils[images]"
python -m pip install -e "vendor/tkinter_utils[plots]"
```

An editable install keeps imports conventional while submodule changes remain
immediately visible:

```python
from tkinter_utils import BackgroundTaskRunner, WorldCanvas, load_theme
```

If installation is deliberately avoided, add the submodule root—not its nested
`tkinter_utils` package directory—to `sys.path`.

## Background work and progress

Workers receive a `TaskContext`. They must not access tkinter widgets:

```python
import time
import tkinter as tk

from tkinter_utils import BackgroundTaskRunner, TaskStatusPanel

root = tk.Tk()
runner = BackgroundTaskRunner(root)
status = TaskStatusPanel(root)
status.pack(fill="x", padx=12, pady=12)


def detect(context):
    for frame_number in range(100):
        context.raise_if_cancelled()
        # Perform blocking work here.
        time.sleep(0.01)
        context.report(frame_number + 1)
    return "100 frames processed"


def start_detection():
    handle = runner.submit(
        detect,
        on_progress=lambda value: status.update_progress(value),
        on_success=lambda result: status.complete(result),
        on_error=lambda error: status.fail("Detection failed", detail=str(error)),
        on_cancelled=status.cancelled,
    )
    status.start(
        "Detecting markers",
        total=100,
        cancel_command=handle.cancel,
    )
```

`TaskContext.report()` is thread-safe and retains only the latest unconsumed
progress value, preventing high-rate workers from flooding Tk's event loop.
Success, error, cancellation, completion, and progress callbacks always run on
the Tk thread. Cancellation is cooperative: workers should periodically call
`raise_if_cancelled()` or inspect `cancelled`/`cancel_event`.
Positional and keyword arguments passed to `submit()` are forwarded to the
worker after its context argument.

The runner defaults to one worker to avoid accidental concurrent access to
devices or project stores. Increase `max_workers` only when the application
explicitly supports parallel operations. Destroying the runner's master widget
cancels active jobs and shuts down its executor.

## Scheduling and resize coalescing

`TkDebouncer` replaces repeated keyed callbacks:

```python
debouncer = TkDebouncer(root)


def on_resize(_event):
    debouncer.call("redraw-map", 75, redraw_map)


canvas.bind("<Configure>", on_resize)
```

Use `cancel(key)`, `flush(key)`, or `cancel_all()` when application state
changes. Like tkinter itself, its methods must be called on the Tk thread.

## Scrollable controls

Place application widgets in `content`:

```python
panel = ScrollableFrame(parent, height=300, padding=(12, 8))
panel.grid(row=0, column=0, sticky="nsew")
ttk.Label(panel.content, text="Settings").grid(row=0, column=0, sticky="w")
```

`canvas` and `scrollbar` remain exposed for normal tkinter configuration.
`refresh()` handles unusual programmatic layout changes and `scroll_to_top()`
resets the viewport. `inner` aliases `content` for migration from the existing
map-builder implementation.

Mouse-wheel bindings are installed per top-level window and removed precisely;
the component does not call `unbind_all`, so it cannot remove bindings owned by
other widgets.

## Tables and validated parameters

Describe table columns while retaining the original row objects:

```python
table = DataTable(
    parent,
    [
        ColumnSpec("name", "Device"),
        ColumnSpec("latency_ms", "Latency (ms)", anchor="e"),
    ],
    row_key="device_id",
)
table.set_rows(device_snapshots)
selected_devices = table.selected_rows()
```

Rows may be mappings or objects. A callable `row_key` or field name supplies a
stable, unique identity. `set_rows()` updates existing rows and preserves
selection/focus. Sorting uses raw values rather than formatted strings.
`copy_selected()` produces tab-separated text.

Use a small typed entry instead of a form framework:

```python
iterations = ValidatedEntry(
    parent,
    parser=int,
    min_value=1,
    max_value=10_000,
    name="Iterations",
)

try:
    count = iterations.get_value()
except ValueError as error:
    show_parameter_error(str(error))
```

Invalid input sets ttk's standard `invalid` state and exposes
`error_message`. Supply `validator=lambda value: "message" or None` for
domain-specific checks and bind `<<ValidationChanged>>` when surrounding UI
must react.

## WorldCanvas

Subclass the canvas and tag application-owned drawing items with `"world"`:

```python
class MapCanvas(WorldCanvas):
    def draw_world(self):
        x, y = self.world_to_canvas(robot.x, robot.y)
        radius = 6
        self.create_oval(
            x - radius,
            y - radius,
            x + radius,
            y + radius,
            fill="orange",
            tags=("world", "robot"),
        )


map_view = MapCanvas(parent, y_up=True, initial_scale=40)
map_view.set_world_bounds((-5, -3, 5, 3), fit=True)
```

`view_scale` is measured in canvas pixels per world unit. The component
provides `world_to_canvas()`, `canvas_to_world()`, `set_view()`,
`fit_bounds()`, `zoom_at()`, `pan_by()`, and `find_at()`. Mouse-wheel zoom is
cursor-centred; double-click restores the remembered bounds. Use `pan_button=2`
when left-click belongs to object selection.

## Images and camera streams

`ImageViewer` loads paths or accepts Pillow images:

```python
viewer = ImageViewer(parent, allow_upscale=False)
viewer.pack(fill="both", expand=True)
viewer.load(image_path)
```

Drag with the left mouse button to pan, use the wheel to zoom, and double-click
to fit again. Use `canvas_to_image()` for hit testing and override
`draw_overlay()` for markers, keypoints, or depth readouts:

```python
class MarkerViewer(ImageViewer):
    def draw_overlay(self, canvas):
        x, y = self.image_to_canvas(120, 80)
        canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill="orange")
```

For a camera producer thread, submit Pillow frames to `LiveImageViewer`:

```python
live_view = LiveImageViewer(parent)


def camera_thread():
    while running:
        frame = read_camera_frame_as_pillow()
        live_view.submit_frame(frame)
```

`submit_frame()` is the only widget method designed to be called from another
thread. It copies the image and replaces any unconsumed frame, keeping display
latency bounded. The view is preserved for equal-sized frames. Optional
`captured_at` values must use `time.monotonic()` seconds.

## Matplotlib

`MatplotlibPanel` imports Matplotlib only when instantiated:

```python
plot = MatplotlibPanel(parent, toolbar=True)
plot.axes.plot(times, positions)
plot.draw_idle()

connection_id = plot.connect("button_press_event", on_plot_click)
plot.disconnect(connection_id)
```

Use `projection="3d"` for a default 3D axes. For multi-plot layouts, construct
a `matplotlib.figure.Figure` yourself and pass it as `figure=...`; `axes` then
references its first axes when present.

## Theme

```python
loaded = load_theme(root, "light")  # falls back to clam and returns False
set_theme(root, "dark")
```

Pass `fallback=None` when loading errors should be fatal. Azure theme assets are
vendored in `azure_ttk_theme/` and retain their upstream MIT license.

## Usage guidelines

- Tk widgets, `BackgroundTaskRunner.submit()`, and `TkDebouncer` belong on the
  Tk thread. Only `TaskContext` and `LiveImageViewer.submit_frame()` are
  thread-safe.
- Keep device discovery, ROS integration, domain models, validation policy,
  dialogs, and business callbacks in the consuming application.
- Prefer composition: pair `BackgroundTaskRunner` with `TaskStatusPanel`, and
  put application controls inside `ScrollableFrame.content`.
- Extend only at explicit hooks such as `draw_world()` and `draw_overlay()`;
  private names beginning with `_` are not compatibility promises.
- Add new components only after the same application-independent plumbing
  appears in multiple projects.

## Development

Run the standard-library test suite from the repository root:

```console
python -m unittest discover -v
```

The tests create real tkinter windows and skip automatically if a display or an
optional dependency is unavailable.
