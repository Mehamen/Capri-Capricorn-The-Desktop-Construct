"""
run_capri.pyw — launches Capri without a console window.
Used by autostart; you can also double-click it.
Output goes to capri.log next to this file.
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

log_path = os.path.join(ROOT, "capri.log")
try:
    if os.path.getsize(log_path) > 1_000_000:   # keep the log small
        os.remove(log_path)
except OSError:
    pass
log = open(log_path, "a", encoding="utf-8", buffering=1)
sys.stdout = sys.stderr = log

from capri.main import main

main()
