# dashboards/apps/minimal_app/app.py
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

from mainsequence.dashboards.streamlit.scaffold import PageConfig, run_page
from mainsequence import logger

# Ensure repo root is importable (same as before)
ROOT = Path(__file__).resolve().parent
if str(ROOT.parent.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent.parent))


logger.info("Starting Main Sequence Streamlit minimal app...")

ctx = run_page(
    PageConfig(
        title="Main Sequence Demo App",
        use_wide_layout=True,
        inject_theme_css=True,
    )
)

st.caption("Sample Streamlit running in Main Sequence ")



