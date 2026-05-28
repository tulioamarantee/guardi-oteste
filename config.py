# CONFIGURAÇÕES DA INTEGRAÇÃO OPENTECH SIL
import os
import streamlit as st

# --- Credenciais do WebService B2B ---
try:
    # Tenta carregar do st.secrets (ambiente online)
    WS_URL = st.secrets.get("WS_URL", "https://ws.opentechgr.com.br/sgrOpentech/sgropentech.asmx")
    WS_DOMINIO = st.secrets.get("WS_DOMINIO", "Transportadoras")
    WS_USUARIO = st.secrets.get("WS_USUARIO", "INT.DIALOG")
    WS_SENHA   = st.secrets.get("WS_SENHA", "INT@123456789")
    CD_PAS     = int(st.secrets.get("CD_PAS", 61027))
    CD_CLIENTE = int(st.secrets.get("CD_CLIENTE", 2673186))
except Exception:
    # Fallback para desenvolvimento local caso o arquivo secrets.toml não exista
    WS_URL = "https://ws.opentechgr.com.br/sgrOpentech/sgropentech.asmx"
    WS_DOMINIO = "Transportadoras"
    WS_USUARIO = "INT.DIALOG"
    WS_SENHA   = "INT@123456789"
    CD_PAS     = 61027
    CD_CLIENTE = 2673186

# --- Mapeamento de Status OpenTech ---
# 1: Recomendado/Validado
# 2: Não Recomendado
# 5: Em Pesquisa
# 8: Sem Pesquisa/Expirado
STATUS_MAP = {
    "1": "Validado",
    "2": "Validado",
    "5": "Em Pesquisa",
    "8": "Sem Pesquisa",
    "0": "Liberado"
}

def get_status_label(codigo):
    return STATUS_MAP.get(str(codigo), f"Status {codigo}")
