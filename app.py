"""Aplicação principal – Auditoria de Cobrança M2M.

Execute com:
    streamlit run app.py
"""

from datetime import date

import pandas as pd
import streamlit as st

from src.config import APP_TITULO, APP_SUBTITULO
from src.cruzamentos import cruzar_dados
from src.exportacao import exportar_csv, exportar_excel
from src.leitura_pdf import ler_arquivo
from src.normalizacao import (
    normalizar_chips,
    normalizar_cobranca,
    normalizar_dispositivos,
    normalizar_veiculos,
)
from src.regras_auditoria import aplicar_regras, resumo_auditoria

# ─────────────────────────── Configuração da página ───────────────────────────

st.set_page_config(
    page_title=APP_TITULO,
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────── Estilos ─────────────────────────────────────

st.markdown(
    """
    <style>
    .metric-card {
        background: #f0f2f6;
        border-radius: 8px;
        padding: 16px;
        text-align: center;
    }
    .metric-card.critico { background: #ffcccc; }
    .metric-card.pendente { background: #fff2cc; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ──────────────────────────────── Cabeçalho ───────────────────────────────────

st.title(f"🔍 {APP_TITULO}")
st.caption(APP_SUBTITULO)
st.divider()

# ─────────────────────────────── Sidebar ──────────────────────────────────────

with st.sidebar:
    st.header("📂 Carregar arquivos")
    st.markdown(
        "Faça upload dos relatórios em **PDF** ou **CSV**. "
        "O relatório de **dispositivos** é obrigatório para iniciar a auditoria."
    )

    arq_disp = st.file_uploader(
        "Relatório de dispositivos *",
        type=["pdf", "csv"],
        key="dispositivos",
        help="Relatório com IMEI, estado de ativação, chip, GPS e placa.",
    )
    arq_chips = st.file_uploader(
        "Relatório de chips (opcional)",
        type=["pdf", "csv"],
        key="chips",
    )
    arq_veic = st.file_uploader(
        "Relatório de veículos (opcional)",
        type=["pdf", "csv"],
        key="veiculos",
    )
    arq_cob = st.file_uploader(
        "Relatório de cobrança M2M (opcional)",
        type=["pdf", "csv"],
        key="cobranca",
    )

    st.divider()
    st.header("⚙️ Configurações")
    limite_gps = st.slider(
        "Dias sem GPS para considerar inativo",
        min_value=7,
        max_value=180,
        value=30,
        step=7,
    )
    import src.config as cfg

    cfg.LIMITE_GPS_DIAS = limite_gps

    st.divider()
    st.caption(f"Data de referência: {date.today().strftime('%d/%m/%Y')}")

# ──────────────────────────────── Pipeline ────────────────────────────────────


@st.cache_data(show_spinner="Lendo arquivo…")
def _ler(arquivo):
    return ler_arquivo(arquivo)


def _carregar_df(arquivo, normalizador):
    if arquivo is None:
        return None
    try:
        df_raw = _ler(arquivo)
        if df_raw.empty:
            st.warning(f"O arquivo '{arquivo.name}' não contém dados reconhecíveis.")
            return None
        return normalizador(df_raw)
    except Exception as exc:
        st.error(f"Erro ao processar '{arquivo.name}': {exc}")
        return None


# ─────────────────────────── Área principal ───────────────────────────────────

if arq_disp is None:
    st.info(
        "👈 Faça o upload do **Relatório de dispositivos** na barra lateral para iniciar a auditoria.",
        icon="ℹ️",
    )
    st.stop()

with st.spinner("Processando dados…"):
    df_disp = _carregar_df(arq_disp, normalizar_dispositivos)
    df_chips = _carregar_df(arq_chips, normalizar_chips)
    df_veic = _carregar_df(arq_veic, normalizar_veiculos)
    df_cob = _carregar_df(arq_cob, normalizar_cobranca)

if df_disp is None or df_disp.empty:
    st.error("Não foi possível extrair dados do relatório de dispositivos.")
    st.stop()

df_cruzado = cruzar_dados(df_disp, df_chips, df_veic, df_cob)
df_auditoria = aplicar_regras(df_cruzado)
resumo = resumo_auditoria(df_auditoria)

# ─────────────────────────── Métricas ─────────────────────────────────────────

total = len(df_auditoria)
total_pendente = resumo.get("Total com pendência", 0)
total_critico = resumo.get("Total crítico", 0)

col1, col2, col3 = st.columns(3)
col1.metric("Total de dispositivos", total)
col2.metric("Com pendência", total_pendente)
col3.metric("🔴 Críticos", total_critico)

if total > 0:
    st.caption(
        f"📌 {total_pendente/total*100:.1f}% dos dispositivos apresentam ao menos uma pendência."
    )

st.divider()

# ─────────────────────────── Gráfico de resumo ────────────────────────────────

motivos_para_grafico = {k: v for k, v in resumo.items() if k not in ("Total com pendência", "Total crítico") and v > 0}
if motivos_para_grafico:
    st.subheader("📊 Resumo por motivo de pendência")
    df_resumo = pd.DataFrame(
        {"Motivo": list(motivos_para_grafico.keys()), "Quantidade": list(motivos_para_grafico.values())}
    ).sort_values("Quantidade", ascending=False)
    st.bar_chart(df_resumo.set_index("Motivo"))

# ─────────────────────────── Filtros e tabela ─────────────────────────────────

st.subheader("📋 Resultados da auditoria")

with st.expander("🔎 Filtros", expanded=True):
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        mostrar_apenas_pendentes = st.checkbox("Apenas com pendência", value=True)
    with col_f2:
        apenas_criticos = st.checkbox("Apenas críticos")
    with col_f3:
        busca_imei = st.text_input("Buscar por IMEI", placeholder="Digite um IMEI…")

df_vis = df_auditoria.copy()

if mostrar_apenas_pendentes and "auditoria_pendencia" in df_vis.columns:
    df_vis = df_vis[df_vis["auditoria_pendencia"]]

if apenas_criticos and "auditoria_critico" in df_vis.columns:
    df_vis = df_vis[df_vis["auditoria_critico"]]

if busca_imei and "imei" in df_vis.columns:
    df_vis = df_vis[df_vis["imei"].astype(str).str.contains(busca_imei.strip(), na=False)]

st.caption(f"{len(df_vis)} registros exibidos de {total} totais.")

# Colunas prioritárias no início
colunas_prioritarias = [
    "auditoria_motivos", "imei", "ativo", "placa", "chip_serie",
    "chip_telefone", "gps_data",
]
colunas_existentes = [c for c in colunas_prioritarias if c in df_vis.columns]
colunas_resto = [c for c in df_vis.columns if c not in colunas_existentes]
df_vis = df_vis[colunas_existentes + colunas_resto]

st.dataframe(
    df_vis,
    use_container_width=True,
    hide_index=True,
)

# ─────────────────────────── Exportação ───────────────────────────────────────

st.divider()
st.subheader("💾 Exportar resultados")

col_e1, col_e2 = st.columns(2)

with col_e1:
    csv_bytes = exportar_csv(df_auditoria)
    st.download_button(
        label="⬇️ Baixar CSV",
        data=csv_bytes,
        file_name="auditoria_cobranca_m2m.csv",
        mime="text/csv",
    )

with col_e2:
    try:
        xlsx_bytes = exportar_excel(df_auditoria)
        st.download_button(
            label="⬇️ Baixar Excel (.xlsx)",
            data=xlsx_bytes,
            file_name="auditoria_cobranca_m2m.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as exc:
        st.warning(f"Exportação Excel indisponível: {exc}")

# ─────────────────────────── Dados brutos ─────────────────────────────────────

with st.expander("🗂️ Ver dados brutos de dispositivos"):
    st.dataframe(df_disp, use_container_width=True, hide_index=True)

if df_chips is not None and not df_chips.empty:
    with st.expander("🗂️ Ver dados brutos de chips"):
        st.dataframe(df_chips, use_container_width=True, hide_index=True)

if df_veic is not None and not df_veic.empty:
    with st.expander("🗂️ Ver dados brutos de veículos"):
        st.dataframe(df_veic, use_container_width=True, hide_index=True)

if df_cob is not None and not df_cob.empty:
    with st.expander("🗂️ Ver dados brutos de cobrança"):
        st.dataframe(df_cob, use_container_width=True, hide_index=True)
