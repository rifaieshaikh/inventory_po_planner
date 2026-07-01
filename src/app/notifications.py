from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st


NOTIFICATION_HISTORY_KEY = "notification_history"
PENDING_TOASTS_KEY = "pending_toasts"
MAX_NOTIFICATION_HISTORY = 200


def add_notification(level: str, message: str, context: str = "") -> None:
    text = str(message or "").strip()
    if not text:
        return
    entry = {
        "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Level": str(level or "info").strip().title(),
        "Message": text,
        "Context": str(context or "").strip(),
    }
    history = st.session_state.setdefault(NOTIFICATION_HISTORY_KEY, [])
    history.insert(0, entry)
    del history[MAX_NOTIFICATION_HISTORY:]
    st.session_state.setdefault(PENDING_TOASTS_KEY, []).append(entry)


def add_notifications(messages: list[tuple[str, str]], context: str = "") -> None:
    for level, message in messages:
        add_notification(level, message, context=context)


def render_pending_toasts() -> None:
    pending = st.session_state.pop(PENDING_TOASTS_KEY, [])
    for entry in pending:
        level = str(entry.get("Level", "Info"))
        message = str(entry.get("Message", ""))
        if message:
            st.toast(f"{level}: {message}")


def render_notifications_page() -> None:
    st.title("Notifications")
    history = st.session_state.get(NOTIFICATION_HISTORY_KEY, [])
    if not history:
        st.info("No notifications yet.")
        return

    col_a, col_b = st.columns([1, 3])
    if col_a.button("Clear Notifications", key="notifications__clear"):
        st.session_state[NOTIFICATION_HISTORY_KEY] = []
        st.session_state[PENDING_TOASTS_KEY] = []
        st.rerun()

    df = pd.DataFrame(history)
    levels = sorted(df["Level"].dropna().astype(str).unique())
    selected = col_b.multiselect("Level", levels, key="notifications__level_filter")
    if selected:
        df = df[df["Level"].isin(selected)]
    st.dataframe(df, hide_index=True, width="stretch")
