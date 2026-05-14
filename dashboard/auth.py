"""
Módulo de autenticación simple para Streamlit.

Uso:
- Lee credenciales desde el archivo .env ubicado en la raíz del proyecto.
- Bloquea el dashboard hasta que el usuario inicie sesión.
- Permite cerrar sesión desde el sidebar.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv


# ============================================================================
# Configuración
# ============================================================================

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

APP_USER = os.getenv("APP_USER")
APP_PASSWORD = os.getenv("APP_PASSWORD")

SESSION_TIMEOUT_SECONDS = 3600


# ============================================================================
# Funciones de autenticación
# ============================================================================

def check_auth() -> bool:
    """Valida si el usuario tiene una sesión activa."""

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if "login_time" in st.session_state:
        session_age = time.time() - st.session_state["login_time"]

        if session_age > SESSION_TIMEOUT_SECONDS:
            st.session_state["authenticated"] = False
            st.session_state.pop("login_time", None)

    return bool(st.session_state["authenticated"])


def login() -> None:
    """Renderiza la pantalla de login."""

    st.markdown(
        """
        <style>
            .stApp {
                background:
                    radial-gradient(circle at top left, #1e293b, #020617);
            }

            .login-card {
                padding: 3rem;
                border-radius: 24px;
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.12);
                box-shadow: 0 24px 80px rgba(0,0,0,0.35);
                margin-top: 10vh;
            }

            .login-title {
                text-align: center;
                font-size: 2rem;
                font-weight: 700;
                color: white;
                margin-bottom: 0.25rem;
            }

            .login-subtitle {
                text-align: center;
                color: #94a3b8;
                margin-bottom: 2rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 1.2, 1])

    with col2:
        st.markdown('<div class="login-card">', unsafe_allow_html=True)

        st.markdown(
            '<div class="login-title">🔐 Acceso Seguro</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="login-subtitle">C&A Systems · Azure Inventory Dashboard</div>',
            unsafe_allow_html=True,
        )

        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")

        if st.button("Ingresar", use_container_width=True):
            if not APP_USER or not APP_PASSWORD:
                st.error("Faltan variables APP_USER o APP_PASSWORD en el archivo .env")
                return

            if username == APP_USER and password == APP_PASSWORD:
                st.session_state["authenticated"] = True
                st.session_state["login_time"] = time.time()
                st.rerun()

            st.error("Usuario o contraseña incorrectos")

        st.markdown("</div>", unsafe_allow_html=True)


def logout() -> None:
    """Muestra botón para cerrar sesión."""

    st.sidebar.divider()

    if st.sidebar.button("Cerrar sesión", use_container_width=True):
        st.session_state["authenticated"] = False
        st.session_state.pop("login_time", None)
        st.rerun()