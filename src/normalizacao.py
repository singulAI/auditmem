"""
Módulo de normalização de dados.

Funções para padronizar valores de IMEI, ICCID, telefone e placa,
além de normalizar DataFrames completos de cada tipo de relatório.
"""

import re

import pandas as pd

from src.config import (
    COL_CHIP_ICCID,
    COL_CHIP_IMEI,
    COL_CHIP_TELEFONE,
    COL_DISP_DATA_GPS,
    COL_DISP_ICCID,
    COL_DISP_IMEI,
    COL_DISP_PLACA,
    COL_DISP_TELEFONE,
    COL_VEIC_IMEI,
    COL_VEIC_PLACA,
    COLUNAS_CHIPS,
    COLUNAS_DISPOSITIVOS,
    COLUNAS_VEICULOS,
)


# ---------------------------------------------------------------------------
# Funções atômicas de normalização
# ---------------------------------------------------------------------------

def normalizar_digitos(valor) -> str:
    """Remove tudo que não é dígito e retorna string limpa (ou vazio).

    Função base compartilhada por IMEI, ICCID e telefone.
    """
    if pd.isna(valor) or str(valor).strip() == "":
        return ""
    return re.sub(r"\D", "", str(valor).strip())


def normalizar_imei(valor) -> str:
    """Remove caracteres não-numéricos do IMEI."""
    return normalizar_digitos(valor)


def normalizar_iccid(valor) -> str:
    """Remove caracteres não-numéricos do ICCID."""
    return normalizar_digitos(valor)


def normalizar_telefone(valor) -> str:
    """Remove caracteres não-numéricos do número de telefone."""
    return normalizar_digitos(valor)


def normalizar_placa(valor) -> str:
    """Remove espaços, hífens e converte para maiúsculas."""
    if pd.isna(valor) or str(valor).strip() == "":
        return ""
    return re.sub(r"[\s\-]", "", str(valor).strip()).upper()


def normalizar_texto(valor) -> str:
    """Strip simples + lower para campos de texto genérico."""
    if pd.isna(valor):
        return ""
    return str(valor).strip()


# ---------------------------------------------------------------------------
# Normalização de DataFrames
# ---------------------------------------------------------------------------

def _garantir_colunas(df: pd.DataFrame, colunas: list) -> pd.DataFrame:
    """Adiciona colunas ausentes com valor vazio para evitar KeyError."""
    for col in colunas:
        if col not in df.columns:
            df[col] = ""
    return df


def normalizar_dataframe_dispositivos(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza um DataFrame de dispositivos."""
    df = df.copy()
    df = _garantir_colunas(df, COLUNAS_DISPOSITIVOS)
    df[COL_DISP_IMEI] = df[COL_DISP_IMEI].apply(normalizar_imei)
    df[COL_DISP_ICCID] = df[COL_DISP_ICCID].apply(normalizar_iccid)
    df[COL_DISP_TELEFONE] = df[COL_DISP_TELEFONE].apply(normalizar_telefone)
    df[COL_DISP_PLACA] = df[COL_DISP_PLACA].apply(normalizar_placa)
    # Tenta converter coluna de data do GPS para datetime
    if COL_DISP_DATA_GPS in df.columns:
        df[COL_DISP_DATA_GPS] = pd.to_datetime(
            df[COL_DISP_DATA_GPS], errors="coerce", dayfirst=True
        )
    return df.reset_index(drop=True)


def normalizar_dataframe_veiculos(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza um DataFrame de veículos."""
    df = df.copy()
    df = _garantir_colunas(df, COLUNAS_VEICULOS)
    df[COL_VEIC_IMEI] = df[COL_VEIC_IMEI].apply(normalizar_imei)
    df[COL_VEIC_PLACA] = df[COL_VEIC_PLACA].apply(normalizar_placa)
    return df.reset_index(drop=True)


def normalizar_dataframe_chips(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza um DataFrame de chips."""
    df = df.copy()
    df = _garantir_colunas(df, COLUNAS_CHIPS)
    df[COL_CHIP_IMEI] = df[COL_CHIP_IMEI].apply(normalizar_imei)
    df[COL_CHIP_ICCID] = df[COL_CHIP_ICCID].apply(normalizar_iccid)
    df[COL_CHIP_TELEFONE] = df[COL_CHIP_TELEFONE].apply(normalizar_telefone)
    return df.reset_index(drop=True)
