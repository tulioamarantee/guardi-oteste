import streamlit as st
import os

def apply_custom_branding(user=None):
    """
    Aplica o tema Light profissional para o BBM Guard.
    """
    st.markdown("""
        <style>
        /* Ajuste de Botões com azul corporativo */
        div.stButton > button:first-child {
            background-color: #004085;
            color: white !important;
            border-radius: 6px;
            border: none;
            transition: all 0.3s;
        }
        div.stButton > button:hover {
            background-color: #002752;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }

        /* Badges de Status (Cores adaptadas para leitura em claro/escuro) */
        .badge {
            padding: 4px 10px;
            border-radius: 12px;
            font-weight: 600;
            font-size: 0.8rem;
            display: inline-block;
        }
        .badge-sucesso { background-color: #198754; color: #FFFFFF; }
        .badge-perigo { background-color: #DC3545; color: #FFFFFF; }
        .badge-atencao { background-color: #FFC107; color: #000000; }

        /* Estilização para as caixas de Status SIL */
        .status-box {
            background-color: var(--secondary-background-color); 
            padding: 10px; 
            border-radius: 5px; 
            margin-top: 10px;
            color: var(--text-color);
        }

        /* Títulos */
        h1, h2, h3 {
            color: var(--text-color) !important;
        }
        </style>
    """, unsafe_allow_html=True)

def render_header(user=None):
    """
    Cabeçalho BBM Guard com Logo.
    """
    logo_path = "logo_bbm.png"
    
    col1, col2 = st.columns([1, 4])
    with col1:
        if os.path.exists(logo_path):
            st.image(logo_path, width=120)
        else:
            st.markdown("<h1 style='margin:0;'>🛡️</h1>", unsafe_allow_html=True)
    with col2:
        st.markdown("<h2 style='margin:0;'>BBM Guard</h2>", unsafe_allow_html=True)
        st.caption("Sistema de Controle de Acesso e Portaria")

def render_sil_status(status, data_consulta):
    """
    Exibição de status SIL.
    """
    status_norm = str(status).strip().lower()
    color = "#28a745" if status_norm == "validado" else "#dc3545"
    
    st.markdown(f"""
        <div class='status-box'>
            <b>Status SIL:</b> <span style='color: {color}; font-weight: bold;'>{status}</span>
            <br><small>Consulta realizada em: {data_consulta}</small>
        </div>
    """, unsafe_allow_html=True)

def render_driver_badge(status_interno, recentes=0):
    """
    Badges para Portaria.
    """
    if status_interno == 'Ativo':
        st.markdown('<span class="badge badge-sucesso">LIBERADO</span>', unsafe_allow_html=True)
    else:
        st.markdown(f'<span class="badge badge-perigo">{status_interno.upper()}</span>', unsafe_allow_html=True)
