"""
Auditoria de Cobrança M2M — Dashboard Streamlit.

Execute com:
    streamlit run app.py
"""

from __future__ import annotations

import hashlib
import io
import logging
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from src.config import (
    COL_AUD_STATUS_DISPOSITIVO,
    COL_SIP_STATUS_REFERENCIA,
    COL_SIP_CONFIANCA_CRUZAMENTO,
    COL_SIP_CHAVE_CRUZAMENTO,
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
    FLAG_SIPROV_INADIMPLENTE_ATIVO_PRESTADOR,
    FLAG_SIPROV_INATIVO_ATIVO_PRESTADOR,
    FLAG_SIPROV_SEM_CADASTRO,
    FLAG_TELEFONE_CLIENTE_DUPLICADO,
    FLAG_TELEFONE_DUPLICADO,
    FLAG_VEICULO_DESATIVADO,
    PROCESSADO_DIR,
)
from src.cruzamentos import cruzar_completo
from src.cruzamentos import cruzar_com_siprov
from src.cruzamentos import listar_chips_sem_dispositivo
from src.exportacao import para_csv_bytes, para_excel_bytes, para_pdf_bytes
from src.leitura_pdf import (
    ler_pdf_chips,
    ler_pdf_dispositivos,
    ler_pdf_siprov,
    ler_pdf_usuarios,
    ler_pdf_veiculos,
)
from src.regras_auditoria import aplicar_todas_regras

logging.basicConfig(level=logging.INFO)

SNAPSHOT_PATH = Path(PROCESSADO_DIR) / "ultimo_cruzamento.pkl"
SNAPSHOT_DATAFRAMES = [
    "df_dispositivos",
    "df_veiculos",
    "df_chips",
    "df_chips_principal",
    "df_chips_m2data",
    "df_usuarios",
    "df_siprov",
    "df_auditoria",
    "df_dispositivos_sem_chip",
    "df_chips_sem_dispositivo",
    "df_duplicidades",
    "df_status",
]
SNAPSHOT_PARAMS = [
    "modo_fin_principal",
    "valor_unit_principal",
    "qtd_principal_ref",
    "valor_total_principal_ref",
    "modo_fin_m2data",
    "valor_unit_m2data",
    "qtd_m2_ref",
    "valor_total_m2_ref",
]

# ---------------------------------------------------------------------------
# Configuração da página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="A.L-Cristina's - Gestão Administrativa avançada",
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
        "df_siprov": None,
        "snapshot_carregado": False,
        "snapshot_salvo_em": None,
    }
    for chave, valor in defaults.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor

_init_state()


def _carregar_snapshot_local() -> None:
    if st.session_state.get("df_auditoria") is not None:
        return
    if not SNAPSHOT_PATH.exists():
        return

    try:
        payload = pd.read_pickle(SNAPSHOT_PATH)
    except Exception as exc:
        logging.warning("Nao foi possivel carregar snapshot local: %s", exc)
        return

    for chave in SNAPSHOT_DATAFRAMES + SNAPSHOT_PARAMS:
        if chave in payload:
            st.session_state[chave] = payload[chave]

    st.session_state["snapshot_carregado"] = True
    st.session_state["snapshot_salvo_em"] = payload.get("snapshot_salvo_em")


def _salvar_snapshot_local() -> None:
    payload = {"snapshot_salvo_em": datetime.now(tz=timezone.utc).isoformat()}

    for chave in SNAPSHOT_DATAFRAMES + SNAPSHOT_PARAMS:
        payload[chave] = st.session_state.get(chave)

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.to_pickle(payload, SNAPSHOT_PATH)
    st.session_state["snapshot_carregado"] = False
    st.session_state["snapshot_salvo_em"] = payload["snapshot_salvo_em"]


_carregar_snapshot_local()


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
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

        :root {
            --bg: #FAFAFA;
            --panel: #FFFFFF;
            --panel-2: #F4F4F5;
            --text: #18181B;
            --muted: #71717A;
            --line: #E4E4E7;
            --good: #10B981;
            --warn: #F59E0B;
            --danger: #EF4444;
            --info: #3B82F6;
        }

        /* Override global styles for clean Light Theme (Global Audit) */
        .stApp {
            background: var(--bg);
            color: var(--text);
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }

        /* Hide Streamlit default components */
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        footer {visibility: hidden;}
        .stDeployButton {display:none;}
        
        /* Custom Footer Style */
        .custom-footer {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: rgba(250, 250, 250, 0.9);
            backdrop-filter: blur(4px);
            padding: 10px;
            text-align: center;
            font-size: 11px;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, monospace;
            border-top: 1px solid var(--line);
            z-index: 1000;
        }
        .custom-footer a {
            color: var(--muted);
            text-decoration: none;
            opacity: 0.7;
            transition: opacity 0.2s ease;
        }
        .custom-footer a:hover {
            opacity: 1;
            color: var(--text);
        }

        h1, h2, h3 {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            font-weight: 500;
            letter-spacing: -0.02em;
            color: var(--text);
        }

        .block-container {
            padding-top: 2rem;
            padding-bottom: 4rem;
        }

        .bi-hero {
            padding: 1.5rem 1.8rem;
            border: 1px solid var(--line);
            border-radius: 12px;
            background: var(--panel);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
            margin-bottom: 2rem;
        }

        .bi-eyebrow {
            display: inline-flex;
            align-items: center;
            gap: .5rem;
            font-size: .75rem;
            color: var(--muted);
            text-transform: uppercase;
            font-weight: 600;
            letter-spacing: .05em;
            margin-bottom: 1rem;
            border-bottom: 1px solid var(--line);
            padding-bottom: 4px;
        }

        .bi-hero h1 {
            margin: 0;
            font-size: 1.8rem;
            color: var(--text);
            font-weight: 600;
        }

        .bi-hero p {
            margin: .5rem 0 0;
            color: var(--muted);
            font-size: 1rem;
            font-weight: 300;
        }

        .bi-section-title {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            font-size: 1.1rem;
            letter-spacing: -0.01em;
            color: var(--text);
            font-weight: 600;
            margin: 1.5rem 0 .7rem;
            border-bottom: 1px solid var(--line);
            padding-bottom: 6px;
        }

        .bi-card {
            border: 1px solid var(--line);
            border-radius: 12px;
            background: var(--panel);
            padding: 1rem 1.2rem;
            min-height: 120px;
            box-shadow: 0 1px 3px 0 rgba(0,0,0,0.02);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        
        .bi-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
        }

        .bi-card-head {
            display: flex;
            align-items: center;
            gap: .6rem;
            margin-bottom: .8rem;
            color: var(--muted);
            font-weight: 500;
            font-size: .85rem;
            text-transform: uppercase;
            letter-spacing: 0.02em;
        }

        .bi-icon {
            width: 24px;
            height: 24px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            color: var(--text);
        }

        .bi-value {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            font-size: 1.8rem;
            font-weight: 500;
            color: var(--text);
            line-height: 1.1;
        }

        .bi-sub {
            margin-top: .4rem;
            color: var(--muted);
            font-size: .8rem;
            font-weight: 400;
        }

        .bi-card-danger .bi-icon { color: var(--danger); }
        .bi-card-warning .bi-icon { color: var(--warn); }
        .bi-card-info .bi-icon { color: var(--info); }
        .bi-card-success .bi-icon { color: var(--good); }

        .stTabs [data-baseweb="tab-list"] {
            gap: 1rem;
            background: transparent;
            border-bottom: 1px solid var(--line);
            padding: 0;
            margin-bottom: 1rem;
        }

        .stTabs [data-baseweb="tab"] {
            border-radius: 0;
            padding: .75rem 1rem;
            font-weight: 500;
            color: var(--muted);
        }
        
        .stTabs [data-baseweb="tab"][aria-selected="true"] {
            color: var(--text);
            border-bottom: 2px solid var(--text);
        }

        .stDataFrame {
            border: 1px solid var(--line);
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 2px 0 rgba(0,0,0,0.02);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _icone_svg(nome: str) -> str:
    icones = {
        "devices": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="2" width="16" height="20" rx="2" ry="2"/><path d="M12 18h.01"/></svg>',
        "alert": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
        "chip": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"/><path d="M9 4v16"/><path d="M15 4v16"/><path d="M4 9h16"/><path d="M4 15h16"/></svg>',
        "link": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>',
        "unlink": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="m18.84 12.25 1.72-1.71h-.01a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="m5.17 11.75-1.71 1.71a5 5 0 0 0 7.07 7.07l1.71-1.71"/><line x1="8" x2="8" y1="2" y2="5"/><line x1="2" x2="5" y1="8" y2="8"/><line x1="16" x2="16" y1="19" y2="22"/><line x1="19" x2="22" y1="16" y2="16"/></svg>',
        "power": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" x2="12" y1="2" y2="12"/></svg>',
        "gps": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>',
        "imei": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><path d="M12 8v8"/><path d="M8 8v8"/><path d="M16 8v8"/></svg>',
        "sim": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="2" width="16" height="20" rx="2" ry="2"/><path d="M12 22v-4"/><path d="M8 22v-4"/><path d="M16 22v-4"/></svg>',
        "check": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
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


def _amostra_registros(df: pd.DataFrame, mask: pd.Series, limite: int = 3) -> str:
    subset = df.loc[mask].head(limite)
    if subset.empty:
        return ""

    colunas = [c for c in ["imei", "iccid", "placa", "nome_dispositivo"] if c in subset.columns]
    if not colunas:
        return ""

    exemplos = []
    for _, row in subset.iterrows():
        partes = [str(row[c]) for c in colunas if pd.notna(row[c]) and str(row[c]).strip() and str(row[c]) != "-"]
        if partes:
            exemplos.append(" / ".join(partes[:2]))

    return f" Exemplo(s): {', '.join(exemplos)}." if exemplos else ""


def _gerar_observacoes_tecnicas(df: pd.DataFrame) -> list[tuple[str, str]]:
    """Gera observações automáticas e objetivas com base nas divergências encontradas."""
    if df is None or df.empty:
        return []

    observacoes: list[tuple[str, str]] = []
    total = len(df)

    suspeitos = int(df["suspeito"].sum()) if "suspeito" in df.columns else 0
    if suspeitos > 0:
        observacoes.append((
            "pendencias",
            f"Foram identificados {suspeitos:,} registros com pendências ({(suspeitos/total)*100:.1f}% da base analisada).",
        ))

    mapa_flags = [
        (FLAG_DISPOSITIVO_INATIVO, "Dispositivos inativos"),
        (FLAG_SEM_GPS_RECENTE, "Dispositivos sem GPS recente"),
        (FLAG_SEM_PLACA, "Dispositivos sem placa"),
        (FLAG_SEM_CHIP, "Dispositivos sem chip"),
        (FLAG_IMEI_DUPLICADO, "IMEI duplicado"),
        (FLAG_ICCID_DUPLICADO, "ICCID duplicado"),
        (FLAG_TELEFONE_DUPLICADO, "Telefone de chip duplicado"),
        (FLAG_PLACA_DUPLICADA, "Placa duplicada"),
    ]

    for flag, rotulo in mapa_flags:
        if flag in df.columns:
            qtd = int(df[flag].sum())
            if qtd > 0:
                observacoes.append((
                    f"flag::{flag}",
                    f"{rotulo}: {qtd:,} ocorrência(s) ({(qtd/total)*100:.1f}% da base).",
                ))

    if COL_AUD_RISCO_COBRANCA in df.columns:
        risco = df[COL_AUD_RISCO_COBRANCA].astype(str).str.upper()
        alto = int((risco == "ALTO").sum())
        if alto > 0:
            observacoes.append((
                "risco_alto",
                f"Risco de cobrança ALTO em {alto:,} registro(s) ({(alto/total)*100:.1f}% da base).",
            ))

        if COL_AUD_STATUS_DISPOSITIVO in df.columns:
            status = df[COL_AUD_STATUS_DISPOSITIVO].astype(str).str.upper()
            ativo_alto = int(((status == "ATIVO") & (risco == "ALTO")).sum())
            inativo_alto = int(((status == "INATIVO") & (risco == "ALTO")).sum())
            if ativo_alto > 0:
                observacoes.append((
                    "ativo_risco_alto",
                    f"Dispositivos ATIVOS com risco alto: {ativo_alto:,} registro(s).",
                ))
            if inativo_alto > 0:
                observacoes.append((
                    "inativo_risco_alto",
                    f"Dispositivos INATIVOS com risco alto: {inativo_alto:,} registro(s).",
                ))

    if COL_AUD_MOTIVOS_COBRANCA in df.columns:
        motivos = []
        for item in df[COL_AUD_MOTIVOS_COBRANCA].dropna():
            motivos.extend([m.strip() for m in str(item).split(";") if m.strip()])
        if motivos:
            from collections import Counter

            top_motivos = Counter(motivos).most_common(3)
            top_txt = ", ".join([f"{m} ({q})" for m, q in top_motivos])
            observacoes.append(("top_motivos", f"Principais causas técnicas: {top_txt}."))

    return observacoes


def _reanalisar_observacao_tecnica(df: pd.DataFrame, chave: str) -> str:
    total = len(df)
    if chave.startswith("flag::"):
        flag = chave.split("::", 1)[1]
        if flag in df.columns:
            mask = df[flag].fillna(False).astype(bool)
            qtd = int(mask.sum())
            if qtd > 0:
                return f"Validação técnica: {qtd:,} registro(s) confirmados para {flag} ({(qtd/total)*100:.1f}% da base)." + _amostra_registros(df, mask)

    if chave == "pendencias" and "suspeito" in df.columns:
        mask = df["suspeito"].fillna(False).astype(bool)
        qtd = int(mask.sum())
        return f"Validação técnica: {qtd:,} registro(s) permanecem classificados com pendências." + _amostra_registros(df, mask)

    if chave in {"risco_alto", "ativo_risco_alto", "inativo_risco_alto"} and COL_AUD_RISCO_COBRANCA in df.columns:
        risco = df[COL_AUD_RISCO_COBRANCA].astype(str).str.upper()
        if chave == "risco_alto":
            mask = risco == "ALTO"
        elif COL_AUD_STATUS_DISPOSITIVO in df.columns:
            status = df[COL_AUD_STATUS_DISPOSITIVO].astype(str).str.upper()
            mask = (risco == "ALTO") & (status == ("ATIVO" if chave == "ativo_risco_alto" else "INATIVO"))
        else:
            mask = pd.Series([False] * len(df), index=df.index)
        qtd = int(mask.sum())
        return f"Validação técnica: {qtd:,} registro(s) confirmados para {chave}." + _amostra_registros(df, mask)

    if chave == "top_motivos" and COL_AUD_MOTIVOS_COBRANCA in df.columns:
        motivos = []
        for item in df[COL_AUD_MOTIVOS_COBRANCA].dropna():
            motivos.extend([m.strip() for m in str(item).split(";") if m.strip()])
        if motivos:
            from collections import Counter

            top = Counter(motivos).most_common(5)
            return "Validação técnica dos motivos: " + ", ".join([f"{m} ({q})" for m, q in top]) + "."

    return "Reanálise concluída sem divergência adicional para este item."


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
st.sidebar.title("Importar Relatórios")

with st.sidebar.expander("Instruções", expanded=False):
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
    "Relatório de Dispositivos (PDF/CSV/HTML)", type=["pdf", "csv", "html", "htm"], key="up_disp"
)
arquivo_veic = st.sidebar.file_uploader(
    "Relatório de Veículos (PDF/CSV/HTML)", type=["pdf", "csv", "html", "htm"], key="up_veic"
)
arquivo_chips = st.sidebar.file_uploader(
    "Relatório de Chips M2M (PDF/CSV/HTML)", type=["pdf", "csv", "html", "htm"], key="up_chips"
)
arquivo_usuarios = st.sidebar.file_uploader(
    "Relatório de Usuários (PDF/CSV/HTML — opcional)", type=["pdf", "csv", "html", "htm"], key="up_usuarios"
)

with st.sidebar.expander("Arquivos da prestadora M2Data", expanded=False):
    arquivo_chips_m2data = st.file_uploader(
        "Chips M2Data (PDF/CSV/HTML)",
        type=["pdf", "csv", "html", "htm"],
        key="up_chips_m2data",
    )

with st.sidebar.expander("Base oficial SIPROV (referência primária)", expanded=False):
    st.caption(
        "Use o export oficial do SIPROV para validar divergências de status. "
        "Formatos aceitos: JSON, XLSX, PDF, CSV e HTML."
    )
    arquivo_siprov = st.file_uploader(
        "Relatório SIPROV Oficial",
        type=["json", "xlsx", "xls", "pdf", "csv", "html", "htm"],
        key="up_siprov",
    )

with st.sidebar.expander("Parâmetros financeiros (opcional)", expanded=False):
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
    "Dias sem GPS para considerar inativo",
    min_value=1,
    max_value=365,
    value=DIAS_SEM_GPS,
    step=1,
)

processar = st.sidebar.button("Processar Auditoria", type="primary", width="stretch")

# ---------------------------------------------------------------------------
# Processamento
# ---------------------------------------------------------------------------
if processar:
    if arquivo_disp is None:
        st.sidebar.error("Envie o relatório de dispositivos da Base Principal (obrigatório).")
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

                df_siprov = None
                if arquivo_siprov:
                    df_siprov = ler_pdf_siprov(arquivo_siprov)
                    st.session_state["df_siprov"] = df_siprov
                else:
                    st.session_state["df_siprov"] = pd.DataFrame()

                df_cruzado = cruzar_completo(df_disp, df_veic, df_chips)
                df_cruzado = cruzar_com_siprov(df_cruzado, df_siprov, df_usuarios)
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
                _salvar_snapshot_local()
                st.success(
                    f"Auditoria concluída: **{len(df_auditoria):,}** dispositivos analisados, "
                    f"**{df_auditoria['suspeito'].sum():,}** com pendências."
                )
                st.caption("A base processada foi salva localmente e sera mantida ate um novo processamento.")
            except Exception as exc:
                st.error(f"Erro durante o processamento: {exc}")
                logging.exception("Erro no processamento dos relatórios.")

# ---------------------------------------------------------------------------
# Conteúdo principal
# ---------------------------------------------------------------------------
st.markdown(
    """
    <section class="bi-hero">
        <div class="bi-eyebrow">Painel BI de Auditoria Tecnica</div>
        <h1>A.L-Cristina's - Gestão Administrativa avançada</h1>
        <p>Visualizacao profissional para identificar divergencias de cobranca, vinculos tecnicos e inconsistencias cadastrais.</p>
    </section>
    """,
    unsafe_allow_html=True,
)

df_auditoria: pd.DataFrame | None = st.session_state.get("df_auditoria")

if df_auditoria is None:
    st.info(
        "Faça upload dos relatórios na barra lateral e clique em "
        "**Processar Auditoria** para começar."
    )

    # Mostra estrutura esperada dos relatórios
    with st.expander("Estrutura esperada dos relatórios", expanded=True):
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
                - Dispositivo **inativo**
                - Sem **placa** vinculada
                - Sem **GPS** nos últimos {dias_gps} dias
                - Sem **chip** (ICCID ausente)
                - **IMEI duplicado**
                - **ICCID duplicado**
                - **Telefone duplicado**
                - **Placa duplicada**
                - Veículo **desativado**
                - **Sem cadastro no SIPROV**
                - **SIPROV inativo x prestador ativo**
                - **SIPROV inadimplente x prestador ativo**
                - **Telefone cliente duplicado** *(risco cadastral)*
                """
            )
    st.stop()

snapshot_salvo_em = st.session_state.get("snapshot_salvo_em")
if st.session_state.get("snapshot_carregado") and snapshot_salvo_em:
    st.info(
        "Usando a ultima base processada salva localmente. "
        f"Snapshot: {snapshot_salvo_em}. Envie novos arquivos e processe novamente apenas quando precisar atualizar o cruzamento."
    )

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

tb_exec, tb_siprov, tb_financeiro, tb_dados = st.tabs(["Visão Executiva", "Auditoria SIPROV", "Impacto Financeiro", "Bases Analíticas"])

with tb_exec:
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

with tb_siprov:
    st.markdown('<div class="bi-section-title">Conferência Oficial SIPROV</div>', unsafe_allow_html=True)
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        _card_kpi(
            "Sem cadastro SIPROV",
            f"{contagem_flag(FLAG_SIPROV_SEM_CADASTRO):,}",
            "Sem match na base oficial",
            "alert",
            "warning",
        )
    with s2:
        _card_kpi(
            "Inativo no SIPROV e ativo no prestador",
            f"{contagem_flag(FLAG_SIPROV_INATIVO_ATIVO_PRESTADOR):,}",
            "Potencial custo indevido",
            "danger",
            "danger",
        )
    with s3:
        _card_kpi(
            "Inadimplente no SIPROV e ativo no prestador",
            f"{contagem_flag(FLAG_SIPROV_INADIMPLENTE_ATIVO_PRESTADOR):,}",
            "Prioridade de bloqueio",
            "danger",
            "danger",
        )
    with s4:
        if COL_SIP_STATUS_REFERENCIA in df_auditoria.columns:
            conferidos = int(df_auditoria[COL_SIP_STATUS_REFERENCIA].astype(str).str.upper().ne("INDEFINIDO").sum())
        else:
            conferidos = 0
        _card_kpi(
            "Com status oficial conferido",
            f"{conferidos:,}",
            "Base SIPROV aplicada",
            "check",
            "info",
        )

    with st.expander("Interpretação inteligente de divergências SIPROV", expanded=False):
        st.markdown(
            """
            - O **SIPROV** é a base oficial de referência para status (ativo, inativo, inadimplente).
            - Divergência de status indica **prioridade de revisão**, mas pode existir caso operacional de transição (ex.: equipamento transferido e cadastro ainda não atualizado).
            - Para reduzir falso positivo, priorize validação quando o cruzamento estiver com confiança **ALTA** (placa ou CPF/CNPJ).
            - Casos com confiança **MÉDIA** (match por nome) devem ser tratados como triagem assistida.
            """
        )

    observacoes_tecnicas = _gerar_observacoes_tecnicas(df_auditoria)

    st.divider()

    # ---------------------------------------------------------------------------
    # Visão financeira e utilidade
    # ---------------------------------------------------------------------------
with tb_financeiro:
    st.subheader("Cobrança Real e Itens Úteis")

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

    with st.expander("Chips cobrados pela Base Principal e pela M2Data", expanded=False):
        if not df_chips_sobrepostos.empty:
            st.dataframe(df_chips_sobrepostos, width="stretch", height=280)
        else:
            st.success("Nenhuma sobreposição de cobrança de chips identificada entre os prestadores.")

    with st.expander("Itens classificados como inúteis", expanded=False):
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
with tb_dados:
    st.subheader("Filtros")

    col_f1, col_f2, col_f3, col_f4, col_f5, col_f6 = st.columns(6)

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
        FLAG_SIPROV_SEM_CADASTRO: "Sem cadastro SIPROV",
        FLAG_SIPROV_INATIVO_ATIVO_PRESTADOR: "SIPROV inativo e prestador ativo",
        FLAG_SIPROV_INADIMPLENTE_ATIVO_PRESTADOR: "SIPROV inadimplente e prestador ativo",
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

    status_siprov_disponiveis = ["TODOS"]
    if COL_SIP_STATUS_REFERENCIA in df_auditoria.columns:
        status_siprov_disponiveis += sorted(
            {str(v).strip().upper() for v in df_auditoria[COL_SIP_STATUS_REFERENCIA].dropna().tolist() if str(v).strip()}
        )

    with col_f5:
        status_siprov_filtro = st.selectbox(
            "Status SIPROV",
            options=status_siprov_disponiveis,
            index=0,
        )

    with col_f6:
        grupo_divergencia = st.selectbox(
            "Grupo de divergência",
            options=[
                "TODOS",
                "Sem cadastro SIPROV",
                "SIPROV inativo e prestador ativo",
                "SIPROV inadimplente e prestador ativo",
                "Somente divergências SIPROV",
            ],
            index=0,
        )

    # Aplica filtros
    df_exibir = df_auditoria.copy()
    if apenas_suspeitos:
        df_exibir = df_exibir[df_exibir["suspeito"]]
    for flag in flags_selecionadas:
        df_exibir = df_exibir[df_exibir[flag]]

    if mostrar_so_alto_risco and COL_AUD_RISCO_COBRANCA in df_exibir.columns:
        df_exibir = df_exibir[df_exibir[COL_AUD_RISCO_COBRANCA] == "ALTO"]

    if status_siprov_filtro != "TODOS" and COL_SIP_STATUS_REFERENCIA in df_exibir.columns:
        df_exibir = df_exibir[df_exibir[COL_SIP_STATUS_REFERENCIA].astype(str).str.upper() == status_siprov_filtro]

    if grupo_divergencia == "Sem cadastro SIPROV" and FLAG_SIPROV_SEM_CADASTRO in df_exibir.columns:
        df_exibir = df_exibir[df_exibir[FLAG_SIPROV_SEM_CADASTRO]]
    elif grupo_divergencia == "SIPROV inativo e prestador ativo" and FLAG_SIPROV_INATIVO_ATIVO_PRESTADOR in df_exibir.columns:
        df_exibir = df_exibir[df_exibir[FLAG_SIPROV_INATIVO_ATIVO_PRESTADOR]]
    elif grupo_divergencia == "SIPROV inadimplente e prestador ativo" and FLAG_SIPROV_INADIMPLENTE_ATIVO_PRESTADOR in df_exibir.columns:
        df_exibir = df_exibir[df_exibir[FLAG_SIPROV_INADIMPLENTE_ATIVO_PRESTADOR]]
    elif grupo_divergencia == "Somente divergências SIPROV":
        flags_siprov = [
            f
            for f in [
                FLAG_SIPROV_SEM_CADASTRO,
                FLAG_SIPROV_INATIVO_ATIVO_PRESTADOR,
                FLAG_SIPROV_INADIMPLENTE_ATIVO_PRESTADOR,
            ]
            if f in df_exibir.columns
        ]
        if flags_siprov:
            df_exibir = df_exibir[df_exibir[flags_siprov].any(axis=1)]

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
    st.subheader("Resultados da Auditoria")

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
        COL_SIP_STATUS_REFERENCIA,
        COL_SIP_CHAVE_CRUZAMENTO,
        COL_SIP_CONFIANCA_CRUZAMENTO,
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
            "suspeito": st.column_config.CheckboxColumn("Suspeito"),
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
            FLAG_SIPROV_SEM_CADASTRO: st.column_config.CheckboxColumn("Sem SIPROV"),
            FLAG_SIPROV_INATIVO_ATIVO_PRESTADOR: st.column_config.CheckboxColumn("SIPROV Inativo x Ativo"),
            FLAG_SIPROV_INADIMPLENTE_ATIVO_PRESTADOR: st.column_config.CheckboxColumn("SIPROV Inadimplente x Ativo"),
        },
    )

    if observacoes_tecnicas:
        with st.expander("Análise Inteligente", expanded=False):
            chaves_erradas: list[str] = []

            for idx, (chave, obs) in enumerate(observacoes_tecnicas, start=1):
                st.markdown(f"{idx}. {obs}")
                c_ok, c_err = st.columns(2)
                key_ok = f"obs_ok_{idx}_{chave}"
                key_err = f"obs_err_{idx}_{chave}"
                ok = c_ok.checkbox("Correto", key=key_ok)
                err = c_err.checkbox("Errado", key=key_err)

                if ok and err:
                    st.caption("Selecione apenas uma opção (Correto ou Errado).")
                if err and not ok:
                    chaves_erradas.append(chave)

            if chaves_erradas:
                if st.button("Reanalisar observações marcadas como erro", key="btn_reanalise_obs"):
                    st.session_state["reanalise_obs"] = {
                        chave: _reanalisar_observacao_tecnica(df_auditoria, chave) for chave in chaves_erradas
                    }

            reanalise = st.session_state.get("reanalise_obs", {})
            if reanalise:
                st.markdown("**Revisão técnica dos itens marcados como erro**")
                for _, texto in reanalise.items():
                    st.markdown(f"- {texto}")

    # ---------------------------------------------------------------------------
    # Exportação
    # ---------------------------------------------------------------------------
    st.subheader("Exportar Resultados")

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
    with col_e3:
        if _pdf_export_disponivel():
            subtitulo_pdf = (
                f"Registros exportados: {len(df_export):,} | Gerado em: {datetime.now(tz=timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}"
            )
            st.download_button(
                label="⬇️ Baixar Relatorio Completo (.pdf)",
                data=para_pdf_bytes(df_export, subtitulo=subtitulo_pdf),
                file_name="auditoria_cobranca_m2m.pdf",
                mime="application/pdf",
                width="stretch",
            )
        else:
            st.caption("Exportacao PDF completa indisponivel neste ambiente ate instalar reportlab.")

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
    st.subheader("Relatório Executivo com IA")

    _OLLAMA_URL = "http://localhost:11434/api/generate"
    _OLLAMA_MODEL = "mistral"


    def _texto_para_pdf_bytes(texto: str, titulo: str = "Relatorio Executivo de Auditoria") -> bytes:
        """Converte texto simples para PDF em bytes."""
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        _, altura = A4

        y = altura - 50
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(40, y, titulo)
        y -= 28

        pdf.setFont("Helvetica", 10)
        for linha in texto.splitlines():
            blocos = textwrap.wrap(linha, width=110) or [""]
            for bloco in blocos:
                if y < 40:
                    pdf.showPage()
                    pdf.setFont("Helvetica", 10)
                    y = altura - 40
                pdf.drawString(40, y, bloco)
                y -= 14

        pdf.save()
        return buffer.getvalue()


    def _pdf_export_disponivel() -> bool:
        try:
            import reportlab  # noqa: F401
            return True
        except Exception:
            return False


    def _possui_dados_financeiros(df: "pd.DataFrame") -> bool:
        if "valor_mensal" not in df.columns:
            return False
        serie = pd.to_numeric(df["valor_mensal"], errors="coerce")
        return bool(serie.notna().any())

    def _resumo_auditoria(df: "pd.DataFrame") -> str:
        """Retorna um resumo textual em linguagem natural para o prompt do modelo."""
        from collections import Counter
        total = len(df)
        linhas = [f"Total de registros auditados: {total}"]

        if COL_AUD_RISCO_COBRANCA in df.columns:
            freq = df[COL_AUD_RISCO_COBRANCA].value_counts()
            linhas.append("\nDistribuição de risco de COBRANÇA:")
            for nivel, qtd in freq.items():
                pct = round(qtd / total * 100, 1)
                linhas.append(f"  - {nivel}: {qtd} registros ({pct}%)")

        if COL_AUD_RISCO_CADASTRO in df.columns:
            freq2 = df[COL_AUD_RISCO_CADASTRO].value_counts()
            linhas.append("\nDistribuição de risco de CADASTRO:")
            for nivel, qtd in freq2.items():
                pct = round(qtd / total * 100, 1)
                linhas.append(f"  - {nivel}: {qtd} registros ({pct}%)")

        if COL_AUD_MOTIVOS_COBRANCA in df.columns:
            todos = []
            for m in df[COL_AUD_MOTIVOS_COBRANCA].dropna():
                todos.extend([x.strip() for x in str(m).split(";") if x.strip()])
            if todos:
                linhas.append("\nMotivos de divergência em COBRANÇA (top 10):")
                for motivo, cnt in Counter(todos).most_common(10):
                    linhas.append(f"  - {motivo}: {cnt} ocorrências")

        if COL_AUD_MOTIVOS_CADASTRO in df.columns:
            todos2 = []
            for m in df[COL_AUD_MOTIVOS_CADASTRO].dropna():
                todos2.extend([x.strip() for x in str(m).split(";") if x.strip()])
            if todos2:
                linhas.append("\nMotivos de divergência em CADASTRO (top 10):")
                for motivo, cnt in Counter(todos2).most_common(10):
                    linhas.append(f"  - {motivo}: {cnt} ocorrências")

        if _possui_dados_financeiros(df) and COL_AUD_RISCO_COBRANCA in df.columns:
            valores = pd.to_numeric(df["valor_mensal"], errors="coerce").fillna(0)
            mask = df[COL_AUD_RISCO_COBRANCA].isin(["alto", "médio"])
            valor = valores[mask].sum()
            linhas.append(f"\nValor mensal estimado em risco (risco alto + médio): R$ {valor:,.2f}")
        else:
            linhas.append("\nValor financeiro: não disponível nos dados fornecidos.")

        return "\n".join(linhas)


    def _resumo_auditoria_por_sessao(df: "pd.DataFrame", sessao: str) -> str:
        """Raciona a análise por sessão para reduzir volume e acelerar resposta do modelo."""
        sessao_norm = (sessao or "Geral").strip().lower()
        total = len(df)
        linhas = [f"Sessão analítica: {sessao}", f"Total de registros: {total}"]

        def _add_flag(nome: str, rotulo: str) -> None:
            if nome in df.columns:
                qtd = int(df[nome].fillna(False).astype(bool).sum())
                linhas.append(f"- {rotulo}: {qtd}")

        if sessao_norm == "cobrança":
            if COL_AUD_RISCO_COBRANCA in df.columns:
                freq = df[COL_AUD_RISCO_COBRANCA].value_counts()
                linhas.append("Distribuição de risco de cobrança:")
                for nivel, qtd in freq.items():
                    linhas.append(f"- {nivel}: {int(qtd)}")
            _add_flag(FLAG_DISPOSITIVO_INATIVO, "Dispositivo inativo")
            _add_flag(FLAG_SEM_GPS_RECENTE, "Sem GPS recente")
            _add_flag(FLAG_SEM_CHIP, "Sem chip")
            _add_flag(FLAG_SEM_PLACA, "Sem placa")

        elif sessao_norm == "cadastro":
            if COL_AUD_RISCO_CADASTRO in df.columns:
                freq = df[COL_AUD_RISCO_CADASTRO].value_counts()
                linhas.append("Distribuição de risco de cadastro:")
                for nivel, qtd in freq.items():
                    linhas.append(f"- {nivel}: {int(qtd)}")
            _add_flag(FLAG_TELEFONE_CLIENTE_DUPLICADO, "Telefone cliente duplicado")
            _add_flag(FLAG_PLACA_DUPLICADA, "Placa duplicada")

        elif sessao_norm == "duplicidades":
            _add_flag(FLAG_IMEI_DUPLICADO, "IMEI duplicado")
            _add_flag(FLAG_ICCID_DUPLICADO, "ICCID duplicado")
            _add_flag(FLAG_TELEFONE_DUPLICADO, "Telefone de chip duplicado")
            _add_flag(FLAG_PLACA_DUPLICADA, "Placa duplicada")

        elif sessao_norm in {"status/gps", "status", "gps"}:
            _add_flag(FLAG_DISPOSITIVO_INATIVO, "Dispositivo inativo")
            _add_flag(FLAG_SEM_GPS_RECENTE, "Sem GPS recente")
            _add_flag(FLAG_SEM_PLACA, "Sem placa")
            _add_flag(FLAG_SEM_CHIP, "Sem chip")

        else:
            # Geral: reaproveita resumo completo
            return _resumo_auditoria(df)

        if _possui_dados_financeiros(df) and COL_AUD_RISCO_COBRANCA in df.columns:
            valores = pd.to_numeric(df["valor_mensal"], errors="coerce").fillna(0)
            mask = df[COL_AUD_RISCO_COBRANCA].astype(str).str.upper().isin(["ALTO", "MÉDIO", "MEDIO"])
            linhas.append(f"Valor em risco (se disponível): R$ {float(valores[mask].sum()):,.2f}")
        else:
            linhas.append("Valor financeiro: não informado nos dados.")

        return "\n".join(linhas)

    _PROMPT_TEMPLATE = """\
    Você é um auditor forense de telecomunicações. Redija um RELATÓRIO DE AUDITORIA em português brasileiro.

    REGRAS CRÍTICAS — SIGA RIGOROSAMENTE:
    1. Use EXCLUSIVAMENTE os números e dados fornecidos abaixo. NUNCA invente valores, percentuais ou estimativas não presentes nos dados.
    2. Se um dado não estiver disponível, escreva explicitamente "não informado" — nunca use placeholders como "R$ XXXX".
    3. Cite sempre a quantidade exata de registros afetados por cada problema.
    4. Linguagem direta, sem rodeios, para gestores não técnicos.
    5. Máximo 800 palavras no total.

    DIRETRIZ FINANCEIRA ESPECÍFICA:
    {regra_financeira}

    ESTRUTURA OBRIGATÓRIA:

    ## RESUMO EXECUTIVO
    Dois parágrafos. Primeiro: o que foi auditado e quantos registros. Segundo: principal problema encontrado com números reais.

    ## DIVERGÊNCIAS IDENTIFICADAS
    Uma linha por tipo de problema, formato:
    - [MOTIVO EXATO DOS DADOS]: X registros afetados (Y% do total)

    ## IMPACTO FINANCEIRO
    Se valor disponível: cite o número exato. Se não disponível: diga "valor financeiro não informado nos dados" e recomende levantamento.

    ## RECOMENDAÇÕES (máximo 4)
    Numeradas, concretas, baseadas nos problemas reais encontrados.

    ## CONCLUSÃO
    Uma frase direta sobre a gravidade e urgência.

    ---
    DADOS REAIS DA AUDITORIA (use apenas estes):
    {resumo}
    """

    with st.expander("Configuração do modelo", expanded=False):
        ollama_modelo = st.text_input("Modelo Ollama", value=_OLLAMA_MODEL, key="ollama_model")
        ollama_url = st.text_input("URL da API Ollama", value=_OLLAMA_URL, key="ollama_url")
        sessao_analise = st.selectbox(
            "Sessão da análise",
            options=["Geral", "Cobrança", "Cadastro", "Duplicidades", "Status/GPS"],
            index=0,
            key="sessao_analise",
        )

    if st.button("Gerar Relatório Executivo", type="primary", key="btn_gerar_relatorio"):
        try:
            import requests as _requests
            import json as _json
            sessao_escolhida = st.session_state.get("sessao_analise", "Geral")
            resumo_txt = _resumo_auditoria_por_sessao(df_auditoria, sessao_escolhida)
            tem_dado_financeiro = _possui_dados_financeiros(df_auditoria)
            regra_financeira = (
                "Existem dados financeiros reais. Você DEVE usar apenas os valores presentes nos dados e citar os números exatos."
                if tem_dado_financeiro
                else "NÃO existem dados financeiros reais. É PROIBIDO mensurar impacto em reais, estimar valores, ou citar qualquer número monetário. "
                     "Nesta situação, escreva somente: 'valor financeiro não informado nos dados'."
            )
            prompt = _PROMPT_TEMPLATE.format(resumo=resumo_txt, regra_financeira=regra_financeira)

            num_predict_por_sessao = {
                "Geral": 900,
                "Cobrança": 500,
                "Cadastro": 500,
                "Duplicidades": 420,
                "Status/GPS": 420,
            }
            num_predict = num_predict_por_sessao.get(sessao_escolhida, 500)
            timeout_por_sessao = 420 if sessao_escolhida == "Geral" else 240

            with st.spinner("Gerando relatório com IA... aguarde"):
                try:
                    resp = _requests.post(
                        st.session_state.get("ollama_url", _OLLAMA_URL),
                        json={
                            "model": st.session_state.get("ollama_model", _OLLAMA_MODEL),
                            "prompt": prompt,
                            "stream": False,
                            "options": {
                                "temperature": 0.1,
                                "top_p": 0.85,
                                "num_predict": num_predict,
                                "repeat_penalty": 1.1,
                            },
                        },
                        timeout=timeout_por_sessao,
                    )
                except _requests.exceptions.ReadTimeout:
                    # Retry leve para evitar travar o usuário em datasets grandes
                    resp = _requests.post(
                        st.session_state.get("ollama_url", _OLLAMA_URL),
                        json={
                            "model": st.session_state.get("ollama_model", _OLLAMA_MODEL),
                            "prompt": prompt + "\n\nResponda de forma extremamente objetiva em no máximo 8 bullets.",
                            "stream": False,
                            "options": {
                                "temperature": 0.1,
                                "top_p": 0.8,
                                "num_predict": max(220, int(num_predict * 0.6)),
                                "repeat_penalty": 1.1,
                            },
                        },
                        timeout=180,
                    )
                resp.raise_for_status()
                texto_acumulado = resp.json().get("response", "")
                st.session_state["ultimo_relatorio"] = texto_acumulado

            st.markdown(texto_acumulado)
            col_down_txt, col_down_pdf = st.columns(2)
            with col_down_txt:
                st.download_button(
                    label="⬇️ Baixar Relatório (.txt)",
                    data=texto_acumulado.encode("utf-8"),
                    file_name="relatorio_executivo_auditoria.txt",
                    mime="text/plain",
                    width="stretch",
                )
            with col_down_pdf:
                pdf_disponivel = _pdf_export_disponivel()
                st.download_button(
                    label="⬇️ Baixar Relatório (.pdf)",
                    data=_texto_para_pdf_bytes(texto_acumulado) if pdf_disponivel else b"",
                    file_name="relatorio_executivo_auditoria.pdf",
                    mime="application/pdf",
                    width="stretch",
                    disabled=not pdf_disponivel,
                    help="Instale a biblioteca reportlab no servidor para habilitar o PDF." if not pdf_disponivel else None,
                )
                if not pdf_disponivel:
                    st.caption("PDF desabilitado neste ambiente (dependência `reportlab` ausente).")

        except Exception as _e:
            st.error(f"Erro ao conectar ao Ollama: {_e}\n\nVerifique se o serviço está rodando: `ollama serve`")

    # ---------------------------------------------------------------------------
    # Abas para visualização dos dados brutos
    # ---------------------------------------------------------------------------
    st.divider()
    with st.expander("Dados brutos importados", expanded=False):
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
    st.subheader("Divergências Detalhadas")

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
