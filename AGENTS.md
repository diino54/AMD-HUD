# Working on AMD HUD

This is the primary guide for agents and contributors working in this directory.
It records the current implementation and the user's established preferences.
New user instructions govern the requested change; these rules do not create an
extra approval step or prevent an explicitly requested behavior change.

## Language and communication

- Use English for code, identifiers, comments, UI text, accessible names, tooltips,
  dialogs, exceptions, tests, documentation, and launcher messages.
- Communicate with the user in English.
- Preserve real paths, game names, proper names, user data, and third-party files.
- Report what was actually changed and checked. Distinguish automated tests,
  desktop diagnostics, and observations inside a real game.
- Never describe generated test samples as game measurements or claim an in-game
  fullscreen/black-screen fix solely from a desktop smoke test.

## Project identity and boundaries

AMD HUD is a local Windows desktop overlay, not a modification of AMD Software's
Metrics Overlay. It uses ADLX, the existing AMD CPU telemetry server, and portable
PresentMon. It does not inject rendering code into game processes.

- Development environment: Windows, 64-bit Python 3.12 with Tkinter.
- Pinned Python dependencies: `requirements.txt`.
- HUD: Tkinter canvas/text, Qt offscreen graph rasterization, native Windows layers.
- Settings: PySide6 in a separate process, launched through `settings.py`.
- Runtime paths resolve from the source directory, not the caller's working directory.
- There is no supplied installer, packaged executable, build system, or CI workflow.

## Read before changing behavior

1. Read the affected module and its callers, not just the visible control.
2. Read [architecture](docs/ARCHITECTURE.md) for data flow and resource ownership.
3. Read [configuration](docs/CONFIGURATION.md) before changing persisted settings.
4. Use [development checks](docs/DEVELOPMENT.md) for validation and restarts.
5. Consult [troubleshooting](docs/TROUBLESHOOTING.md) for known failure mechanisms.

Source is authoritative if documentation disagrees with implementation. Correct
stale documentation alongside the relevant change. Do not silently change runtime
behavior just to make it agree with an old description.

## Settings UI and ownership of user data

- Preserve the single-column, three-tab layout: **Appearance**, **Behavior**, **Games**.
  Keep scrolling forms and persistent action buttons. Do not add cards, sidebars,
  additional panels, or a preview column unless explicitly requested.
- Vela's design documents are style references, not a mandate to copy its structure.
  Links are in `README.md`. The settings theme is independent from the HUD palette.
- Number controls must not change values on mouse-wheel scrolling. Preserve
  accessible names and tooltips for truncated game names and paths.
- Border and Shadow have inline collapsible headings, expanded on first use.
  Section expansion, window size, and the selected tab are remembered automatically
  in local `settings-ui.ini`.
  Preserve edits, do not save or mark HUD config dirty, and reveal a collapsed
  section when one of its fields fails validation.
- Settings motion lives in `ui_motion.py`. Keep feedback short and interruptible:
  button press about 65 ms, hover 140 ms, page fade 170 ms, tab slide 180 ms, section
  reveal 220 ms. Retarget from the current painted value; never queue old transitions.
- Effects must not delay command signals, disable input while animating, save config,
  or move button hit targets. Respect Windows client-area animation preferences.
- Clip a full-height section form through `RevealViewport`; do not shrink its grid
  and squash controls. Validation must expand instantly before focusing a bad field.
- Keep page opacity effects at the viewport level, not nested throughout its children.
  Do not update stylesheets every animation frame or sleep/block the GUI thread.
  Hidden controls stop feedback; only the visible dirty Save button has a looping glow.
- Editing, navigation, color/font selection, and palette reset affect the edit
  buffer only. Save only through an explicit save action, including Ctrl+S.
- **Start HUD** and **Preview 10 s** use saved configuration. They must not implicitly
  save edits or run an uncommitted form as runtime settings.
- Closing a dirty editor offers Save, Discard, and Cancel. Failed saves retain edits.
  Never discard a user's pending changes to simplify a restart or visual check.
- `SettingsApp.collect()` deep-copies loaded settings. Preserve unexposed keys and
  the values of disabled effects rather than rebuilding a partial config.
- Preserve digest conflict detection and atomic replacement in `write_config()`.
  A stale settings window must not overwrite external config changes.
- Treat `config.json` as live user data, not a disposable test fixture or template.
  Current font paths, opacity, game paths, position, and shadow settings are choices.
- `validate_config()` fills some missing keys in memory; reading must not re-save
  or normalize the user's file automatically.

## HUD layout, appearance, and fonts

- Preserve the four rows: GPU usage/temperature, CPU usage/temperature, RAM,
  FPS/API and frame interval. Active Lossless Scaling adds an automatic LSFG FPS
  row below FPS and above the graph, using the FPS accent. Preserve the four base
  rows when LS output is inactive.
- Keep explicit pixel columns so proportional custom fonts remain aligned.
- Separate numeric values from `FPS`, `GiB`, and `ms` with one space (for example,
  `60 FPS`, `12.5 GiB`, and `16.7 ms`).
- Preserve Rosé Pine defaults and configurable border, shadow, and colors.
- Custom TTF/OTF fonts are referenced in place and loaded privately through GDI.
  Do not install them globally or copy user font files without a reason.
- Font reset restores Consolas without changing text size. Missing/invalid fonts
  fall back to Consolas with an English diagnostic. Settings uses its own Noto Sans.
- Keep sharp text separate from native background/frame/shadow windows.
- Preserve per-pixel alpha at border and shadow edges. Binary window regions
  reintroduce jagged corners.
- Translucent Acrylic uses a Windows Composition host-backdrop brush and tint,
  clipped together with a rounded-rectangle geometry at the selected radius.
  Do not restrict blur to native DWM corner sizes or apply GDI window regions;
  those previously caused black-corner/background artifacts.
- Opaque backgrounds omit unnecessary Acrylic. Preserve plain-background fallback
  when Windows rejects the material.

## Visibility, focus, and game recognition

- Normally show only over an exact recognized foreground game executable path.
  Preview and `games_only=false` are explicit exceptions.
- Read AMD profiles without modifying them. Manual game changes belong to this
  project's config. A matching basename alone must not recognize another executable.
- Preserve exclusions for launchers, removed games, app/link/AI profiles, and
  explicitly excluded executable names.
- LSFG output detection requires a recognized foreground game and the visible
  native `LosslessScaling` output window on the same monitor. LS settings alone
  must not enable capture. Keep LS excluded from game recognition.
- Hiding stops both game and auxiliary LS PresentMon capture. Returning to a game starts fresh history;
  clear old displayed values instead of flashing the previous game's readings.
- HUD windows must never take the game's activation or keyboard focus.
- Keep `prevent_window_activation()` installed before Tk creates its first native
  wrapper and until the HUD session closes. Its CBT hook is local to the GUI thread.
- Show through `HudWindowVisibility` and native non-activating operations. Do not
  restore Tk `deiconify()`, forced focus, or activation-based raising.
- Preserve click-through behavior and non-activating background windows.
- Target windowed, borderless, and Windows-composited fullscreen presentation.
  Maintain non-activating topmost order while visible, including mode transitions.
  Do not promise legacy exclusive paths that bypass desktop composition, unverified
  fullscreen/HDR compatibility, or compatibility with every game's anti-cheat system.

## Frametime graph decisions

- Visible history is **7 seconds**, set by `hud.GRAPH_WINDOW_SECONDS`.
- Target animation cadence is about **60 Hz**, independent of `refresh_ms`.
  **Metrics refresh interval (ms)** controls metric text polling, including FPS text.
- Keep straight antialiased segments. No spline/curved interpolation and no dashed
  reference line. Do not average away measured stalls.
- PresentMon uses `--qpc_time`; convert CSV `QPCTime` with Windows QPC frequency.
  Frame ages, retries, animation, and reveal use `time.perf_counter()`.
- Never timestamp frames by CSV receipt time: ETW/pipe delivery can arrive in batches.
  Receipt times may track delivery liveness only; the graph tolerates advancing
  batches up to 3 seconds late with a 1.5-second delivery timeout. Source-change
  history starts at the selected chain's latest measured timestamp, not receipt time.
- Never mix `time.monotonic()` with QPC frame timestamps. On the verified Python 3.12
  runtime it uses `GetTickCount64()`, with a different epoch/resolution. Visibility
  and CPU sampling may retain their separate monotonic clocks.
- Keep time-anchored peak reduction. Screen-relative bins change selected samples
  during scrolling and can make an unchanged trace jump.
- `GraphReveal` begins at the first point and progressively clips known straight
  segments. Its interpolated endpoint is a drawing boundary, not a measurement.
- Keep viewport scrolling at elapsed QPC time independently of the reveal cursor.
  Exhausting a delivery batch stops drawing, not the movement of measured history.
- Never predict beyond received data. Missing/stale data returns to the waiting
  state. Min/max must use measured samples, not interpolated endpoints.
- Request an additional 1.5 seconds of capture history for reveal backlog while
  keeping the visible range at seven seconds.
- Keep gradual scale contraction when old peaks expire. Scale expansion for a real
  new spike is intentional; do not hide it with fabricated or averaged data.
- Keep swap-chain hysteresis and fresh history on source changes. Do not multiply
  FPS by summing swap chains or switch sources on every near-tie.
- Reuse the two Tk image buffers and canvas items; retain both `PhotoImage` references.
  Decode into the hidden buffer, then swap the canvas image. Never reconfigure the
  displayed photo in place. Match the raster
  background to Tk's color key so it does not become a solid rectangular block.
- Hidden HUDs do not need animation-rate timer wakeups.

## Module map and change routing

| Concern | Main files |
| --- | --- |
| Startup, config loading, ADLX, layout, scheduling | `hud.py` |
| Settings forms and edit buffer | `settings_qt.py`, `settings.py` |
| Responsive settings animation and painted controls | `ui_motion.py` |
| Palette, persistence validation, digest, atomic save | `settings_store.py` |
| PresentMon process, CSV reader, FPS, swap chains | `fps_counter.py` |
| Peak reduction, reveal, scale, plot rasterization | `frametime_graph.py` |
| Native Acrylic/frame/shadow and premultiplied alpha | `backdrop.py`, `composition_backdrop.py` |
| Non-activating mapping and thread-local guard | `window_visibility.py` |
| Profiles and foreground process recognition | `game_visibility.py` |
| Private AMD CPU telemetry adapter | `cpu_temperature.py` |
| Font name parsing and private font lifetime | `font_support.py` |
| Named events and per-directory instance mutex | `hud_control.py`, `single_instance.py` |
| Icon and shortcut | `assets/app-icon.svg`, `tools/build_icon.py`, `Create-DesktopShortcut.cmd` |
| Regression tests | `test_hud.py`, `test_settings.py` |

## Native resource and telemetry rules

- Declare correct `ctypes` argument/result types, especially handles and pointers
  on 64-bit Windows. Retain callback objects for their entire native lifetime.
- Release ADLX interfaces and collect references before `ADLXHelper.Terminate()`.
- Clean up worker threads, mappings, handles, hotkeys, windows, and fonts on failure
  as well as normal exit. Preserve the instance mutex through config reload.
- PresentMon runs with `CREATE_NO_WINDOW`, a PID filter, and its own `AMDHUD-<pid>`
  ETW session. The auxiliary LS output counter uses `AMDHUD-<pid>-LSFG` with the
  LS PID and displayed-frame intervals, excluding dropped frames. Never multiply
  game FPS to fabricate LS output. Terminate only the session owned by each counter.
- Never kill unrelated Python, AMD, PresentMon, or game processes to clear a conflict.
- CPU temperature reuses the existing `CPUMetricsServer.exe`. Do not introduce a
  driver, sensor service, or third-party monitoring dependency incidentally.
- Preserve the CPU server SHA-256 guard, packet layout checks, freshness tests,
  mutex protection, and unavailable result for unknown builds.
- The CPU adapter temporarily sets a telemetry-request byte and attempts to restore
  it under the mutex. This IPC is not entirely read-only. Never extend it into CPU
  tuning/control fields as part of a telemetry/UI change.
- Do not patch AMD binaries or bypass the hash check to conceal `N/A`. Review the
  adapter when an Adrenalin update changes the server build.
- Unsupported or stale readings legitimately produce `N/A`. Do not fabricate a
  temperature, frame interval, or exact DirectX version as a fallback.

## Change and verification workflow

1. Inspect the affected source, current config, and running state without overwriting
   user data. Keep the task focused.
2. For a new setting, cover defaults/validation, editor load/collect, disabled-value
   preservation, persistence, and documentation as appropriate.
3. Run checks proportional to the change using the local venv. Add meaningful bug
   regression tests; do not add tests that simply mirror trivial implementation.
4. For rendering/input changes, check native behavior where relevant. Offscreen Qt
   tests cannot establish compositor behavior or actual game compatibility.
5. When code changes require it, gracefully stop and restart a previously running
   HUD after validation. Restore its prior running state. Config reload does not
   re-import changed Python modules. Documentation-only edits need no HUD restart.
6. Preserve dirty settings windows. Restart them only when necessary without losing
   pending edits. Closing settings must not stop the HUD.
7. Refresh the desktop shortcut after every completed change, including documentation.
   Report actual checks and any remaining limitations.

CMD commands from the project directory:

```cmd
.\.venv\Scripts\python.exe -m unittest -q test_hud test_settings
.\.venv\Scripts\python.exe hud.py --probe
.\.venv\Scripts\python.exe hud.py --probe-game
rem Requires the HUD instance to be stopped; temporarily displays outside games.
.\.venv\Scripts\python.exe hud.py --smoke-test
.\Create-DesktopShortcut.cmd
```

Use the available permission mechanism for actual filesystem/sandbox boundaries.
A sandbox denial does not prove that the application requires administrator rights.
Preserve diagnostics rather than suppressing errors. See the development guide for
test scope, temporary directories, and manual verification limits.

## Desktop shortcut and icon completion rule

- Run `Create-DesktopShortcut.cmd` after each completed fix, feature, or docs update.
- Maintain one **AMD HUD.lnk** in the OS-resolved desktop directory.
- Target this project's `.venv\Scripts\pythonw.exe` with `settings.py`, the project
  working directory, and `assets/app-icon.ico`.
- Do not create dated/numbered duplicates or alter unrelated shortcuts.
- `Create-StartMenuShortcut.cmd` creates the same settings shortcut in the current
  user's OS-resolved Start menu Programs folder using `tools/create_shortcut.vbs`.
- Pass a destination directory as the first argument for a scratch check when useful.
- Edit `assets/app-icon.svg`, then run `tools/build_icon.py` to regenerate PNG/ICO.
  Keep all three together; the ICO contains nine sizes from 16 to 256 px.
- Use the existing permission mechanism if the desktop is outside writable roots;
  do not silently put the requested desktop shortcut elsewhere.

## Documentation and repository hygiene

- Keep agent instructions here, implementation details in `docs/`, usage in `README.md`.
- Use placeholder paths in generic examples instead of copying personal config data.
- In the current workspace, scratch diagnostics belong under `../../work`, outside
  the product directory. Permanent guides must not depend on helpers from a past chat.
- Preserve vendor/font licenses and upstream source. Avoid bulk edits of `vendor/`,
  `.venv/`, bytecode, logs, or live user config.
- Do not assume this directory is a Git checkout or invent commit/CI evidence.
- A target of 60 Hz is not a guaranteed frame rate on every machine. Keep implementation
  guarantees, performance measurements, and manual observations clearly separated.
