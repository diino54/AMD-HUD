"""Launch the Python/Qt HUD settings window."""
from settings_qt import SettingsApp, main
from settings_store import PALETTE, write_config

if __name__ == '__main__':
    raise SystemExit(main())
