"""
Unified Refresh Entry Point (Wrapper for refresh_catalog.py)
Provides intuitive alias commands supporting both '--mode all|ingest|health' and '--mode full|ingest-only|health-only'.
"""
import sys
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Translate arguments if using shorthand
args = list(sys.argv)
mode_mappings = {
    "all": "full",
    "ingest": "ingest-only",
    "health": "health-only"
}

for i, arg in enumerate(args):
    if arg == "--mode" and i + 1 < len(args):
        target = args[i + 1].lower()
        if target in mode_mappings:
            args[i + 1] = mode_mappings[target]

sys.argv = args

from scripts.refresh_catalog import main

if __name__ == "__main__":
    main()
