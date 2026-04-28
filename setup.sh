#!/bin/bash
# Setup script for Letterboxd -> Obsidian sync
# Run this once after setting your TMDB_API_KEY in the .env file

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.letterboxd.obsidian-sync"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo "=== Letterboxd -> Obsidian Sync Setup ==="
echo ""

# Check .env exists
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "No .env file found. Creating from .env.example..."
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    echo "Please edit $SCRIPT_DIR/.env and set your TMDB_API_KEY."
    echo "Then re-run this script."
    exit 1
fi

# Check TMDB key is set
if grep -q "your_tmdb_api_key_here" "$SCRIPT_DIR/.env"; then
    echo "TMDB_API_KEY is not set in .env file."
    echo "Edit $SCRIPT_DIR/.env and replace 'your_tmdb_api_key_here' with your key."
    echo "Get a free key at: https://www.themoviedb.org/settings/api"
    exit 1
fi

echo "1. Installing automatic sync (runs every 6 hours)..."

# Unload existing if present
launchctl unload "$PLIST_DST" 2>/dev/null || true

# Generate plist with correct paths for this machine
cat > "$PLIST_DST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>
    <key>ProgramArguments</key>
    <array>
        <string>$SCRIPT_DIR/.venv/bin/python</string>
        <string>$SCRIPT_DIR/sync.py</string>
        <string>--rss</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    <key>StartInterval</key>
    <integer>21600</integer>
    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/sync.log</string>
    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/sync-error.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF

# Load the agent
launchctl load "$PLIST_DST"

echo "   Installed and loaded: $PLIST_DST"
echo ""
echo "2. Setup complete!"
echo ""
echo "Commands:"
echo "  Bulk import:     cd $SCRIPT_DIR && source .venv/bin/activate && python sync.py --bulk /path/to/diary.csv"
echo "  Manual RSS sync: cd $SCRIPT_DIR && source .venv/bin/activate && python sync.py --rss"
echo "  View logs:       cat $SCRIPT_DIR/sync.log"
echo "  Stop auto-sync:  launchctl unload $PLIST_DST"
echo "  Start auto-sync: launchctl load $PLIST_DST"
