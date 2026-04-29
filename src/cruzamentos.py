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
    COL_VEIC_DATA_DESATIVACAO,
    COL_VEIC_MARCA,
    COL_VEIC_MODELO,
    COL_VEIC_PLACA,
)


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
