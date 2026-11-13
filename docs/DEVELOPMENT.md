# Development and verification

Read [AGENTS.md](../AGENTS.md) first. This guide covers reproducible commands,
test scope, and safe operation of the existing application. Commands below assume
Command Prompt (CMD) with the working directory set to the project root.

## Local environment

The verified environment is Windows with 64-bit Python 3.12.14 and Tkinter, an AMD
Adrenalin installation exposing ADLX, and the vendored PresentMon 2.6.0 executable.
The known machine used an RX 6700 XT and Ryzen 5 5600. These are observations, not
requirements that exclude every other AMD GPU or CPU.

For an existing installation, use its venv; do not recreate or upgrade it unnecessarily:

```cmd
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip show amd-adlx PySide6
.\.venv\Scripts\python.exe -c "import tkinter; import adlx; import PySide6"
```

For a fresh GitHub checkout, create a local configuration from the public example
before the first launch. Do not overwrite an existing configuration:

```cmd
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if not exist config.json copy config.example.json config.json
.\Create-DesktopShortcut.cmd
```

The dependency install needs access to the package source. These commands do not
download or install AMD drivers, the vendor SDK, PresentMon, or a replacement CPU
server. Preserve bundled licenses. The ADLX SDK reference tree and `amd-adlx` Python
binding are separate components; running this setup does not require a C++ build.
The reference SDK under `vendor/ADLX` stays local and is excluded from publication.
The GitHub file set includes the runtime PresentMon executable, fonts, and their
existing upstream licenses. Local tests, logs, environments, and user configuration
are intentionally excluded by the `.gitignore` allowlist. The test instructions
below apply to the full local development workspace; tests are not shipped in the
public checkout. Add new distributable files explicitly to `.gitignore`.

## Checks proportional to the change

| Change | Suitable checks |
| --- | --- |
| Documentation only | Local links, commands, module/setting references, factual comparison with source; no HUD restart |
| Config/save/UI behavior | `test_settings`; validate conflicts, invalid input, disabled values, dirty close behavior |
| Graph/FPS calculations | `test_hud.FpsTests`; controlled batches, source changes, timestamps, spikes, reveal boundaries |
| Frame/shadow pixels | `test_hud.RoundedRenderingTests`; inspect native composition over a contrasting background |
| Visibility/input/window code | `test_hud.WindowVisibilityTests`, native foreground-event observation, then manual game check when available |
| CPU adapter | Packet decoder tests; verify server compatibility/freshness on the actual supported build |
| Dependency/native lifecycle changes | Full tests, telemetry probe, appropriate smoke/restart and resource cleanup checks |

Do not add redundant tests for a trivial parameter edit or repeatedly rerun an
already-passing suite without a new change, failure, or unresolved concern.

### Automated commands

```cmd
.\.venv\Scripts\python.exe -m unittest -q test_hud test_settings
.\.venv\Scripts\python.exe -m unittest -v test_hud.FpsTests
.\.venv\Scripts\python.exe -m unittest -v test_hud.WindowVisibilityTests
.\.venv\Scripts\python.exe -m unittest -v test_settings
```

The last full run before this documentation review passed 27 tests. Treat the count
as dated evidence, not a permanent acceptance criterion; inspect the current suite.

`test_settings.py` uses Qt's offscreen platform, temporary config files, and fake
control events. It covers buffered edits, save ownership, conflicts, custom fonts,
graph settings, border/shadow options, invalid inputs, and wheel behavior. It does
not intentionally control the live HUD or save the real config.
It also checks mid-animation form clipping, rapid reversal, immediate mouse/keyboard
button commands, and the system-reduced-motion path. Animation tests use disposable
editor windows and controlled Qt timing; they do not click the user's live settings.

`test_hud.py` exercises geometry/alpha, private CPU packet decoding, game matching,
mutex/events, native non-activating window behavior, FPS filtering, QPC CSV parsing,
swap-chain hysteresis, stable graph reduction, gradual scale changes, and reveal.
Some checks create native Tk windows briefly and need an available Windows desktop.
They are not a complete headless or non-Windows test suite. Focus checks forbid the
HUD/test windows from becoming foreground; other apps may legitimately change focus.

If temporary-directory cleanup fails with `PermissionError` inside a sandbox, separate
that environment failure from a product failure. Use an authorized suitable execution
context or a writable temporary directory. Do not hide failed assertions or remove
the failing checks to obtain a green result.

## Diagnostics

```cmd
.\.venv\Scripts\python.exe hud.py --probe
.\.venv\Scripts\python.exe hud.py --probe-game
```

`--probe` reads actual ADLX/CPU data and prints JSON. It does not start frame capture,
so `fps` is unavailable. It asks the CPU adapter to sample with a short wait.
`--probe-game` reports the foreground path, recognized game paths, and profile errors.
If the console is foreground when it runs, seeing the console rather than the game
is expected. These outputs may contain personal paths; do not publish them unreviewed.

### Smoke test

```cmd
.\.venv\Scripts\python.exe hud.py --smoke-test
```

Stop the existing HUD gracefully first. Otherwise the instance guard exits with an
already-running message; exit status zero alone does not prove the smoke test ran.
Look for JSON with `hud_smoke_test: passed` and a sufficient successful-reading count.

The diagnostic displays outside games for approximately 3.2 seconds. It checks
telemetry reads and the real window lifecycle, not full game compatibility. Because
it uses the saved `refresh_ms`, a very slow interval can prevent the required second
reading before the deadline. Do not overwrite user config just to make this check
pass; explain that timing limitation or use an isolated test setup.

Desktop preview/smoke mode does not automatically target a desktop application for
FPS. An empty graph or `N/A` FPS there is expected without a recognized game PID.

## Running state, reload, and restart

Prefer **Stop HUD** in settings or the project's `HudControl` event to process kills.
Inspect state from a console without creating a second HUD:

```cmd
.\.venv\Scripts\python.exe -c "from pathlib import Path; from hud_control import HudControl; c=HudControl(Path.cwd()); print(c.running()); c.close()"
```

To request shutdown:

```cmd
.\.venv\Scripts\python.exe -c "from pathlib import Path; from hud_control import HudControl; c=HudControl(Path.cwd()); c.send('stop'); c.close()"
```

Remember whether it was running, wait for the mutex to disappear, validate, and
restore that state with the project's launcher/interpreter. Do not force-start a
previously stopped HUD or create duplicate instances to test a new feature.
Do not close dirty settings windows without preserving pending edits.

**Save and apply** reloads configuration and recreates native HUD resources while
holding the mutex. It does not re-import changed source. After changing imported
Python code, restart the affected process. Documentation-only edits need neither
HUD nor settings restart.

## Logs and failure reporting

- Starting from settings redirects stdout/stderr to `hud-output.log` and `hud-error.log`
  in the project directory, replacing previous contents on that start.
- `Start-HUD.cmd` runs console Python and pauses on an error; it does not provide
  the same automatic log redirection.
- `Settings.cmd` and the desktop shortcut use `pythonw.exe`; start `settings.py` with
  console Python to inspect startup exceptions when necessary.
- `settings-error.log` can exist from external diagnostic redirection; it is not an
  application-managed log guaranteed to be written on every launch.
- PresentMon stderr is discarded in ordinary capture. Diagnose its own executable
  separately when needed, keeping any diagnostic ETW session uniquely named/cleaned.

Report the command, relevant output, and scope. Do not expose private paths or logs
unnecessarily. A desktop focus test is not a manual Alt+Tab/game rendering test.

## Manual regression checklist when relevant

1. Check an active recognized windowed/borderless game; confirm numeric data and graph.
2. Confirm the graph grows progressively, scrolls across seven seconds, keeps straight
   antialiased segments, and has no dashed line or viewport-wide regrouping jumps.
3. Watch a real stall: do not mistake a measured frametime spike or intentional scale
   expansion for a fabricated animation. Min/max must remain actual measurements.
4. Alt+Tab out/in; verify hiding, fresh history, no focus theft, and no stale game values.
5. Exercise manual hide, stop, and saved-config preview. Preview should not save edits.
6. Check border/shadow on a contrasting desktop; translucent corners must not turn black.
7. With a recognized game and LS output on the same monitor, verify the additional
   LSFG row below FPS, compare it with LS output, stop scaling, and verify that the
   row disappears and the graph returns to its original position. An open LS
   settings window alone must not create the row. Alt+Tab must stop both captures.
8. Edit a setting, navigate tabs, cancel close, save explicitly, and test a stale-editor
   conflict using a disposable config rather than destroying live settings.

Only claim the items actually observed. Do not launch or manipulate a user's game
session unnecessarily for an unrelated documentation or palette edit.

## Icon and shortcut workflow

```cmd
.\.venv\Scripts\python.exe tools\build_icon.py
.\Create-DesktopShortcut.cmd
```

Rebuild only when the SVG changes. The generator writes a PNG preview and a multi-size
ICO (16, 20, 24, 32, 40, 48, 64, 128, 256 px). Settings and HUD refer to the ICO.
The shortcut points directly to `pythonw.exe` and quoted `settings.py`, with the
project working directory, and is updated under one stable name.

The CMD launcher uses Windows Script Host (`cscript.exe`) and the bundled
`tools/create_shortcut.vbs` helper to create the shortcut without PowerShell.
The desktop is resolved by Windows, including redirected desktops. A scratch check
can use an existing writable directory:

```cmd
.\Create-DesktopShortcut.cmd "C:\Path\To\Scratch"
```

Run `Create-StartMenuShortcut.cmd` to create or refresh the same `AMD HUD.lnk`
in the current user's Start menu Programs folder, resolved by Windows Script Host.
It uses the shared helper and the same target, arguments, working directory, and
icon as the desktop shortcut. It also accepts an optional destination directory
as its first argument for a scratch check. No administrator privileges are needed.

Refresh the actual desktop shortcut after every completed change as required by
`AGENTS.md`; scratch output is not a substitute for that final step.

## Keeping documentation accurate

Update `AGENTS.md` for workflow/user decisions, the architecture guide for data flow,
the configuration reference for settings, and troubleshooting for verified failure
mechanisms. Check local Markdown links and source symbols. Preserve upstream URLs
as references without claiming to have re-audited external content every time.
Keep experiments in the workspace's `work` directory; do not document a temporary
helper as a permanently shipped command. Do not assume a Git checkout or CI service.
