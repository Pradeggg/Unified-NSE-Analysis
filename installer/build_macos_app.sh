#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# build_macos_app.sh
#
# Build a macOS .app bundle for Agent Adda that:
#   • Lives at  installer/macos/Agent Adda.app  (or copies to /Applications)
#   • Has a proper icon converted from docs/Agent-adda-logo.jpg
#   • Launches the agent in a new Terminal window inside the project venv
#
# Usage:
#   ./installer/build_macos_app.sh                 # build into installer/macos/
#   ./installer/build_macos_app.sh --install       # also copy to /Applications
#   ./installer/build_macos_app.sh --user-install  # copy to ~/Applications
#
# Re-runnable; safe to invoke after a `git pull`.
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="Agent Adda"
BUILD_DIR="$ROOT/installer/macos"
APP_BUNDLE="$BUILD_DIR/${APP_NAME}.app"
LOGO="$ROOT/docs/Agent-adda-logo.jpg"
INSTALL_DEST=""

for arg in "$@"; do
    case "$arg" in
        --install)       INSTALL_DEST="/Applications" ;;
        --user-install)  INSTALL_DEST="$HOME/Applications" ;;
        -h|--help)
            sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'
            exit 0 ;;
        *) echo "Unknown arg: $arg" >&2; exit 1 ;;
    esac
done

[[ "$(uname -s)" == "Darwin" ]] || { echo "macOS only."; exit 1; }
[[ -f "$LOGO" ]] || { echo "Missing logo at $LOGO"; exit 1; }

echo "── Building ${APP_NAME}.app ──"
rm -rf "$APP_BUNDLE"
mkdir -p "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Resources"

# ── 1. Build .icns from the JPG logo ─────────────────────────────────────────
TMP_ICONSET="$(mktemp -d)/AgentAdda.iconset"
mkdir -p "$TMP_ICONSET"
# Square crop first (1184 → 1024 square via sips)
TMP_PNG="$(mktemp -d)/logo.png"
sips -s format png "$LOGO" --out "$TMP_PNG" >/dev/null
# Generate every required size
for size in 16 32 64 128 256 512 1024; do
    sips -z "$size" "$size" "$TMP_PNG" --out "$TMP_ICONSET/icon_${size}x${size}.png" >/dev/null
done
# Retina pairs
cp "$TMP_ICONSET/icon_32x32.png"   "$TMP_ICONSET/icon_16x16@2x.png"
cp "$TMP_ICONSET/icon_64x64.png"   "$TMP_ICONSET/icon_32x32@2x.png"
cp "$TMP_ICONSET/icon_256x256.png" "$TMP_ICONSET/icon_128x128@2x.png"
cp "$TMP_ICONSET/icon_512x512.png" "$TMP_ICONSET/icon_256x256@2x.png"
cp "$TMP_ICONSET/icon_1024x1024.png" "$TMP_ICONSET/icon_512x512@2x.png"
rm -f "$TMP_ICONSET/icon_64x64.png" "$TMP_ICONSET/icon_1024x1024.png"
iconutil -c icns "$TMP_ICONSET" -o "$APP_BUNDLE/Contents/Resources/AgentAdda.icns"
echo "  ✓ icon: AgentAdda.icns"

# ── 2. Info.plist ────────────────────────────────────────────────────────────
cat > "$APP_BUNDLE/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Agent Adda</string>
    <key>CFBundleDisplayName</key><string>Agent Adda</string>
    <key>CFBundleIdentifier</key><string>com.agentadda.launcher</string>
    <key>CFBundleVersion</key><string>1.0.0</string>
    <key>CFBundleShortVersionString</key><string>1.0.0</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleExecutable</key><string>AgentAdda</string>
    <key>CFBundleIconFile</key><string>AgentAdda</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>LSApplicationCategoryType</key><string>public.app-category.finance</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>LSUIElement</key><false/>
</dict>
</plist>
PLIST
echo "  ✓ Info.plist"

# ── 3. Launcher executable ───────────────────────────────────────────────────
# Substitute the real project root so the app remembers where the code lives.
LAUNCHER="$APP_BUNDLE/Contents/MacOS/AgentAdda"
cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/usr/bin/env bash
# Agent Adda app-bundle launcher.
# Opens a new Terminal window and starts the agent REPL in the project venv.
set -e

PROJECT_ROOT="$ROOT"
VENV_PY="\$PROJECT_ROOT/.venv/bin/python"
ENTRY="\$PROJECT_ROOT/nse_agent.py"

# Quick sanity — bail with a GUI alert if venv is missing
if [[ ! -x "\$VENV_PY" ]]; then
    osascript -e 'display alert "Agent Adda — not installed" message "The .venv was not found at '"\$PROJECT_ROOT"'. Run installer/install.sh first." as critical'
    exit 1
fi
if [[ ! -f "\$ENTRY" ]]; then
    osascript -e 'display alert "Agent Adda — missing entry" message "nse_agent.py not found in '"\$PROJECT_ROOT"'." as critical'
    exit 1
fi

# Hand the work to Terminal so the user sees the REPL.
osascript <<APPLESCRIPT
tell application "Terminal"
    activate
    do script "cd '\$PROJECT_ROOT' && '\$VENV_PY' '\$ENTRY'"
end tell
APPLESCRIPT
LAUNCHER_EOF
chmod +x "$LAUNCHER"
echo "  ✓ launcher: Contents/MacOS/AgentAdda"

# ── 4. Optional install ──────────────────────────────────────────────────────
if [[ -n "$INSTALL_DEST" ]]; then
    mkdir -p "$INSTALL_DEST"
    DEST_APP="$INSTALL_DEST/${APP_NAME}.app"
    rm -rf "$DEST_APP"
    cp -R "$APP_BUNDLE" "$DEST_APP"
    # macOS gatekeeper: clear quarantine so it opens without right-click
    xattr -dr com.apple.quarantine "$DEST_APP" 2>/dev/null || true
    echo "  ✓ installed: $DEST_APP"
fi

echo
echo "Done."
echo "  Built:    $APP_BUNDLE"
[[ -n "$INSTALL_DEST" ]] && echo "  Installed: $INSTALL_DEST/${APP_NAME}.app"
echo
echo "Tip: drag the .app to your Dock to launch with one click."
