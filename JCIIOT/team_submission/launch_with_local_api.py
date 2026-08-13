"""Launch the organizer UI with local, uncommitted API defaults."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIG = Path(__file__).resolve().parent / ".local" / "api_credentials.json"


def _load_local_defaults() -> None:
    # The local file is intentionally excluded from submissions.  On another
    # machine the official sidebar remains available when it is absent.
    if not LOCAL_CONFIG.exists():
        return

    config = json.loads(LOCAL_CONFIG.read_text(encoding="utf-8"))
    text = config["text_llm"]
    vision = config["vision_llm"]

    defaults = {
        "_llm_backend": text.get("backend", "openai"),
        "_llm_backend_select": "OpenAI API",
        "_openai_api_key": text["api_key"],
        "_openai_base_url": text["base_url"],
        "_openai_model": text["model"],
        "_vlm_api_url": vision["base_url"],
        "_vlm_api_key": vision["api_key"],
        "_vlm_model": vision["model"],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


_load_local_defaults()
runpy.run_path(str(PROJECT_ROOT / "app.py"), run_name="__main__")
