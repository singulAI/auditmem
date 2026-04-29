"""
Módulo de cruzamento de dados entre dispositivos, veículos e chips.

Funções de merge/join que produzem uma visão consolidada para auditoria.
"""

from __future__ import annotations

import pandas as pd

from src.config import (
    COL_CHIP_ICCID,
    COL_CHIP_IMEI,
    COL_CHIP_OPERADORA,
    COL_CHIP_TELEFONE,
    COL_DISP_CHASSI,
    COL_DISP_ICCID,
    COL_DISP_IMEI,
    COL_DISP_NOME,
    COL_DISP_PLACA,
    COL_DISP_USUARIO,
    COL_VEIC_DATA_DESATIVACAO,
    COL_VEIC_MARCA,
    COL_VEIC_MODELO,
    COL_VEIC_PLACA,
)


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

    colunas_chip = [COL_CHIP_ICCID]
    for col in (COL_CHIP_TELEFONE, COL_CHIP_OPERADORA):
        if col in df_chips.columns:
            colunas_chip.append(col)

    df_chips_sel = df_chips[colunas_chip].drop_duplicates(
        subset=[COL_CHIP_ICCID]
    ).copy()

    merged = df_disp.merge(
        df_chips_sel,
        left_on=COL_DISP_ICCID,
        right_on=COL_CHIP_ICCID,
        how="left",
        suffixes=("", "_chip_ref"),
    )

    # Remove colunas duplicadas (iccid_chip_ref se criar)
    iccid_ref = f"{COL_CHIP_ICCID}_chip_ref"
    if iccid_ref in merged.columns:
        merged = merged.drop(columns=[iccid_ref])

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
