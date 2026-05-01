#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup_populate.sh  —  Install the populate_nhea management command & run it
#
# Run from your Django project root (where manage.py lives):
#     bash setup_populate.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="voting/management/commands"

echo "→ Creating management command directory structure…"
mkdir -p "$SCRIPT_DIR"

# Ensure __init__.py files exist
touch voting/management/__init__.py
touch voting/management/commands/__init__.py

echo "→ Copying populate_nhea.py into $SCRIPT_DIR …"
cp populate_nhea.py "$SCRIPT_DIR/populate_nhea.py"

echo "→ Installing requests (needed for avatar downloads)…"
pip install requests --quiet

echo ""
echo "Done! You can now run:"
echo ""
echo "  python manage.py populate_nhea               # populate everything"
echo "  python manage.py populate_nhea --clear       # wipe first, then populate"
echo "  python manage.py populate_nhea --no-images   # skip avatar downloads"
echo "  python manage.py populate_nhea --voters-only # only add voters"
echo "  python manage.py populate_nhea --no-voters   # skip voter creation"
echo ""
echo "Running now with --no-images for speed (add images manually or re-run without flag)…"
echo ""
python manage.py populate_nhea