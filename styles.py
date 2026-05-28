import streamlit as st
import os

def apply_custom_branding(user=None):
    """
    Aplica o tema Light profissional para o BBM Guard.
    """
    st.markdown("""
        <style>
        /* Fundo claro e limpo */
        .stApp {
            background-color: #F8F9FA;
            color: #212529;
        }

        /* Sidebar com azul corporativo suave */
        [data-testid="stSidebar"] {
            background-color: #FFFFFF;
            border-right: 1px solid #E9ECEF;
        }

        /* Estilização de Cards e Expansores (Fundo Branco, Borda Suave) */
        .stExpander {
            background-color: #FFFFFF !important;
            border: 1px solid #E9ECEF !important;
            border-radius: 8px !important;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            margin-bottom: 10px;
        }
        
        .streamlit-expanderHeader {
            background-color: #FFFFFF !important;
            color: #004085 !important;
            font-weight: bold !important;
        }

        /* Botões com azul BBM */
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

        /* Badges de Status */
        .badge {
            padding: 4px 10px;
            border-radius: 12px;
            font-weight: 600;
            font-size: 0.8rem;
            display: inline-block;
        }
        .badge-sucesso { background-color: #D4EDDA; color: #155724; }
        .badge-perigo { background-color: #F8D7DA; color: #721C24; }
        .badge-atencao { background-color: #FFF3CD; color: #856404; }

        /* Títulos e Textos */
        h1, h2, h3 {
            color: #004085 !important;
        }
        
        .stMarkdown p {
            color: #495057;
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
        <div style='background-color: #f1f3f5; padding: 10px; border-radius: 5px; margin-top: 10px;'>
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
