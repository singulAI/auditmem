"""
Auditoria de Cobrança M2M — Dashboard Streamlit.

Execute com:
    streamlit run app.py
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from src.config import (
    DIAS_SEM_GPS,
    FLAGS_AUDITORIA,
    FLAG_DISPOSITIVO_INATIVO,
    FLAG_ICCID_DUPLICADO,
    FLAG_IMEI_DUPLICADO,
    FLAG_SEM_CHIP,
    FLAG_SEM_GPS_RECENTE,
    FLAG_SEM_PLACA,
    FLAG_VEICULO_DESATIVADO,
)
from src.cruzamentos import cruzar_completo
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
        "df_usuarios": None,
        "df_auditoria": None,
    }
    for chave, valor in defaults.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor

_init_state()

# ---------------------------------------------------------------------------
# Sidebar — Upload de PDFs
# ---------------------------------------------------------------------------
st.sidebar.title("📂 Importar Relatórios PDF")

with st.sidebar.expander("ℹ️ Instruções", expanded=False):
    st.markdown(
        """
        Faça upload dos relatórios exportados em PDF:

        - **Dispositivos** *(obrigatório)*
        - **Veículos** *(recomendado)*
        - **Chips M2M** *(recomendado)*
        - **Usuários** *(opcional)*

        O sistema extrai as tabelas automaticamente, normaliza os dados e
        aplica as regras de auditoria.
        """
    )

arquivo_disp = st.sidebar.file_uploader(
    "📡 Relatório de Dispositivos (PDF)", type=["pdf"], key="up_disp"
)
arquivo_veic = st.sidebar.file_uploader(
    "🚗 Relatório de Veículos (PDF)", type=["pdf"], key="up_veic"
)
arquivo_chips = st.sidebar.file_uploader(
    "📶 Relatório de Chips M2M (PDF)", type=["pdf"], key="up_chips"
)
arquivo_usuarios = st.sidebar.file_uploader(
    "👤 Relatório de Usuários (PDF — opcional)", type=["pdf"], key="up_usuarios"
)

st.sidebar.divider()
dias_gps = st.sidebar.slider(
    "⏱️ Dias sem GPS para considerar inativo",
    min_value=1,
    max_value=365,
    value=DIAS_SEM_GPS,
    step=1,
)

processar = st.sidebar.button("🚀 Processar Auditoria", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Processamento
# ---------------------------------------------------------------------------
if processar:
    if arquivo_disp is None:
        st.sidebar.error("⚠️ O relatório de dispositivos é obrigatório.")
    else:
        with st.spinner("Lendo e processando os PDFs…"):
            try:
                df_disp = ler_pdf_dispositivos(arquivo_disp)
                st.session_state["df_dispositivos"] = df_disp

                df_veic = None
                if arquivo_veic:
                    df_veic = ler_pdf_veiculos(arquivo_veic)
                    st.session_state["df_veiculos"] = df_veic

                df_chips = None
                if arquivo_chips:
                    df_chips = ler_pdf_chips(arquivo_chips)
                    st.session_state["df_chips"] = df_chips

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
                st.session_state["df_auditoria"] = df_auditoria
                st.success(
                    f"✅ Auditoria concluída: **{len(df_auditoria):,}** dispositivos analisados, "
                    f"**{df_auditoria['suspeito'].sum():,}** com pendências."
                )
            except Exception as exc:
                st.error(f"❌ Erro durante o processamento: {exc}")
                logging.exception("Erro no processamento do PDF.")

# ---------------------------------------------------------------------------
# Conteúdo principal
# ---------------------------------------------------------------------------
st.title("🔍 Auditoria de Cobrança M2M")
st.caption(
    "Dashboard para identificação de cobranças indevidas em rastreadores, "
    "chips M2M e veículos."
)

df_auditoria: pd.DataFrame | None = st.session_state.get("df_auditoria")

if df_auditoria is None:
    st.info(
        "👈 Faça upload dos relatórios PDF na barra lateral e clique em "
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
                - Telefone do chip
                - Operadora
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
                - 🟠 Veículo **desativado**
                """
            )
    st.stop()

# ---------------------------------------------------------------------------
# Métricas resumo
# ---------------------------------------------------------------------------
total = len(df_auditoria)
suspeitos = int(df_auditoria["suspeito"].sum())

col_m1, col_m2, col_m3, col_m4, col_m5, col_m6, col_m7, col_m8 = st.columns(8)
col_m1.metric("Total", f"{total:,}")
col_m2.metric("⚠️ Suspeitos", f"{suspeitos:,}", delta=f"{(suspeitos/total)*100:.1f}%" if total else "0%", delta_color="inverse")

for flag, col, label in [
    (FLAG_DISPOSITIVO_INATIVO, col_m3, "🔴 Inativos"),
    (FLAG_SEM_PLACA, col_m4, "🔴 Sem Placa"),
    (FLAG_SEM_GPS_RECENTE, col_m5, "🔴 Sem GPS"),
    (FLAG_SEM_CHIP, col_m6, "🔴 Sem Chip"),
    (FLAG_IMEI_DUPLICADO, col_m7, "🟠 IMEI Dup."),
    (FLAG_ICCID_DUPLICADO, col_m8, "🟠 ICCID Dup."),
]:
    if flag in df_auditoria.columns:
        col.metric(label, f"{int(df_auditoria[flag].sum()):,}")

st.divider()

# ---------------------------------------------------------------------------
# Filtros interativos
# ---------------------------------------------------------------------------
st.subheader("🔎 Filtros")

col_f1, col_f2, col_f3, col_f4 = st.columns(4)

with col_f1:
    apenas_suspeitos = st.checkbox("Exibir apenas suspeitos", value=True)

flags_disponiveis = [f for f in FLAGS_AUDITORIA if f in df_auditoria.columns]
nomes_flags = {
    FLAG_DISPOSITIVO_INATIVO: "Dispositivo inativo",
    FLAG_SEM_PLACA: "Sem placa",
    FLAG_SEM_GPS_RECENTE: "Sem GPS recente",
    FLAG_SEM_CHIP: "Sem chip",
    FLAG_IMEI_DUPLICADO: "IMEI duplicado",
    FLAG_ICCID_DUPLICADO: "ICCID duplicado",
    FLAG_VEICULO_DESATIVADO: "Veículo desativado",
}

with col_f2:
    flags_selecionadas = st.multiselect(
        "Filtrar por critério",
        options=flags_disponiveis,
        format_func=lambda f: nomes_flags.get(f, f),
        default=[],
    )

# Aplica filtros
df_exibir = df_auditoria.copy()
if apenas_suspeitos:
    df_exibir = df_exibir[df_exibir["suspeito"]]
for flag in flags_selecionadas:
    df_exibir = df_exibir[df_exibir[flag]]

st.caption(f"Exibindo **{len(df_exibir):,}** de **{total:,}** registros.")

# ---------------------------------------------------------------------------
# Tabela de resultados
# ---------------------------------------------------------------------------
st.subheader("📊 Resultados da Auditoria")

# Coluna 'suspeito' e flags como primeiras colunas de destaque
colunas_flags = ["suspeito"] + [f for f in FLAGS_AUDITORIA if f in df_exibir.columns]
colunas_dados = [c for c in df_exibir.columns if c not in colunas_flags]
df_exibir_ordenado = df_exibir[colunas_flags + colunas_dados]

st.dataframe(
    df_exibir_ordenado,
    use_container_width=True,
    height=500,
    column_config={
        "suspeito": st.column_config.CheckboxColumn("⚠️ Suspeito"),
        FLAG_DISPOSITIVO_INATIVO: st.column_config.CheckboxColumn("Inativo"),
        FLAG_SEM_PLACA: st.column_config.CheckboxColumn("Sem Placa"),
        FLAG_SEM_GPS_RECENTE: st.column_config.CheckboxColumn("Sem GPS"),
        FLAG_SEM_CHIP: st.column_config.CheckboxColumn("Sem Chip"),
        FLAG_IMEI_DUPLICADO: st.column_config.CheckboxColumn("IMEI Dup."),
        FLAG_ICCID_DUPLICADO: st.column_config.CheckboxColumn("ICCID Dup."),
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
        use_container_width=True,
    )

col_e3, col_e4 = st.columns(2)
with col_e4:
    st.download_button(
        label="⬇️ Baixar Excel (.xlsx)",
        data=para_excel_bytes(df_export),
        file_name="auditoria_cobranca_m2m.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

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
            st.dataframe(df_d, use_container_width=True)
        else:
            st.info("Nenhum dado de dispositivos carregado.")
    with aba_veic:
        df_v = st.session_state.get("df_veiculos")
        if df_v is not None and not df_v.empty:
            st.dataframe(df_v, use_container_width=True)
        else:
            st.info("Nenhum dado de veículos carregado.")
    with aba_chips:
        df_c = st.session_state.get("df_chips")
        if df_c is not None and not df_c.empty:
            st.dataframe(df_c, use_container_width=True)
        else:
            st.info("Nenhum dado de chips carregado.")
    with aba_usr:
        df_u = st.session_state.get("df_usuarios")
        if df_u is not None and not df_u.empty:
            st.dataframe(df_u, use_container_width=True)
        else:
            st.info("Nenhum dado de usuários carregado (relatório opcional).")

# ---------------------------------------------------------------------------
# Rodapé
# ---------------------------------------------------------------------------
st.divider()
st.caption(
    "Auditoria de Cobrança M2M · "
    "Os dados são processados localmente e não são enviados a nenhum servidor externo."
)
