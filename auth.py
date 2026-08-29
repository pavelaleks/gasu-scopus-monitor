"""Вход в приложение: пароль из Secrets, опционально cookie в браузере."""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta
from pathlib import Path

import extra_streamlit_components as stx
import streamlit as st

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

DEFAULT_APP_PASSWORD = "12345"
COOKIE_NAME = "gasu_monitor_auth"
COOKIE_DAYS = 30
ENV_PATH = Path(__file__).with_name(".env")


def get_app_password() -> str:
    try:
        if "APP_PASSWORD" in st.secrets:
            value = str(st.secrets["APP_PASSWORD"]).strip()
            if value:
                return value
    except Exception:
        pass
    if load_dotenv:
        load_dotenv(ENV_PATH)
    env_value = (os.getenv("APP_PASSWORD") or "").strip()
    if env_value:
        return env_value
    return DEFAULT_APP_PASSWORD


def access_token(password: str) -> str:
    return hmac.new(
        password.encode("utf-8"),
        b"gasu-scopus-monitor-access",
        hashlib.sha256,
    ).hexdigest()


def passwords_match(entered: str, expected: str) -> bool:
    left = hashlib.sha256((entered or "").encode("utf-8")).hexdigest()
    right = hashlib.sha256((expected or "").encode("utf-8")).hexdigest()
    return hmac.compare_digest(left, right)


def cookie_manager() -> stx.CookieManager:
    return stx.CookieManager(key="gasu_auth_cookies")


def _cookie_unlocks(manager: stx.CookieManager, token: str) -> bool:
    stored = manager.get(COOKIE_NAME)
    if not stored:
        return False
    return hmac.compare_digest(str(stored), token)


def require_login(manager: stx.CookieManager) -> bool:
    password = get_app_password()
    token = access_token(password)

    if st.session_state.get("gasu_authenticated"):
        return True
    if _cookie_unlocks(manager, token):
        st.session_state["gasu_authenticated"] = True
        return True

    st.title("Мониторинг публикаций Scopus")
    st.subheader("Вход")
    st.caption("Доступ для сотрудников ГАГУ. Ключ Scopus в приложении не вводится.")
    st.text_input("Пароль", type="password", key="gasu_password_input")
    remember = st.checkbox("Запомнить в этом браузере", value=True)
    if st.button("Войти", type="primary"):
        if passwords_match(st.session_state.get("gasu_password_input", ""), password):
            st.session_state["gasu_authenticated"] = True
            if remember:
                manager.set(
                    COOKIE_NAME,
                    token,
                    expires_at=datetime.now() + timedelta(days=COOKIE_DAYS),
                    same_site="lax",
                )
            st.rerun()
        else:
            st.error("Неверный пароль.")
    return False


def logout(manager: stx.CookieManager) -> None:
    st.session_state.pop("gasu_authenticated", None)
    try:
        manager.delete(COOKIE_NAME)
    except Exception:
        pass
    st.rerun()
