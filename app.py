"""
Auditoria de Cobrança M2M — Dashboard Streamlit.

Execute com:
    streamlit run app.py
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from src.config import (
    COL_AUD_STATUS_DISPOSITIVO,
    COL_AUD_MOTIVOS_CADASTRO,
    COL_AUD_MOTIVOS_COBRANCA,
    COL_AUD_RISCO_CADASTRO,
    COL_AUD_RISCO_COBRANCA,
    DIAS_SEM_GPS,
    FLAGS_AUDITORIA,
    FLAG_DISPOSITIVO_INATIVO,
    FLAG_ICCID_DUPLICADO,
    FLAG_IMEI_DUPLICADO,
    FLAG_PLACA_DUPLICADA,
    FLAG_SEM_CHIP,
    FLAG_SEM_GPS_RECENTE,
    FLAG_SEM_PLACA,
    FLAG_TELEFONE_CLIENTE_DUPLICADO,
    FLAG_TELEFONE_DUPLICADO,
    FLAG_VEICULO_DESATIVADO,
)
from src.cruzamentos import cruzar_completo
from src.cruzamentos import listar_chips_sem_dispositivo
from src.exportacao import para_csv_bytes, para_excel_bytes
from src.leitura_pdf import (
    ler_pdf_chips,
    ler_pdf_dispositivos,
    ler_pdf_usuarios,
    ler_pdf_veiculos,
)
from src.regras_auditoria import aplicar_todas_regras

logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Configuração da página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Auditoria de Cobrança M2M",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Estado da sessão
# ---------------------------------------------------------------------------
def _init_state() -> None:
    defaults: dict = {
        "df_dispositivos": None,
        "df_veiculos": None,
        "df_chips": None,
        "df_chips_principal": None,
        "df_chips_m2data": None,
        "df_usuarios": None,
        "df_auditoria": None,
        "df_dispositivos_sem_chip": None,
        "df_chips_sem_dispositivo": None,
        "df_duplicidades": None,
        "df_status": None,
    }
    for chave, valor in defaults.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor

_init_state()


def _colunas_presentes(df: pd.DataFrame, colunas: list[str]) -> list[str]:
    return [c for c in colunas if c in df.columns]


def _combinar_bases(*dfs: pd.DataFrame | None) -> pd.DataFrame:
    """Combina múltiplas bases já normalizadas, removendo linhas idênticas."""
    validos = [df for df in dfs if df is not None and not df.empty]
    if not validos:
        return pd.DataFrame()
    combinado = pd.concat(validos, ignore_index=True)
    return combinado.drop_duplicates().reset_index(drop=True)


def _serie_str(df: pd.DataFrame, coluna: str) -> pd.Series:
    if coluna not in df.columns:
        return pd.Series([""] * len(df), index=df.index)
    return df[coluna].astype(str).str.strip()


def _calcular_utilidade(df_auditoria: pd.DataFrame) -> pd.DataFrame:
    """Classifica itens úteis/inúteis para visão operacional e financeira."""
    df = df_auditoria.copy()
    risco_ok = _serie_str(df, COL_AUD_RISCO_COBRANCA).eq("BAIXO")
    status_ok = _serie_str(df, COL_AUD_STATUS_DISPOSITIVO).eq("ATIVO")
    df["item_util"] = risco_ok & status_ok
    df["item_inutil"] = ~df["item_util"]
    return df


def _valor_unitario_efetivo(
    modo: str,
    valor_medio: float,
    quantidade_ref: float,
    valor_total_ref: float,
) -> float:
    """Calcula valor unitário efetivo conforme método escolhido no painel."""
    if modo == "Valor e quantidade de itens" and quantidade_ref > 0:
        return float(valor_total_ref or 0) / float(quantidade_ref)
    return float(valor_medio or 0)


def _calcular_sobreposicao_chips(
    df_chips_principal: pd.DataFrame | None,
    df_chips_m2data: pd.DataFrame | None,
) -> pd.DataFrame:
    """Identifica chips possivelmente cobrados por ambos os prestadores."""
    if df_chips_principal is None or df_chips_principal.empty:
        return pd.DataFrame()
    if df_chips_m2data is None or df_chips_m2data.empty:
        return pd.DataFrame()

    p = df_chips_principal.copy()
    m = df_chips_m2data.copy()

    p["_k_iccid"] = _serie_str(p, "iccid")
    p["_k_tel"] = _serie_str(p, "telefone")
    m["_k_iccid"] = _serie_str(m, "iccid")
    m["_k_tel"] = _serie_str(m, "telefone")

    set_piccid = {v for v in p["_k_iccid"].tolist() if v}
    set_ptel = {v for v in p["_k_tel"].tolist() if v}

    mask = (
        (m["_k_iccid"].ne("") & m["_k_iccid"].isin(set_piccid))
        | (m["_k_tel"].ne("") & m["_k_tel"].isin(set_ptel))
    )

    sobrepostos = m[mask].copy()
    cols_base = _colunas_presentes(sobrepostos, ["iccid", "telefone", "operadora", "empresa", "nome_dispositivo", "imei"])
    if cols_base:
        sobrepostos = sobrepostos[cols_base + [c for c in sobrepostos.columns if c not in cols_base]]
    return sobrepostos.drop(columns=[c for c in sobrepostos.columns if c.startswith("_k_")], errors="ignore").reset_index(drop=True)


def _calcular_resumo_financeiro(
    df_auditoria: pd.DataFrame,
    df_chips_m2data: pd.DataFrame | None,
    valor_unit_principal: float,
    valor_unit_m2data: float,
) -> dict:
    """Calcula totais úteis/inúteis e valores estimados de cobrança real."""
    df = _calcular_utilidade(df_auditoria)

    sof_total = len(df)
    sof_uteis = int(df["item_util"].sum()) if "item_util" in df.columns else 0
    sof_inuteis = sof_total - sof_uteis

    sof_valor_atual = sof_total * float(valor_unit_principal or 0)
    sof_valor_real = sof_uteis * float(valor_unit_principal or 0)
    sof_economia = sof_valor_atual - sof_valor_real

    m2_total = 0
    m2_uteis = 0
    m2_inuteis = 0
    m2_valor_atual = 0.0
    m2_valor_real = 0.0
    m2_economia = 0.0

    m2_preco_medio = float(valor_unit_m2data or 0)

    if df_chips_m2data is not None and not df_chips_m2data.empty:
        m2_total = len(df_chips_m2data)

        uteis = df[df.get("item_util", False)] if "item_util" in df.columns else pd.DataFrame()
        set_iccid_uteis = set(_serie_str(uteis, "iccid"))
        set_tel_uteis = set(_serie_str(uteis, "telefone_chip"))

        iccid_m2 = _serie_str(df_chips_m2data, "iccid")
        tel_m2 = _serie_str(df_chips_m2data, "telefone")

        mask_util_m2 = (
            (iccid_m2.ne("") & iccid_m2.isin(set_iccid_uteis))
            | (tel_m2.ne("") & tel_m2.isin(set_tel_uteis))
        )

        m2_uteis = int(mask_util_m2.sum())
        m2_inuteis = m2_total - m2_uteis

        m2_valor_atual = m2_total * m2_preco_medio
        m2_valor_real = m2_uteis * m2_preco_medio
        m2_economia = m2_valor_atual - m2_valor_real

    return {
        "df_utilidade": df,
        "sof_total": sof_total,
        "sof_uteis": sof_uteis,
        "sof_inuteis": sof_inuteis,
        "sof_valor_atual": sof_valor_atual,
        "sof_valor_real": sof_valor_real,
        "sof_economia": sof_economia,
        "m2_total": m2_total,
        "m2_uteis": m2_uteis,
        "m2_inuteis": m2_inuteis,
        "m2_preco_medio": m2_preco_medio,
        "m2_valor_atual": m2_valor_atual,
        "m2_valor_real": m2_valor_real,
        "m2_economia": m2_economia,
    }


def _injetar_tema_bi() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap');

        :root {
            --bg: #0b1020;
            --panel: #121a2e;
            --panel-2: #1a2340;
            --text: #e8ecf8;
            --muted: #9da9c7;
            --line: #273353;
            --good: #22c55e;
            --warn: #f59e0b;
            --danger: #ef4444;
            --info: #38bdf8;
        }

        .stApp {
            background:
                radial-gradient(circle at 8% 12%, rgba(56,189,248,.18), transparent 35%),
                radial-gradient(circle at 90% 8%, rgba(34,197,94,.12), transparent 28%),
                linear-gradient(145deg, #080d1a 0%, #0c1324 40%, #0b1020 100%);
            color: var(--text);
            font-family: 'Manrope', sans-serif;
        }

        h1, h2, h3 {
            font-family: 'Space Grotesk', sans-serif;
            letter-spacing: .01em;
        }

        .block-container {
            padding-top: 1.4rem;
            padding-bottom: 1.4rem;
        }

        .bi-hero {
            padding: 1.2rem 1.4rem;
            border: 1px solid var(--line);
            border-radius: 18px;
            background: linear-gradient(140deg, rgba(18,26,46,.95), rgba(10,16,30,.95));
            box-shadow: 0 14px 40px rgba(0,0,0,.35);
            margin-bottom: 1rem;
        }

        .bi-eyebrow {
            display: inline-flex;
            align-items: center;
            gap: .45rem;
            font-size: .72rem;
            color: #c8d4f5;
            text-transform: uppercase;
            font-weight: 700;
            letter-spacing: .08em;
            border: 1px solid rgba(56,189,248,.4);
            border-radius: 999px;
            padding: .25rem .65rem;
            background: rgba(56,189,248,.08);
            margin-bottom: .75rem;
        }

        .bi-hero h1 {
            margin: 0;
            font-size: 1.9rem;
            color: var(--text);
        }

        .bi-hero p {
            margin: .35rem 0 0;
            color: var(--muted);
            font-size: .97rem;
        }

        .bi-section-title {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 1rem;
            letter-spacing: .04em;
            color: #bfd4ff;
            text-transform: uppercase;
            margin: .2rem 0 .7rem;
        }

        .bi-card {
            border: 1px solid var(--line);
            border-radius: 16px;
            background: linear-gradient(170deg, rgba(23,33,58,.95), rgba(12,18,34,.95));
            padding: .85rem .95rem;
            min-height: 132px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.03), 0 10px 24px rgba(0,0,0,.28);
        }

        .bi-card-head {
            display: flex;
            align-items: center;
            gap: .55rem;
            margin-bottom: .65rem;
            color: #d8e4ff;
            font-weight: 700;
            font-size: .84rem;
        }

        .bi-icon {
            width: 26px;
            height: 26px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 8px;
            border: 1px solid rgba(255,255,255,.15);
            background: rgba(255,255,255,.03);
        }

        .bi-value {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 1.72rem;
            font-weight: 700;
            color: #f4f7ff;
            line-height: 1.1;
        }

        .bi-sub {
            margin-top: .35rem;
            color: var(--muted);
            font-size: .79rem;
        }

        .bi-card-danger { border-color: rgba(239,68,68,.45); }
        .bi-card-warning { border-color: rgba(245,158,11,.45); }
        .bi-card-info { border-color: rgba(56,189,248,.45); }
        .bi-card-success { border-color: rgba(34,197,94,.45); }

        .stTabs [data-baseweb="tab-list"] {
            gap: .4rem;
            background: rgba(15,23,42,.55);
            border: 1px solid var(--line);
            border-radius: 10px;
            padding: .25rem;
        }

        .stTabs [data-baseweb="tab"] {
            border-radius: 8px;
            padding: .45rem .75rem;
        }

        .stDataFrame {
            border: 1px solid var(--line);
            border-radius: 12px;
            overflow: hidden;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _icone_svg(nome: str) -> str:
    icones = {
        "devices": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="12" rx="2"/><path d="M8 20h8"/><path d="M12 17v3"/></svg>',
        "alert": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2 20h20L12 3z"/><path d="M12 9v5"/><path d="M12 18h.01"/></svg>',
        "chip": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="7" width="10" height="10" rx="1.5"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 15h3M1 9h3M1 15h3"/></svg>',
        "link": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 1 0-7l1.5-1.5a5 5 0 0 1 7 7L17 13"/><path d="M14 11a5 5 0 0 1 0 7L12.5 19.5a5 5 0 0 1-7-7L7 11"/></svg>',
        "unlink": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M16 7a5 5 0 0 1 0 7l-1 1"/><path d="M8 17a5 5 0 0 1 0-7l1-1"/><path d="M4 4l16 16"/></svg>',
        "power": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v10"/><path d="M6.2 6.2a8 8 0 1 0 11.3 0"/></svg>',
        "gps": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.2"/></svg>',
        "imei": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 9h8M8 13h5M8 17h8"/></svg>',
        "sim": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7 2h7l5 5v13a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/><path d="M9 14h6M9 10h6M9 18h4"/></svg>',
    }
    return icones.get(nome, icones["devices"])


def _card_kpi(titulo: str, valor: str, subtitulo: str, icone: str, tom: str = "info") -> None:
    st.markdown(
        f"""
        <div class="bi-card bi-card-{tom}">
            <div class="bi-card-head">
                <span class="bi-icon">{_icone_svg(icone)}</span>
                <span>{titulo}</span>
            </div>
            <div class="bi-value">{valor}</div>
            <div class="bi-sub">{subtitulo}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _ordenar_para_triagem(df: pd.DataFrame) -> pd.DataFrame:
    """Ordena registros por prioridade de auditoria para facilitar triagem."""
    if df.empty:
        return df

    trabalho = df.copy()

    if COL_AUD_RISCO_COBRANCA in trabalho.columns:
        trabalho["_score_risco_cobranca"] = trabalho[COL_AUD_RISCO_COBRANCA].map(
            {"ALTO": 1, "BAIXO": 0}
        ).fillna(0)
    else:
        trabalho["_score_risco_cobranca"] = 0

    if COL_AUD_RISCO_CADASTRO in trabalho.columns:
        trabalho["_score_risco_cadastro"] = trabalho[COL_AUD_RISCO_CADASTRO].map(
            {"ALTO": 1, "BAIXO": 0}
        ).fillna(0)
    else:
        trabalho["_score_risco_cadastro"] = 0

    flags_presentes = [f for f in FLAGS_AUDITORIA if f in trabalho.columns]
    if flags_presentes:
        trabalho["_qtd_flags"] = trabalho[flags_presentes].fillna(False).astype(bool).sum(axis=1)
    else:
        trabalho["_qtd_flags"] = 0

    colunas_sort = [
        "_score_risco_cobranca",
        "_qtd_flags",
        "_score_risco_cadastro",
    ]
    ascending = [False, False, False]

    if "suspeito" in trabalho.columns:
        colunas_sort.append("suspeito")
        ascending.append(False)

    if COL_AUD_STATUS_DISPOSITIVO in trabalho.columns:
        trabalho["_score_status"] = trabalho[COL_AUD_STATUS_DISPOSITIVO].map(
            {"INATIVO": 1, "ATIVO": 0}
        ).fillna(0)
        colunas_sort.append("_score_status")
        ascending.append(False)

    trabalho = trabalho.sort_values(by=colunas_sort, ascending=ascending, kind="mergesort")
    return trabalho.drop(columns=[c for c in trabalho.columns if c.startswith("_score_") or c == "_qtd_flags"])


_injetar_tema_bi()

# ---------------------------------------------------------------------------
# Helpers de query params compatíveis com versões do Streamlit
# ---------------------------------------------------------------------------

def _get_query_params() -> dict[str, list[str]]:
    for name in ("experimental_get_query_params", "get_query_params", "experimental_get_query_params"):
        fn = getattr(st, name, None)
        if callable(fn):
            return fn()
    return {}


def _set_query_params(**params: str) -> None:
    fn = getattr(st, "experimental_set_query_params", None) or getattr(st, "set_query_params", None)
    if callable(fn):
        fn(**params)


# ---------------------------------------------------------------------------
# Acesso restrito por senha
# ---------------------------------------------------------------------------
_SENHA_HASH = hashlib.sha256(b"@vrj2327").hexdigest()

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    col = st.columns([1, 2, 1])[1]
    with col:
        st.markdown("<br><br>", unsafe_allow_html=True)
        senha_input = st.text_input("Senha de acesso", type="password", key="campo_senha")
        if st.button("Entrar", type="primary", key="btn_entrar", use_container_width=True):
            if hashlib.sha256(senha_input.encode()).hexdigest() == _SENHA_HASH:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar — Upload de relatórios
# ---------------------------------------------------------------------------
st.sidebar.title("📂 Importar Relatórios")

with st.sidebar.expander("ℹ️ Instruções", expanded=False):
    st.markdown(
        """
        Faça upload dos relatórios exportados em PDF, CSV ou HTML.

        Você pode enviar arquivos da base principal e também da **M2Data**.
        O sistema consolida as duas fontes automaticamente.

        - **Dispositivos** *(obrigatório)*
        - **Veículos** *(recomendado)*
        - **Chips M2M** *(recomendado)*
        - **Usuários** *(opcional)*

        O sistema extrai as tabelas automaticamente, normaliza os dados e
        aplica as regras de auditoria.
        """
    )

arquivo_disp = st.sidebar.file_uploader(
    "📡 Relatório de Dispositivos (PDF/CSV/HTML)", type=["pdf", "csv", "html", "htm"], key="up_disp"
)
arquivo_veic = st.sidebar.file_uploader(
    "🚗 Relatório de Veículos (PDF/CSV/HTML)", type=["pdf", "csv", "html", "htm"], key="up_veic"
)
arquivo_chips = st.sidebar.file_uploader(
    "📶 Relatório de Chips M2M (PDF/CSV/HTML)", type=["pdf", "csv", "html", "htm"], key="up_chips"
)
arquivo_usuarios = st.sidebar.file_uploader(
    "👤 Relatório de Usuários (PDF/CSV/HTML — opcional)", type=["pdf", "csv", "html", "htm"], key="up_usuarios"
)

with st.sidebar.expander("🏢 Arquivos da prestadora M2Data", expanded=False):
    arquivo_chips_m2data = st.file_uploader(
        "📶 Chips M2Data (PDF/CSV/HTML)",
        type=["pdf", "csv", "html", "htm"],
        key="up_chips_m2data",
    )

with st.sidebar.expander("💰 Parâmetros financeiros (opcional)", expanded=False):
    st.markdown("**Base Principal**")
    modo_fin_principal = st.radio(
        "Método de valor (Base Principal)",
        options=["Valor médio por item", "Valor e quantidade de itens"],
        horizontal=True,
        key="modo_fin_principal",
    )
    valor_unit_principal = st.number_input(
        "Base Principal - Valor médio por item",
        min_value=0.0,
        value=0.0,
        step=0.01,
        format="%.2f",
        key="valor_unit_principal",
        disabled=modo_fin_principal != "Valor médio por item",
    )
    qtd_principal_ref = st.number_input(
        "Base Principal - Quantidade de itens (referência)",
        min_value=0.0,
        value=0.0,
        step=1.0,
        format="%.0f",
        key="qtd_principal_ref",
        disabled=modo_fin_principal != "Valor e quantidade de itens",
    )
    valor_total_principal_ref = st.number_input(
        "Base Principal - Valor total (referência)",
        min_value=0.0,
        value=0.0,
        step=0.01,
        format="%.2f",
        key="valor_total_principal_ref",
        disabled=modo_fin_principal != "Valor e quantidade de itens",
    )

    st.markdown("**M2Data**")
    modo_fin_m2data = st.radio(
        "Método de valor (M2Data)",
        options=["Valor médio por item", "Valor e quantidade de itens"],
        horizontal=True,
        key="modo_fin_m2data",
    )
    valor_unit_m2data = st.number_input(
        "M2Data - Valor médio por item",
        min_value=0.0,
        value=0.0,
        step=0.01,
        format="%.2f",
        key="valor_unit_m2data",
        disabled=modo_fin_m2data != "Valor médio por item",
    )
    qtd_m2_ref = st.number_input(
        "M2Data - Quantidade de itens (referência)",
        min_value=0.0,
        value=0.0,
        step=1.0,
        format="%.0f",
        key="qtd_m2_ref",
        disabled=modo_fin_m2data != "Valor e quantidade de itens",
    )
    valor_total_m2_ref = st.number_input(
        "M2Data - Valor total (referência)",
        min_value=0.0,
        value=0.0,
        step=0.01,
        format="%.2f",
        key="valor_total_m2_ref",
        disabled=modo_fin_m2data != "Valor e quantidade de itens",
    )

st.sidebar.divider()
dias_gps = st.sidebar.slider(
    "⏱️ Dias sem GPS para considerar inativo",
    min_value=1,
    max_value=365,
    value=DIAS_SEM_GPS,
    step=1,
)

processar = st.sidebar.button("🚀 Processar Auditoria", type="primary", width="stretch")

# ---------------------------------------------------------------------------
# Processamento
# ---------------------------------------------------------------------------
if processar:
    if arquivo_disp is None:
        st.sidebar.error("⚠️ Envie o relatório de dispositivos da Base Principal (obrigatório).")
    else:
        with st.spinner("Lendo e processando os relatórios…"):
            try:
                df_disp = ler_pdf_dispositivos(arquivo_disp)
                st.session_state["df_dispositivos"] = df_disp

                df_veic = None
                if arquivo_veic:
                    df_veic = ler_pdf_veiculos(arquivo_veic)
                    st.session_state["df_veiculos"] = df_veic

                df_chips = None
                df_chips_m2 = None
                if arquivo_chips or arquivo_chips_m2data:
                    df_chips_base = ler_pdf_chips(arquivo_chips) if arquivo_chips else None
                    df_chips_m2 = ler_pdf_chips(arquivo_chips_m2data) if arquivo_chips_m2data else None
                    df_chips = _combinar_bases(df_chips_base, df_chips_m2)
                    st.session_state["df_chips"] = df_chips
                    st.session_state["df_chips_principal"] = df_chips_base if df_chips_base is not None else pd.DataFrame()
                    st.session_state["df_chips_m2data"] = df_chips_m2
                else:
                    st.session_state["df_chips_principal"] = pd.DataFrame()
                    st.session_state["df_chips_m2data"] = pd.DataFrame()

                df_usuarios = None
                if arquivo_usuarios:
                    df_usuarios = ler_pdf_usuarios(arquivo_usuarios)
                    st.session_state["df_usuarios"] = df_usuarios

                df_cruzado = cruzar_completo(df_disp, df_veic, df_chips)
                df_auditoria = aplicar_todas_regras(
                    df_cruzado,
                    dias_sem_gps=dias_gps,
                    data_referencia=datetime.now(tz=timezone.utc),
                )

                st.session_state["df_dispositivos_sem_chip"] = (
                    df_auditoria[df_auditoria[FLAG_SEM_CHIP]].copy()
                    if FLAG_SEM_CHIP in df_auditoria.columns
                    else pd.DataFrame()
                )
                st.session_state["df_chips_sem_dispositivo"] = (
                    listar_chips_sem_dispositivo(df_disp, df_chips)
                    if df_chips is not None
                    else pd.DataFrame()
                )

                flags_dup = [
                    f
                    for f in [
                        FLAG_IMEI_DUPLICADO,
                        FLAG_ICCID_DUPLICADO,
                        FLAG_TELEFONE_DUPLICADO,
                        FLAG_PLACA_DUPLICADA,
                    ]
                    if f in df_auditoria.columns
                ]
                st.session_state["df_duplicidades"] = (
                    df_auditoria[df_auditoria[flags_dup].any(axis=1)].copy()
                    if flags_dup
                    else pd.DataFrame()
                )

                if COL_AUD_STATUS_DISPOSITIVO in df_auditoria.columns:
                    st.session_state["df_status"] = df_auditoria[
                        [COL_AUD_STATUS_DISPOSITIVO] + [c for c in ["nome_dispositivo", "imei", "iccid", "placa"] if c in df_auditoria.columns]
                    ].copy()
                else:
                    st.session_state["df_status"] = pd.DataFrame()

                st.session_state["df_auditoria"] = df_auditoria
                st.success(
                    f"✅ Auditoria concluída: **{len(df_auditoria):,}** dispositivos analisados, "
                    f"**{df_auditoria['suspeito'].sum():,}** com pendências."
                )
            except Exception as exc:
                st.error(f"❌ Erro durante o processamento: {exc}")
                logging.exception("Erro no processamento dos relatórios.")

# ---------------------------------------------------------------------------
# Conteúdo principal
# ---------------------------------------------------------------------------
st.markdown(
    """
    <section class="bi-hero">
        <div class="bi-eyebrow">Painel BI de Auditoria Tecnica</div>
        <h1>Auditoria de Cobranca M2M</h1>
        <p>Visualizacao profissional para identificar divergencias de cobranca, vinculos tecnicos e inconsistencias cadastrais.</p>
    </section>
    """,
    unsafe_allow_html=True,
)

df_auditoria: pd.DataFrame | None = st.session_state.get("df_auditoria")

if df_auditoria is None:
    st.info(
        "👈 Faça upload dos relatórios na barra lateral e clique em "
        "**Processar Auditoria** para começar."
    )

    # Mostra estrutura esperada dos relatórios
    with st.expander("📋 Estrutura esperada dos relatórios", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Relatório de Dispositivos")
            st.markdown(
                """
                - Nome do dispositivo
                - IMEI
                - Estado de ativação
                - ICCID (nº série do chip)
                - Telefone do chip (M2M)
                - Telefone do cliente (usuário)
                - Última conexão GPS / Data GPS
                - Placa / Chassi
                - Usuário
                """
            )
            st.subheader("Relatório de Veículos")
            st.markdown(
                """
                - Placa / Chassi
                - Marca / Modelo / Ano
                - Data de desativação
                - Usuário / Dispositivo / IMEI
                """
            )
        with col2:
            st.subheader("Relatório de Chips M2M")
            st.markdown(
                """
                - ICCID / IMSI
                - Telefone
                - Operadora / Provedor
                - Dispositivo / IMEI
                - Empresa
                """
            )
            st.subheader("Critérios de Auditoria")
            st.markdown(
                f"""
                - 🔴 Dispositivo **inativo**
                - 🔴 Sem **placa** vinculada
                - 🔴 Sem **GPS** nos últimos {dias_gps} dias
                - 🔴 Sem **chip** (ICCID ausente)
                - 🟠 **IMEI duplicado**
                - 🟠 **ICCID duplicado**
                - 🟠 **Telefone duplicado**
                - 🟠 **Placa duplicada**
                - 🟠 Veículo **desativado**
                - ℹ️ **Telefone cliente duplicado** *(risco cadastral)*
                """
            )
    st.stop()

valor_unit_principal_efetivo = _valor_unitario_efetivo(
    st.session_state.get("modo_fin_principal", "Valor médio por item"),
    st.session_state.get("valor_unit_principal", 0.0),
    st.session_state.get("qtd_principal_ref", 0.0),
    st.session_state.get("valor_total_principal_ref", 0.0),
)

valor_unit_m2_efetivo = _valor_unitario_efetivo(
    st.session_state.get("modo_fin_m2data", "Valor médio por item"),
    st.session_state.get("valor_unit_m2data", 0.0),
    st.session_state.get("qtd_m2_ref", 0.0),
    st.session_state.get("valor_total_m2_ref", 0.0),
)

resumo_fin = _calcular_resumo_financeiro(
    df_auditoria,
    st.session_state.get("df_chips_m2data"),
    valor_unit_principal_efetivo,
    valor_unit_m2_efetivo,
)

df_chips_sobrepostos = _calcular_sobreposicao_chips(
    st.session_state.get("df_chips_principal"),
    st.session_state.get("df_chips_m2data"),
)
df_auditoria = resumo_fin["df_utilidade"]

# ---------------------------------------------------------------------------
# Métricas resumo
# ---------------------------------------------------------------------------
total = len(df_auditoria)
suspeitos = int(df_auditoria["suspeito"].sum())
perc_suspeito = (suspeitos / total) * 100 if total else 0

df_chips_raw = st.session_state.get("df_chips")
df_chips_sem_dispositivo = st.session_state.get("df_chips_sem_dispositivo")
chips_total = len(df_chips_raw) if df_chips_raw is not None else 0
chips_sem_disp_total = len(df_chips_sem_dispositivo) if df_chips_sem_dispositivo is not None else 0
chips_vinculados_total = max(chips_total - chips_sem_disp_total, 0)

contagem_flag = lambda f: int(df_auditoria[f].sum()) if f in df_auditoria.columns else 0

st.markdown('<div class="bi-section-title">Pulse BI</div>', unsafe_allow_html=True)

linha_1 = st.columns(5)
with linha_1[0]:
    _card_kpi("Dispositivos", f"{total:,}", "Base analisada", "devices", "info")
with linha_1[1]:
    _card_kpi("Risco de cobranca", f"{suspeitos:,}", f"{perc_suspeito:.1f}% da base", "alert", "danger")
with linha_1[2]:
    _card_kpi("Chips totais", f"{chips_total:,}", "Inventario importado", "chip", "info")
with linha_1[3]:
    _card_kpi("Chips vinculados", f"{chips_vinculados_total:,}", "Com dispositivo associado", "link", "success")
with linha_1[4]:
    _card_kpi("Sem dispositivo", f"{chips_sem_disp_total:,}", "Chips em divergencia", "unlink", "warning")

linha_2 = st.columns(5)
with linha_2[0]:
    _card_kpi("Inativos", f"{contagem_flag(FLAG_DISPOSITIVO_INATIVO):,}", "Status operacional", "power", "danger")
with linha_2[1]:
    _card_kpi("Sem chip", f"{contagem_flag(FLAG_SEM_CHIP):,}", "ICCID vazio ou nao encontrado", "sim", "warning")
with linha_2[2]:
    _card_kpi("Sem GPS", f"{contagem_flag(FLAG_SEM_GPS_RECENTE):,}", "Sem conexao recente", "gps", "warning")
with linha_2[3]:
    _card_kpi("IMEI duplicado", f"{contagem_flag(FLAG_IMEI_DUPLICADO):,}", "Conflito tecnico", "imei", "warning")
with linha_2[4]:
    _card_kpi("ICCID duplicado", f"{contagem_flag(FLAG_ICCID_DUPLICADO):,}", "Conflito de chip", "sim", "warning")

st.divider()

# ---------------------------------------------------------------------------
# Visão financeira e utilidade
# ---------------------------------------------------------------------------
st.subheader("💼 Cobrança Real e Itens Úteis")

f1, f2, f3 = st.columns(3)
f1.metric("Base Principal - Itens úteis", f"{resumo_fin['sof_uteis']:,}")
f2.metric("Base Principal - Itens inúteis", f"{resumo_fin['sof_inuteis']:,}")
f3.metric("Base Principal - Valor real", f"R$ {resumo_fin['sof_valor_real']:,.2f}")

f4, f5, f6 = st.columns(3)
f4.metric("M2Data - Chips úteis", f"{resumo_fin['m2_uteis']:,}")
f5.metric("M2Data - Chips inúteis", f"{resumo_fin['m2_inuteis']:,}")
f6.metric("M2Data - Valor real", f"R$ {resumo_fin['m2_valor_real']:,.2f}")

st.caption(
    f"Preço unitário efetivo | Base Principal: R$ {valor_unit_principal_efetivo:,.4f} | "
    f"M2Data: R$ {valor_unit_m2_efetivo:,.4f}"
)

f7, f8 = st.columns(2)
f7.metric("Economia potencial Base Principal", f"R$ {resumo_fin['sof_economia']:,.2f}")
f8.metric("Economia potencial M2Data", f"R$ {resumo_fin['m2_economia']:,.2f}")

st.metric("Chips possivelmente cobrados por ambos os prestadores", f"{len(df_chips_sobrepostos):,}")

if len(df_chips_sobrepostos) > 0:
    valor_sobreposto_principal = len(df_chips_sobrepostos) * valor_unit_principal_efetivo
    valor_sobreposto_m2 = len(df_chips_sobrepostos) * valor_unit_m2_efetivo
    valor_sobreposto_total = valor_sobreposto_principal + valor_sobreposto_m2
    s1, s2, s3 = st.columns(3)
    s1.metric("Sobreposição potencial - Base Principal", f"R$ {valor_sobreposto_principal:,.2f}")
    s2.metric("Sobreposição potencial - M2Data", f"R$ {valor_sobreposto_m2:,.2f}")
    s3.metric("Sobreposição potencial total", f"R$ {valor_sobreposto_total:,.2f}")

with st.expander("🔁 Chips cobrados pela Base Principal e pela M2Data", expanded=False):
    if not df_chips_sobrepostos.empty:
        st.dataframe(df_chips_sobrepostos, width="stretch", height=280)
    else:
        st.success("Nenhuma sobreposição de cobrança de chips identificada entre os prestadores.")

with st.expander("📉 Itens classificados como inúteis", expanded=False):
    df_inuteis = df_auditoria[df_auditoria["item_inutil"]].copy() if "item_inutil" in df_auditoria.columns else pd.DataFrame()
    if not df_inuteis.empty:
        cols_inuteis = _colunas_presentes(
            df_inuteis,
            [
                "nome_dispositivo",
                "placa",
                "imei",
                "iccid",
                "telefone_chip",
                COL_AUD_STATUS_DISPOSITIVO,
                COL_AUD_RISCO_COBRANCA,
                COL_AUD_MOTIVOS_COBRANCA,
            ],
        )
        if cols_inuteis:
            df_inuteis = df_inuteis[cols_inuteis + [c for c in df_inuteis.columns if c not in cols_inuteis]]
        st.dataframe(_ordenar_para_triagem(df_inuteis), width="stretch", height=320)
    else:
        st.success("Nenhum item inútil identificado pelos critérios atuais.")

st.divider()

# ---------------------------------------------------------------------------
# Filtros interativos
# ---------------------------------------------------------------------------
st.subheader("🔎 Filtros")

col_f1, col_f2, col_f3, col_f4 = st.columns(4)

with col_f1:
    apenas_suspeitos = st.checkbox("Exibir apenas suspeitos", value=False)

flags_disponiveis = [f for f in FLAGS_AUDITORIA if f in df_auditoria.columns]
nomes_flags = {
    FLAG_DISPOSITIVO_INATIVO: "Dispositivo inativo",
    FLAG_SEM_PLACA: "Sem placa",
    FLAG_SEM_GPS_RECENTE: "Sem GPS recente",
    FLAG_SEM_CHIP: "Sem chip",
    FLAG_IMEI_DUPLICADO: "IMEI duplicado",
    FLAG_ICCID_DUPLICADO: "ICCID duplicado",
    FLAG_TELEFONE_DUPLICADO: "Telefone duplicado",
    FLAG_TELEFONE_CLIENTE_DUPLICADO: "Telefone cliente duplicado (cadastral)",
    FLAG_PLACA_DUPLICADA: "Placa duplicada",
    FLAG_VEICULO_DESATIVADO: "Veículo desativado",
}

with col_f2:
    flags_selecionadas = st.multiselect(
        "Filtrar por critério",
        options=flags_disponiveis,
        format_func=lambda f: nomes_flags.get(f, f),
        default=[],
    )

with col_f3:
    modo_ordenacao = st.selectbox(
        "Ordenar por",
        options=["Prioridade de erro", "Placa", "IMEI", "ICCID"],
        index=0,
    )

with col_f4:
    mostrar_so_alto_risco = st.checkbox("Somente risco cobrança ALTO", value=False)

# Aplica filtros
df_exibir = df_auditoria.copy()
if apenas_suspeitos:
    df_exibir = df_exibir[df_exibir["suspeito"]]
for flag in flags_selecionadas:
    df_exibir = df_exibir[df_exibir[flag]]

if mostrar_so_alto_risco and COL_AUD_RISCO_COBRANCA in df_exibir.columns:
    df_exibir = df_exibir[df_exibir[COL_AUD_RISCO_COBRANCA] == "ALTO"]

if modo_ordenacao == "Prioridade de erro":
    df_exibir = _ordenar_para_triagem(df_exibir)
elif modo_ordenacao == "Placa" and "placa" in df_exibir.columns:
    df_exibir = df_exibir.sort_values(by=["placa"], kind="mergesort")
elif modo_ordenacao == "IMEI" and "imei" in df_exibir.columns:
    df_exibir = df_exibir.sort_values(by=["imei"], kind="mergesort")
elif modo_ordenacao == "ICCID" and "iccid" in df_exibir.columns:
    df_exibir = df_exibir.sort_values(by=["iccid"], kind="mergesort")

st.caption(f"Exibindo **{len(df_exibir):,}** de **{total:,}** registros.")

# ---------------------------------------------------------------------------
# Tabela de resultados
# ---------------------------------------------------------------------------
st.subheader("📊 Resultados da Auditoria")

# Coluna 'suspeito' e flags como primeiras colunas de destaque
colunas_flags = ["suspeito"] + [f for f in FLAGS_AUDITORIA if f in df_exibir.columns]
colunas_dados = [c for c in df_exibir.columns if c not in colunas_flags]

colunas_principais = [
    "placa",
    "imei",
    "iccid",
    "telefone_chip",
    "operadora",
    COL_AUD_STATUS_DISPOSITIVO,
    "ultima_conexao_gps",
    "telefone_cliente",
    "usuario",
    COL_AUD_RISCO_COBRANCA,
    COL_AUD_MOTIVOS_COBRANCA,
    COL_AUD_RISCO_CADASTRO,
    COL_AUD_MOTIVOS_CADASTRO,
]
colunas_principais_presentes = [c for c in colunas_principais if c in df_exibir.columns]
restantes = [c for c in (colunas_flags + colunas_dados) if c not in colunas_principais_presentes]
df_exibir_ordenado = df_exibir[colunas_principais_presentes + restantes]

st.dataframe(
    df_exibir_ordenado,
    width="stretch",
    height=500,
    column_config={
        "suspeito": st.column_config.CheckboxColumn("⚠️ Suspeito"),
        FLAG_DISPOSITIVO_INATIVO: st.column_config.CheckboxColumn("Inativo"),
        FLAG_SEM_PLACA: st.column_config.CheckboxColumn("Sem Placa"),
        FLAG_SEM_GPS_RECENTE: st.column_config.CheckboxColumn("Sem GPS"),
        FLAG_SEM_CHIP: st.column_config.CheckboxColumn("Sem Chip"),
        FLAG_IMEI_DUPLICADO: st.column_config.CheckboxColumn("IMEI Dup."),
        FLAG_ICCID_DUPLICADO: st.column_config.CheckboxColumn("ICCID Dup."),
        FLAG_TELEFONE_DUPLICADO: st.column_config.CheckboxColumn("Fone Dup."),
        FLAG_TELEFONE_CLIENTE_DUPLICADO: st.column_config.CheckboxColumn("Fone Cliente Dup."),
        FLAG_PLACA_DUPLICADA: st.column_config.CheckboxColumn("Placa Dup."),
        FLAG_VEICULO_DESATIVADO: st.column_config.CheckboxColumn("Veíc. Desativ."),
    },
)

# ---------------------------------------------------------------------------
# Exportação
# ---------------------------------------------------------------------------
st.subheader("💾 Exportar Resultados")

col_e1, col_e2 = st.columns(2)

with col_e1:
    exportar_filtrado = st.checkbox("Exportar apenas registros exibidos", value=True)

df_export = df_exibir if exportar_filtrado else df_auditoria

with col_e2:
    st.download_button(
        label="⬇️ Baixar CSV",
        data=para_csv_bytes(df_export),
        file_name="auditoria_cobranca_m2m.csv",
        mime="text/csv",
        width="stretch",
    )

col_e3, col_e4 = st.columns(2)
with col_e4:
    st.download_button(
        label="⬇️ Baixar Excel (.xlsx)",
        data=para_excel_bytes(df_export),
        file_name="auditoria_cobranca_m2m.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )

# ---------------------------------------------------------------------------
# Relatório narrativo com Ollama
# ---------------------------------------------------------------------------
st.divider()
st.subheader("🤖 Relatório Executivo com IA")

_OLLAMA_URL = "http://localhost:11434/api/generate"
_OLLAMA_MODEL = "mistral"

def _resumo_auditoria(df: "pd.DataFrame") -> str:
    """Retorna um resumo textual compacto dos achados para o prompt."""
    import json
    total = len(df)
    resumo: dict = {"total_registros": total}

    if COL_AUD_RISCO_COBRANCA in df.columns:
        freq = df[COL_AUD_RISCO_COBRANCA].value_counts().to_dict()
        resumo["risco_cobranca"] = freq
    if COL_AUD_RISCO_CADASTRO in df.columns:
        freq2 = df[COL_AUD_RISCO_CADASTRO].value_counts().to_dict()
        resumo["risco_cadastro"] = freq2
    if COL_AUD_MOTIVOS_COBRANCA in df.columns:
        motivos = df[COL_AUD_MOTIVOS_COBRANCA].dropna()
        todos = []
        for m in motivos:
            todos.extend([x.strip() for x in str(m).split(";") if x.strip()])
        from collections import Counter
        top = dict(Counter(todos).most_common(10))
        resumo["principais_motivos_cobranca"] = top
    if COL_AUD_MOTIVOS_CADASTRO in df.columns:
        motivos2 = df[COL_AUD_MOTIVOS_CADASTRO].dropna()
        todos2 = []
        for m in motivos2:
            todos2.extend([x.strip() for x in str(m).split(";") if x.strip()])
        from collections import Counter
        top2 = dict(Counter(todos2).most_common(10))
        resumo["principais_motivos_cadastro"] = top2
    if "valor_mensal" in df.columns:
        em_risco = df[df.get(COL_AUD_RISCO_COBRANCA, pd.Series(dtype=str)).isin(["alto", "médio"])]["valor_mensal"].sum() if COL_AUD_RISCO_COBRANCA in df.columns else 0
        resumo["valor_estimado_em_risco_R$"] = round(float(em_risco), 2)

    return json.dumps(resumo, ensure_ascii=False, indent=2)

_PROMPT_TEMPLATE = """\
Você é um auditor forense de telecomunicações especializado em contratos M2M (Machine-to-Machine).
Sua missão é redigir um RELATÓRIO DE AUDITORIA EXECUTIVO em português brasileiro com linguagem direta, contundente e sem rodeios.

REGRAS OBRIGATÓRIAS:
- Seja específico: cite números, quantidades e percentuais sempre que disponíveis
- Destaque DIVERGÊNCIAS com clareza, usando frases como "IDENTIFICADO:", "DIVERGÊNCIA:", "ALERTA:"
- Não suavize problemas — se há cobrança indevida, diga explicitamente
- Linguagem acessível para gestores não técnicos (evite siglas sem explicação)
- Seja objetivo: máximo 1 parágrafo por seção, exceto "Achados" que pode ter lista

ESTRUTURA DO RELATÓRIO:

## 1. RESUMO EXECUTIVO
Síntese do que foi encontrado e o impacto financeiro. Seja direto: se há problema, comece por ele.

## 2. DIVERGÊNCIAS IDENTIFICADAS
Liste cada divergência encontrada no formato:
- **[TIPO DE RISCO]**: descrição objetiva do problema + quantidade de registros afetados

## 3. IMPACTO FINANCEIRO
Valor estimado em risco, cobranças indevidas identificadas e projeção mensal de perda.

## 4. RECOMENDAÇÕES IMEDIATAS
Ações concretas e prioritárias, numeradas por urgência. Não coloque recomendações vagas.

## 5. CONCLUSÃO
Uma frase contundente sobre a situação geral e o que precisa ser feito.

---
DADOS DA AUDITORIA:
{resumo}
"""

with st.expander("⚙️ Configuração do modelo", expanded=False):
    ollama_modelo = st.text_input("Modelo Ollama", value=_OLLAMA_MODEL, key="ollama_model")
    ollama_url = st.text_input("URL da API Ollama", value=_OLLAMA_URL, key="ollama_url")

if st.button("📝 Gerar Relatório Executivo", type="primary", key="btn_gerar_relatorio"):
    try:
        import requests as _requests
        resumo_txt = _resumo_auditoria(df_auditoria)
        prompt = _PROMPT_TEMPLATE.format(resumo=resumo_txt)

        with st.spinner("Gerando relatório... aguarde"):
            resp = _requests.post(
                st.session_state.get("ollama_url", _OLLAMA_URL),
                json={
                    "model": st.session_state.get("ollama_model", _OLLAMA_MODEL),
                    "prompt": prompt,
                    "stream": True,
                },
                stream=True,
                timeout=120,
            )
            resp.raise_for_status()

            relatorio_placeholder = st.empty()
            texto_acumulado = ""
            import json as _json
            for linha in resp.iter_lines():
                if linha:
                    chunk = _json.loads(linha)
                    texto_acumulado += chunk.get("response", "")
                    relatorio_placeholder.markdown(texto_acumulado)
                    if chunk.get("done"):
                        break

            st.session_state["ultimo_relatorio"] = texto_acumulado

        st.download_button(
            label="⬇️ Baixar Relatório (.txt)",
            data=st.session_state["ultimo_relatorio"].encode("utf-8"),
            file_name="relatorio_executivo_auditoria.txt",
            mime="text/plain",
        )

    except Exception as _e:
        st.error(f"Erro ao conectar ao Ollama: {_e}\n\nVerifique se o serviço está rodando: `ollama serve`")

# ---------------------------------------------------------------------------
# Abas para visualização dos dados brutos
# ---------------------------------------------------------------------------
st.divider()
with st.expander("📂 Dados brutos importados", expanded=False):
    aba_disp, aba_veic, aba_chips, aba_usr = st.tabs(
        ["Dispositivos", "Veículos", "Chips", "Usuários"]
    )
    with aba_disp:
        df_d = st.session_state.get("df_dispositivos")
        if df_d is not None and not df_d.empty:
            st.dataframe(df_d, width="stretch")
        else:
            st.info("Nenhum dado de dispositivos carregado.")
    with aba_veic:
        df_v = st.session_state.get("df_veiculos")
        if df_v is not None and not df_v.empty:
            st.dataframe(df_v, width="stretch")
        else:
            st.info("Nenhum dado de veículos carregado.")
    with aba_chips:
        df_c = st.session_state.get("df_chips")
        if df_c is not None and not df_c.empty:
            st.dataframe(df_c, width="stretch")
        else:
            st.info("Nenhum dado de chips carregado.")
    with aba_usr:
        df_u = st.session_state.get("df_usuarios")
        if df_u is not None and not df_u.empty:
            st.dataframe(df_u, width="stretch")
        else:
            st.info("Nenhum dado de usuários carregado (relatório opcional).")

# ---------------------------------------------------------------------------
# Divergências detalhadas
# ---------------------------------------------------------------------------
st.divider()
st.subheader("🧭 Divergências Detalhadas")

df_dispositivos_sem_chip = st.session_state.get("df_dispositivos_sem_chip")
df_chips_sem_dispositivo = st.session_state.get("df_chips_sem_dispositivo")
df_duplicidades = st.session_state.get("df_duplicidades")
df_status = st.session_state.get("df_status")
df_chips_raw = st.session_state.get("df_chips")

chips_total = len(df_chips_raw) if df_chips_raw is not None else 0
chips_sem_disp_total = len(df_chips_sem_dispositivo) if df_chips_sem_dispositivo is not None else 0
chips_vinculados_total = max(chips_total - chips_sem_disp_total, 0)

col_r1, col_r2, col_r3 = st.columns(3)
col_r1.metric("Chips totais", f"{chips_total:,}")
col_r2.metric("Chips vinculados", f"{chips_vinculados_total:,}")
col_r3.metric("Chips sem dispositivo", f"{chips_sem_disp_total:,}")

aba_div1, aba_div2, aba_div3, aba_div4 = st.tabs(
    [
        "Dispositivos sem chip",
        "Chips sem dispositivo",
        "Duplicidades",
        "Status ativo/inativo",
    ]
)

with aba_div1:
    if df_dispositivos_sem_chip is not None and not df_dispositivos_sem_chip.empty:
        df_sem_chip_view = _ordenar_para_triagem(df_dispositivos_sem_chip)
        colunas_sem_chip = _colunas_presentes(
            df_sem_chip_view,
            ["nome_dispositivo", "placa", "imei", "iccid", "telefone_chip", "operadora", COL_AUD_MOTIVOS_COBRANCA],
        )
        if colunas_sem_chip:
            df_sem_chip_view = df_sem_chip_view[colunas_sem_chip + [c for c in df_sem_chip_view.columns if c not in colunas_sem_chip]]
        st.caption(f"Total: **{len(df_dispositivos_sem_chip):,}**")
        st.dataframe(df_sem_chip_view, width="stretch", height=350)
    else:
        st.success("Nenhum dispositivo sem chip identificado.")

with aba_div2:
    if df_chips_sem_dispositivo is not None and not df_chips_sem_dispositivo.empty:
        df_chips_sem_disp_view = df_chips_sem_dispositivo.copy()
        if "iccid" in df_chips_sem_disp_view.columns:
            df_chips_sem_disp_view = df_chips_sem_disp_view.sort_values(by=["iccid"], kind="mergesort")
        colunas_chips_sem_disp = _colunas_presentes(
            df_chips_sem_disp_view,
            ["iccid", "telefone", "operadora", "nome_dispositivo", "imei", "empresa"],
        )
        if colunas_chips_sem_disp:
            df_chips_sem_disp_view = df_chips_sem_disp_view[
                colunas_chips_sem_disp + [c for c in df_chips_sem_disp_view.columns if c not in colunas_chips_sem_disp]
            ]
        st.caption(f"Total: **{len(df_chips_sem_dispositivo):,}**")
        st.dataframe(df_chips_sem_disp_view, width="stretch", height=350)
    else:
        st.success("Nenhum chip sem dispositivo identificado.")

with aba_div3:
    if df_duplicidades is not None and not df_duplicidades.empty:
        df_dup_view = _ordenar_para_triagem(df_duplicidades)
        colunas_dup = _colunas_presentes(
            df_dup_view,
            [
                "placa",
                "imei",
                "iccid",
                "telefone_chip",
                "telefone_cliente",
                FLAG_IMEI_DUPLICADO,
                FLAG_ICCID_DUPLICADO,
                FLAG_TELEFONE_DUPLICADO,
                FLAG_TELEFONE_CLIENTE_DUPLICADO,
                FLAG_PLACA_DUPLICADA,
            ],
        )
        if colunas_dup:
            df_dup_view = df_dup_view[colunas_dup + [c for c in df_dup_view.columns if c not in colunas_dup]]
        st.caption(f"Total: **{len(df_duplicidades):,}**")
        st.dataframe(df_dup_view, width="stretch", height=350)
    else:
        st.success("Nenhuma duplicidade identificada.")

with aba_div4:
    if df_status is not None and not df_status.empty and COL_AUD_STATUS_DISPOSITIVO in df_status.columns:
        resumo_status = df_status[COL_AUD_STATUS_DISPOSITIVO].value_counts(dropna=False).rename_axis("status").reset_index(name="quantidade")
        if "status" in resumo_status.columns:
            resumo_status["ordem"] = resumo_status["status"].map({"INATIVO": 0, "ATIVO": 1}).fillna(2)
            resumo_status = resumo_status.sort_values(by=["ordem", "quantidade"], ascending=[True, False]).drop(columns=["ordem"])

        df_status_view = df_status.copy()
        df_status_view["ordem"] = df_status_view[COL_AUD_STATUS_DISPOSITIVO].map({"INATIVO": 0, "ATIVO": 1}).fillna(2)
        df_status_view = df_status_view.sort_values(by=["ordem"], ascending=[True]).drop(columns=["ordem"])
        st.dataframe(resumo_status, width="stretch", height=160)
        st.dataframe(df_status_view, width="stretch", height=350)
    else:
        st.info("Status ativo/inativo indisponível para os dados atuais.")

# ---------------------------------------------------------------------------
# Rodapé
# ---------------------------------------------------------------------------
st.divider()
st.caption(
    "Auditoria de Cobrança M2M · "
    "Os dados são processados localmente e não são enviados a nenhum servidor externo."
)
