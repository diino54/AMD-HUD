# AMD HUD

A local Windows HUD using real AMD ADLX telemetry and process-specific FPS capture.
The settings application uses Python and PySide6. All project text is in English.

## Project documentation

- [AGENTS.md](AGENTS.md): primary contributor/agent instructions, user preferences,
  behavior invariants, module ownership, validation, and shortcut completion rules.
- [Architecture](docs/ARCHITECTURE.md): processes, threads, clocks, graph pipeline,
  native rendering, telemetry, resource lifetimes, and known limitations.
- [Configuration](docs/CONFIGURATION.md): every persisted key, bounds, actual defaults,
  units, UI conversions, metric sources, and persistence behavior.
- [Development and verification](docs/DEVELOPMENT.md): setup, targeted checks,
  diagnostics, restarts, manual regression scope, icons, and desktop shortcuts.
- [Troubleshooting](docs/TROUBLESHOOTING.md): visibility, hotkeys, focus, corners,
  graph delivery/reveal, unavailable measurements, save conflicts, and fonts.

Documentation was reviewed against the local source on 2026-11-07. Start with
`AGENTS.md` before changing the project; this README is the user-facing overview.

## Getting started

- Open `Settings.cmd` to configure the HUD.
- The **AMD HUD** desktop shortcut opens settings without a console window.
  Run `Create-DesktopShortcut.ps1` to create or refresh it after project changes.
  The editable icon source is `assets/app-icon.svg`; rebuild its PNG and multi-size
  Windows ICO with `.venv\Scripts\python.exe tools\build_icon.py`.
- The existing tabs are **Appearance**, **Behavior**, and **Games**.
- **Save and apply** saves the edit buffer and reloads a running HUD. Ctrl+S does the same.
- **Reload saved** discards unsaved form edits and loads the saved configuration.
- Closing settings does not stop the HUD. Closing with unsaved edits offers Save, Discard, or Cancel.
- **Start HUD** starts with the saved configuration; it does not silently save pending edits.
- **Preview 10 s** shows the saved HUD for ten seconds, including outside games.
- `Start-HUD.cmd` starts the HUD directly. Starting it again does not create a second instance.
- **Ctrl+Alt+F10** toggles HUD visibility in games. **Ctrl+Alt+F11** closes the HUD.
- `Check-ADLX.cmd` prints a diagnostic GPU/CPU sample.

The settings window follows the visual and interaction guidance in
[Vela](https://github.com/diino54/Vela), particularly its
[visual design guide](https://github.com/diino54/Vela/blob/main/docs/UI_DESIGN.md) and
[UI/UX philosophy](https://github.com/diino54/Vela/blob/main/docs/UI_UX_PHILOSOPHY.md).
The three-tab layout is preserved. No side panels, cards, or extra preview column were added.
The HUD retains its own color theme independently from the settings window.

Appearance edits stay in memory until an explicit save. Changing tabs and scrolling do not
write the configuration. Mouse-wheel events do not change numbers. Saves are atomic and
blocked if the file has changed outside the editor. Failed saves preserve the edit buffer.
Long game names and executable paths have tooltips containing their full values.

## Appearance

Appearance contains background, text, color, border, and shadow controls. Scroll down to
reach the border and shadow settings; the action buttons remain visible.
Click **Border** or **Shadow** to collapse or expand its options. Both start expanded;
folding a section preserves edits and does not save or change HUD configuration.
Settings includes short hover/focus transitions, press feedback, animated checkmarks,
sliding tab selection, page/status fades, and smooth wheel scrolling. Section contents
are progressively revealed without compressing their controls. Animations reverse
from their current state on rapid input and do not delay actions or save settings.
Windows' client-area animation preference is respected; motion is presentation-only.

**Choose font…** accepts a local `.ttf` or `.otf` file for HUD text. **Reset to default**
restores Consolas without changing the text size. Font changes remain in the edit buffer
until **Save and apply**. The selected file is referenced in place, not copied or installed
system-wide. Keep it at its saved location. If it later becomes unavailable, the HUD logs
the problem and falls back to Consolas. Columns remain aligned with proportional fonts.
The settings application's own font is independent from the HUD font.

**Show frametime graph** enables a sparkline beneath the four metric rows. It shows
the last 7 seconds of actual PresentMon frame intervals for the active game's
most active swap chain, with minimum and maximum values in milliseconds. Higher
spikes mean slower frames. The graph targets 60 Hz independently of ADLX polling.
It reuses canvas items and moves samples at subpixel positions for smoother scrolling.
The antialiased line joins plotted samples with straight segments, retaining peaks
without curved interpolation or averaging away stalls.
Frame positions use PresentMon QPC timestamps rather than CSV arrival times.
A drawing cursor progressively reveals known straight segments from the first
received point. A 250 ms playback buffer absorbs ordinary delivery batches;
additional backlogs above 120 ms catch up at up to 1.25x playback speed.
It stops at the latest received frame instead of predicting missing measurements.
The displayed range remains seven seconds; min/max use measured frames only.
Downsampling retains peaks in time-anchored buckets about one pixel wide, so scrolling
does not regroup existing samples. The vertical range expands for new spikes and
contracts gradually after they leave the window. Swap-chain selection resists brief
count changes and starts fresh history when switching sources.
There is no dashed reference line. Hidden HUDs suspend animation-rate updates.
**Graph height (px)** and **Graph color** control its appearance. Missing/stale data
shows **Waiting for frame data**; no sample values are invented. Changing games or
stopping capture clears the previous history. The graph is enabled by default.

- Border: enable/disable, width 0-8 px, opacity 0-100%, and color.
- Shadow: enable/disable, X/Y offsets from -100 to 100 px, opacity 0-100%, color,
  and blur strength from 0 to 64 px. It is disabled by default.
- Disabling an effect preserves its parameters.
- The shadow is a separate click-through layer below the HUD and does not move the text.
- Background and border edges use per-pixel alpha antialiasing through `UpdateLayeredWindow`.
- Rounded images and shadow masks are cached until the HUD size or configuration changes.

The optional Acrylic material uses the Windows compositor. Text stays sharp above the
blurred layer. Acrylic uses Windows' 8 px rounded corners to avoid black artifacts caused
by GDI window regions. At 100% material opacity, the unnecessary Acrylic layer is omitted
and the custom corner radius is used. If Windows rejects Acrylic, a plain background is used.
No additional system component or driver is installed for the appearance effects.

## Game visibility

The HUD appears only over a recognized foreground game when `games_only` is enabled.
Alt+Tab to the desktop, browser, or another app hides it and pauses telemetry/FPS capture.
Foreground detection runs every 200 ms. Returning to the game restores the HUD.
The overlay targets windowed, borderless, and Windows-composited fullscreen games.
While visible it restores its topmost position every 200 ms without taking focus,
including after a game raises its window during a display-mode change.
Fullscreen with HDR still requires per-game verification; legacy exclusive paths
that bypass desktop composition cannot display this external-window overlay.

Games are matched by full executable path using AMD's local `gmdb.blb` profiles, which are
reloaded every five seconds. Manually added executable paths are also supported.
Launchers, uninstalled games, AMD Link application profiles, Windows Media Player, and
Lossless Scaling are excluded. This is local profile-based recognition, not AMD's private
game-detection implementation. Missing profiles keep the HUD hidden except over manually
added games. Existing user paths and game names are preserved as data.

## Configuration

Use the settings window, or edit `config.json` and restart the HUD.

| Key | Meaning |
| --- | --- |
| `gpu_index` | GPU index, starting at 0 |
| `refresh_ms` | Telemetry interval, 250-10000 ms |
| `x`, `y` | HUD position in screen pixels |
| `opacity` | Plain background opacity, 0.2-1.0 |
| `blur`, `blur_opacity` | Acrylic enable flag and material opacity, 0.2-1.0 |
| `corner_radius` | Custom corner radius, 0-100 px; 0 means square corners |
| `font_size` | HUD font size, 8-48 |
| `font_file` | Custom TTF/OTF file path; an empty string restores Consolas |
| `frametime_graph` | Show the frametime sparkline below the metrics |
| `frametime_graph_height` | Plot height, 24-160 px |
| `frametime_color` | Sparkline and heading color in `#RRGGBB` format |
| `text_color`, `background_color`, `muted_color` | Colors in `#RRGGBB` format |
| `row_colors` | GPU, CPU, RAM, and FPS/API label colors |
| `border_enabled`, `border_width` | Border enable flag and width, 0-8 px |
| `border_color`, `border_opacity` | Border color and opacity, 0-1 |
| `shadow_enabled` | Shadow enable flag; false by default |
| `shadow_x`, `shadow_y` | Shadow offsets relative to the HUD, -100 to 100 px |
| `shadow_color`, `shadow_opacity` | Shadow color and opacity, 0-1 |
| `shadow_blur` | Shadow blur strength, 0-64 px |
| `click_through` | Pass mouse input through to the game |
| `games_only` | Restrict visibility to recognized foreground games |
| `amd_profiles_path` | Read-only AMD profile database path |
| `game_executables` | Additional full game executable paths |
| `excluded_executables` | Executable names excluded from detection |
| `metrics` | Telemetry fields requested by the HUD |

The visible layout has four rows: GPU usage/temperature, CPU usage/temperature,
system RAM, and FPS/frame time. Other GPU fields remain available to diagnostic reads.
`power` is ADLX `GPUPower`, not necessarily total board power. `N/A` means that a
supported, fresh value is unavailable.

Example of a manually added game:

```json
"game_executables": ["D:\\Games\\MyGame\\Game.exe"]
```

## CPU temperature

CPU temperature reuses the already installed AMD `CPUMetricsServer.exe`, its shared
memory, and its sampling event. Ryzen Master, LibreHardwareMonitor, or another driver
does not need to be installed. The AMD server must already be running; the HUD does not
launch it. Sampling runs on a worker thread, on demand, at most once per second.
A result is accepted only after the server's sample counter changes. Stale or invalid
values are displayed as `N/A`.

This private adapter was verified with `CPUMetricsServer 10,01,02,2068`.
It checks the executable's SHA-256 and rejects unknown builds instead of guessing their
memory layout. An Adrenalin update may require the adapter to be reviewed.
Only the telemetry capture flag is temporarily enabled and restored after a sample.
CPU tuning/control fields are not modified.

## FPS

Portable PresentMon 2.6.0 captures only the active game's process. FPS is calculated from
Present intervals in a rolling window of up to 1.5 seconds. With multiple swap chains,
the most active one is selected rather than summing their rates. This measures rendered
FPS and does not guarantee inclusion of generated frames. Startup or missing events show
`N/A`. Frame data is processed in memory rather than written to a trace file.
`DXGI` is labeled `DirectX`; it does not identify a specific DirectX version.

## Components

- Official [AMD ADLX SDK](https://github.com/GPUOpen-LibrariesAndSDKs/ADLX), under `vendor/ADLX`.
- SDK snapshot: `32b5a740d42295c5dfe9026b9f52683da0f3af91`.
- Python binding: `amd-adlx==1.0.3`, installed locally in `.venv`.
- Settings UI and offscreen graph rasterization: `PySide6==6.8.3`.
  The HUD uses Tkinter for its window/text/image canvas and native Windows layers.
- Noto Sans is bundled under `assets/fonts`, with its Open Font License.
- SDK license: `vendor/ADLX/ADLX SDK License Agreement.pdf`.
- [PresentMon 2.6.0](https://github.com/GameTechDev/PresentMon/releases/tag/v2.6.0), executable
  and license under `vendor/PresentMon`.

The SDK reference and prebuilt Python binding are separate downloads. Running this project
does not require compiling C++ or installing Visual Studio.

## Setup and diagnostics

Use 64-bit Python 3.12 with Tkinter. From the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe hud.py --probe
.\.venv\Scripts\python.exe settings.py
```

- `hud.py --probe-game`: report the foreground executable and recognized games.
- `hud.py --probe`: read ADLX and CPU telemetry; FPS is null because this command does not capture frames.
- `hud.py --smoke-test`: show the HUD for about three seconds and exit. This diagnostic mode
  intentionally shows it outside games.
- `python -m unittest -v test_hud test_settings`: renderer, telemetry, game matching,
  process-control, edit-buffer, validation, and persistence tests.

Administrator privileges are not required. A shortcut conflict is reported at startup
instead of leaving an overlay that cannot be closed.

## Verification

Verified on 2026-11-07 with an AMD Radeon RX 6700 XT, AMD Ryzen 5 5600,
driver `32.0.21045.16010`, ADLX runtime 1.4, and Python 3.12.14 x64.
Real GPU telemetry, CPU temperature, foreground Rust detection, and process-specific FPS
were observed. Border/shadow composition was visually checked over a contrasting background.
Automated checks cover game-to-desktop visibility transitions and capture cleanup.
Game-specific exclusive-fullscreen behavior and a manual Alt+Tab session remain unverified.

The HUD is shown and hidden through native non-activating window operations.
It avoids Tk's deiconify/restack path, which can interrupt a fullscreen game's
foreground state. A thread-local activation guard also prevents Tk's initial
native wrapper from taking focus before its non-activating styles are installed.
The guard applies only to the HUD GUI thread and is removed when that thread's
HUD session closes. The settings window remains interactive.
Regression checks cover startup, explicit activation attempts, repeated visibility
transitions, Tk client rendering, and preservation of the foreground window.
