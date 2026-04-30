"""
Módulo de cruzamento de dados entre dispositivos, veículos e chips.

Funções de merge/join que produzem uma visão consolidada para auditoria.
"""

from __future__ import annotations

import pandas as pd

from src.config import (
    COL_AUD_CHIP_ENCONTRADO,
    COL_CHIP_ICCID,
    COL_CHIP_IMEI,
    COL_CHIP_OPERADORA,
    COL_CHIP_TELEFONE,
    COL_DISP_CHASSI,
    COL_DISP_ICCID,
    COL_DISP_IMEI,
    COL_DISP_NOME,
    COL_DISP_PLACA,
    COL_DISP_TELEFONE,
    COL_DISP_USUARIO,
    COL_SIP_ASSOCIADO_CPF_CNPJ,
    COL_SIP_ASSOCIADO_NOME,
    COL_SIP_BENEFICIO_SITUACAO,
    COL_SIP_CHAVE_CRUZAMENTO,
    COL_SIP_CONFIANCA_CRUZAMENTO,
    COL_SIP_ENCONTRADO,
    COL_SIP_PLACA,
    COL_SIP_STATUS_REFERENCIA,
    COL_USR_CPF,
    COL_USR_USUARIO,
    COL_VEIC_DATA_DESATIVACAO,
    COL_VEIC_MARCA,
    COL_VEIC_MODELO,
    COL_VEIC_PLACA,
)
from src.normalizacao import normalizar_digitos, normalizar_nome, normalizar_placa


def _serie_chave(df: pd.DataFrame, coluna: str) -> pd.Series:
    """Retorna série normalizada para uso como chave de cruzamento."""
    if coluna not in df.columns:
        return pd.Series([""] * len(df), index=df.index)
    return df[coluna].astype(str).str.strip()


def _escolher_chave_chip(df_disp: pd.DataFrame, df_chips: pd.DataFrame) -> tuple[str, str] | None:
    """Escolhe automaticamente a melhor chave para cruzar dispositivos e chips."""
    candidatos = [
        (COL_DISP_ICCID, COL_CHIP_ICCID),
        (COL_DISP_TELEFONE, COL_CHIP_TELEFONE),
    ]

    melhor: tuple[str, str] | None = None
    melhor_score: tuple[int, int, int] | None = None

    for col_disp, col_chip in candidatos:
        if col_disp not in df_disp.columns or col_chip not in df_chips.columns:
            continue

        serie_disp = _serie_chave(df_disp, col_disp)
        serie_chip = _serie_chave(df_chips, col_chip)

        set_disp = {v for v in serie_disp.tolist() if v}
        set_chip = {v for v in serie_chip.tolist() if v}
        intersecao = len(set_disp & set_chip)
        score = (intersecao, len(set_chip), len(set_disp))

        if melhor_score is None or score > melhor_score:
            melhor_score = score
            melhor = (col_disp, col_chip)

    return melhor


def cruzar_dispositivos_veiculos(
    df_disp: pd.DataFrame,
    df_veic: pd.DataFrame,
) -> pd.DataFrame:
    """
    Cruza dispositivos com veículos pelo campo placa.

    Adiciona colunas do veículo (marca, modelo, data_desativacao) ao DataFrame
    de dispositivos. Usa left join para manter todos os dispositivos.

    Parameters
    ----------
    df_disp:
        DataFrame de dispositivos (normalizado).
    df_veic:
        DataFrame de veículos (normalizado).

    Returns
    -------
    DataFrame enriquecido com dados do veículo.
    """
    if df_disp.empty:
        return df_disp.copy()

    colunas_veic = [COL_VEIC_PLACA]
    for col in (COL_VEIC_MARCA, COL_VEIC_MODELO, COL_VEIC_DATA_DESATIVACAO):
        if col in df_veic.columns:
            colunas_veic.append(col)

    df_veic_sel = df_veic[colunas_veic].copy()
    if COL_VEIC_PLACA in df_veic_sel.columns:
        # Evita multiplicação de linhas quando há mais de um veículo por placa.
        df_veic_sel = df_veic_sel.drop_duplicates(subset=[COL_VEIC_PLACA])

    # Evita duplicar coluna 'placa' já existente no dispositivo
    merged = df_disp.merge(
        df_veic_sel,
        left_on=COL_DISP_PLACA,
        right_on=COL_VEIC_PLACA,
        how="left",
        suffixes=("", "_veic"),
    )

    # Remove coluna 'placa_veic' redundante se presente
    merged = merged.loc[:, ~merged.columns.duplicated()]
    placa_veic_col = f"{COL_VEIC_PLACA}_veic"
    if placa_veic_col in merged.columns:
        merged = merged.drop(columns=[placa_veic_col])

    return merged.reset_index(drop=True)


def cruzar_dispositivos_chips(
    df_disp: pd.DataFrame,
    df_chips: pd.DataFrame,
) -> pd.DataFrame:
    """
    Cruza dispositivos com chips pelo campo ICCID.

    Adiciona colunas do chip (telefone_chip, operadora do chip) ao DataFrame
    de dispositivos, para validação cruzada. Usa left join.

    Parameters
    ----------
    df_disp:
        DataFrame de dispositivos (normalizado).
    df_chips:
        DataFrame de chips (normalizado).

    Returns
    -------
    DataFrame enriquecido com dados do chip.
    """
    if df_disp.empty or df_chips.empty:
        return df_disp.copy()

    chave = _escolher_chave_chip(df_disp, df_chips)
    if chave is None:
        resultado = df_disp.copy()
        resultado[COL_AUD_CHIP_ENCONTRADO] = False
        return resultado.reset_index(drop=True)

    col_disp, col_chip = chave

    colunas_chip = [col_chip]
    if COL_CHIP_ICCID in df_chips.columns and COL_CHIP_ICCID not in colunas_chip:
        colunas_chip.append(COL_CHIP_ICCID)
    for col in (COL_CHIP_TELEFONE, COL_CHIP_OPERADORA):
        if col in df_chips.columns:
            colunas_chip.append(col)
    colunas_chip = list(dict.fromkeys(colunas_chip))

    df_chips_sel = df_chips[colunas_chip].copy()
    chave_chip = df_chips_sel[col_chip].astype(str).str.strip()
    df_chips_sel = df_chips_sel[chave_chip != ""].drop_duplicates(subset=[col_chip]).copy()
    df_chips_sel[COL_AUD_CHIP_ENCONTRADO] = True

    merged = df_disp.merge(
        df_chips_sel,
        left_on=col_disp,
        right_on=col_chip,
        how="left",
        suffixes=("", "_chip_ref"),
    )

    # Remove colunas duplicadas (iccid_chip_ref se criar)
    chave_ref = f"{col_chip}_chip_ref"
    if chave_ref in merged.columns:
        merged = merged.drop(columns=[chave_ref])

    if COL_AUD_CHIP_ENCONTRADO in merged.columns:
        merged[COL_AUD_CHIP_ENCONTRADO] = merged[COL_AUD_CHIP_ENCONTRADO].fillna(False).astype(bool)
    else:
        merged[COL_AUD_CHIP_ENCONTRADO] = False

    return merged.reset_index(drop=True)


def cruzar_completo(
    df_disp: pd.DataFrame,
    df_veic: pd.DataFrame | None = None,
    df_chips: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Realiza o cruzamento completo: dispositivos + veículos + chips.

    Primeiro cruza dispositivos com veículos, depois com chips.
    Qualquer um dos DataFrames secundários pode ser None (ou vazio),
    caso em que o cruzamento correspondente é ignorado.

    Parameters
    ----------
    df_disp:
        DataFrame de dispositivos (normalizado). Obrigatório.
    df_veic:
        DataFrame de veículos (normalizado). Opcional.
    df_chips:
        DataFrame de chips (normalizado). Opcional.

    Returns
    -------
    DataFrame consolidado pronto para auditoria.
    """
    resultado = df_disp.copy()

    if df_veic is not None and not df_veic.empty:
        resultado = cruzar_dispositivos_veiculos(resultado, df_veic)

    if df_chips is not None and not df_chips.empty:
        resultado = cruzar_dispositivos_chips(resultado, df_chips)

    return resultado.reset_index(drop=True)


def listar_dispositivos_sem_chip(df_disp: pd.DataFrame) -> pd.DataFrame:
    """
    Retorna os dispositivos sem ICCID (sem chip vinculado).
    """
    if df_disp.empty or COL_DISP_ICCID not in df_disp.columns:
        return pd.DataFrame(columns=df_disp.columns)

    sem_chip = df_disp[df_disp[COL_DISP_ICCID].astype(str).str.strip() == ""].copy()
    return sem_chip.reset_index(drop=True)


def listar_chips_sem_dispositivo(
    df_disp: pd.DataFrame,
    df_chips: pd.DataFrame,
) -> pd.DataFrame:
    """
    Retorna chips sem vínculo com dispositivos usando a melhor chave disponível
    (ICCID ou telefone do chip).
    """
    if df_chips.empty:
        return pd.DataFrame(columns=df_chips.columns)

    chave = _escolher_chave_chip(df_disp, df_chips)
    if chave is None:
        return pd.DataFrame(columns=df_chips.columns)
    col_disp, col_chip = chave

    chaves_disp = set()
    if not df_disp.empty and col_disp in df_disp.columns:
        chaves_disp = {
            v
            for v in df_disp[col_disp].astype(str).str.strip().tolist()
            if v
        }

    serie_chips = df_chips[col_chip].astype(str).str.strip()
    mascara = serie_chips.ne("") & ~serie_chips.isin(chaves_disp)
    chips_sem_disp = df_chips[mascara].copy()
    return chips_sem_disp.reset_index(drop=True)


def _serie_vazia(df: pd.DataFrame) -> pd.Series:
    return pd.Series([""] * len(df), index=df.index)


def cruzar_com_siprov(
    df_auditoria_base: pd.DataFrame,
    df_siprov: pd.DataFrame,
    df_usuarios: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Enriquecimento do consolidado com a base oficial SIPROV.

    Prioridade de chave:
    1) Placa
    2) CPF/CNPJ via relatório de usuários (usuario -> cpf)
    3) Nome do usuário/dispositivo
    """
    resultado = df_auditoria_base.copy()

    if df_siprov is None or df_siprov.empty:
        resultado[COL_SIP_ENCONTRADO] = False
        resultado[COL_SIP_CHAVE_CRUZAMENTO] = "sem_base_siprov"
        resultado[COL_SIP_CONFIANCA_CRUZAMENTO] = "N/A"
        return resultado.reset_index(drop=True)

    sip = df_siprov.copy()

    # Colunas de apoio no consolidado
    resultado[COL_SIP_ENCONTRADO] = False
    resultado[COL_SIP_CHAVE_CRUZAMENTO] = "sem_match"
    resultado[COL_SIP_CONFIANCA_CRUZAMENTO] = "BAIXA"

    # Gera chaves normalizadas de consulta
    sip["_k_placa"] = _serie_chave(sip, COL_SIP_PLACA).apply(normalizar_placa)
    sip["_k_doc"] = _serie_chave(sip, COL_SIP_ASSOCIADO_CPF_CNPJ).apply(normalizar_digitos)
    sip["_k_nome"] = _serie_chave(sip, COL_SIP_ASSOCIADO_NOME).apply(normalizar_nome)

    for c in sip.columns:
        if c not in resultado.columns:
            resultado[c] = pd.NA

    # 1) Match por placa
    resultado["_k_placa"] = _serie_chave(resultado, COL_DISP_PLACA).apply(normalizar_placa)
    idx_placa = (
        sip[sip["_k_placa"].ne("")]
        .drop_duplicates(subset=["_k_placa"])
        .set_index("_k_placa")
    )
    match_placa = resultado["_k_placa"].map(idx_placa.index.to_series()) if not idx_placa.empty else _serie_vazia(resultado)
    mask_placa = match_placa.notna() & resultado["_k_placa"].ne("")

    if mask_placa.any() and not idx_placa.empty:
        linhas = resultado.loc[mask_placa, "_k_placa"].map(idx_placa.to_dict(orient="index"))
        linhas_df = pd.DataFrame(linhas.tolist(), index=resultado.index[mask_placa])
        for col in linhas_df.columns:
            resultado.loc[mask_placa, col] = linhas_df[col]
        resultado.loc[mask_placa, COL_SIP_ENCONTRADO] = True
        resultado.loc[mask_placa, COL_SIP_CHAVE_CRUZAMENTO] = "placa"
        resultado.loc[mask_placa, COL_SIP_CONFIANCA_CRUZAMENTO] = "ALTA"

    # 2) Match por CPF/CNPJ via usuários (somente para os não casados)
    resultado["_k_doc"] = ""
    if df_usuarios is not None and not df_usuarios.empty and COL_USR_USUARIO in df_usuarios.columns and COL_USR_CPF in df_usuarios.columns:
        usr = df_usuarios.copy()
        usr["_k_user"] = _serie_chave(usr, COL_USR_USUARIO).apply(normalizar_nome)
        usr["_k_doc"] = _serie_chave(usr, COL_USR_CPF).apply(normalizar_digitos)
        mapa_user_doc = (
            usr[usr["_k_user"].ne("") & usr["_k_doc"].ne("")]
            .drop_duplicates(subset=["_k_user"])
            .set_index("_k_user")["_k_doc"]
            .to_dict()
        )
        resultado["_k_user"] = _serie_chave(resultado, COL_DISP_USUARIO).apply(normalizar_nome)
        resultado["_k_doc"] = resultado["_k_user"].map(mapa_user_doc).fillna("")
    else:
        resultado["_k_user"] = _serie_chave(resultado, COL_DISP_USUARIO).apply(normalizar_nome)

    idx_doc = (
        sip[sip["_k_doc"].ne("")]
        .drop_duplicates(subset=["_k_doc"])
        .set_index("_k_doc")
    )
    mask_doc = (~resultado[COL_SIP_ENCONTRADO]) & resultado["_k_doc"].ne("") & resultado["_k_doc"].isin(idx_doc.index)
    if mask_doc.any() and not idx_doc.empty:
        linhas = resultado.loc[mask_doc, "_k_doc"].map(idx_doc.to_dict(orient="index"))
        linhas_df = pd.DataFrame(linhas.tolist(), index=resultado.index[mask_doc])
        for col in linhas_df.columns:
            resultado.loc[mask_doc, col] = linhas_df[col]
        resultado.loc[mask_doc, COL_SIP_ENCONTRADO] = True
        resultado.loc[mask_doc, COL_SIP_CHAVE_CRUZAMENTO] = "cpf_cnpj"
        resultado.loc[mask_doc, COL_SIP_CONFIANCA_CRUZAMENTO] = "ALTA"

    # 3) Match por nome
    idx_nome = (
        sip[sip["_k_nome"].ne("")]
        .drop_duplicates(subset=["_k_nome"])
        .set_index("_k_nome")
    )
    mask_nome = (~resultado[COL_SIP_ENCONTRADO]) & resultado["_k_user"].ne("") & resultado["_k_user"].isin(idx_nome.index)
    if mask_nome.any() and not idx_nome.empty:
        linhas = resultado.loc[mask_nome, "_k_user"].map(idx_nome.to_dict(orient="index"))
        linhas_df = pd.DataFrame(linhas.tolist(), index=resultado.index[mask_nome])
        for col in linhas_df.columns:
            resultado.loc[mask_nome, col] = linhas_df[col]
        resultado.loc[mask_nome, COL_SIP_ENCONTRADO] = True
        resultado.loc[mask_nome, COL_SIP_CHAVE_CRUZAMENTO] = "nome"
        resultado.loc[mask_nome, COL_SIP_CONFIANCA_CRUZAMENTO] = "MEDIA"

    if COL_SIP_STATUS_REFERENCIA not in resultado.columns:
        resultado[COL_SIP_STATUS_REFERENCIA] = pd.NA

    # Fallback inicial: se não houver status derivado, usa a situação bruta do benefício.
    if COL_SIP_BENEFICIO_SITUACAO in resultado.columns:
        mask_sem_status = resultado[COL_SIP_STATUS_REFERENCIA].isna() | (resultado[COL_SIP_STATUS_REFERENCIA].astype(str).str.strip() == "")
        resultado.loc[mask_sem_status, COL_SIP_STATUS_REFERENCIA] = resultado.loc[mask_sem_status, COL_SIP_BENEFICIO_SITUACAO]

    return resultado.drop(columns=[c for c in ["_k_placa", "_k_doc", "_k_nome", "_k_user"] if c in resultado.columns]).reset_index(drop=True)
