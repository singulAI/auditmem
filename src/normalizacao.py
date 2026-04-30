"""Normalização de campos nos DataFrames de auditoria M2M."""

import re
import pandas as pd
from src.config import (
    COLUNAS_DISPOSITIVOS,
    COLUNAS_CHIPS,
    COLUNAS_VEICULOS,
    COLUNAS_COBRANCA,
)

# Número máximo de dígitos preservados em um telefone normalizado
# (DDI 2 + DDD 2 + número 9 = 13 dígitos no padrão brasileiro internacional)
MAX_PHONE_DIGITS = 13


def _encontrar_coluna(df: pd.DataFrame, alternativas: list[str]) -> str | None:
    """Retorna o primeiro nome de coluna encontrado no DataFrame dentre as alternativas."""
    for nome in alternativas:
        if nome in df.columns:
            return nome
    return None


def _mapear_colunas(df: pd.DataFrame, mapeamento: dict) -> pd.DataFrame:
    """Renomeia colunas do DataFrame conforme mapeamento {alias: [alternativas]}."""
    renomear = {}
    for alias, alternativas in mapeamento.items():
        coluna = _encontrar_coluna(df, alternativas)
        if coluna and coluna != alias:
            renomear[coluna] = alias
    return df.rename(columns=renomear)


def _limpar_numerico(valor: str) -> str:
    """Remove caracteres não numéricos de uma string."""
    if pd.isna(valor) or valor in ("-", ""):
        return ""
    return re.sub(r"\D", "", str(valor))


def _normalizar_imei(valor: str) -> str:
    """Normaliza IMEI: mantém apenas dígitos."""
    return _limpar_numerico(valor)


def _normalizar_iccid(valor: str) -> str:
    """Normaliza ICCID/número de série do chip: mantém apenas dígitos."""
    return _limpar_numerico(valor)


def _normalizar_telefone(valor: str) -> str:
    """Normaliza número de telefone: remove DDI/DDDs opcionais, mantém dígitos."""
    num = _limpar_numerico(valor)
    if len(num) > MAX_PHONE_DIGITS:
        num = num[-MAX_PHONE_DIGITS:]
    return num


def _normalizar_placa(valor: str) -> str:
    """Normaliza placa: maiúsculo, remove espaços e hífens."""
    if pd.isna(valor) or valor in ("-", ""):
        return ""
    return re.sub(r"[\s\-]", "", str(valor)).upper()


def normalizar_dispositivos(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza o DataFrame de dispositivos."""
    df = _mapear_colunas(df, COLUNAS_DISPOSITIVOS)
    if "imei" in df.columns:
        df["imei"] = df["imei"].apply(_normalizar_imei)
    if "chip_serie" in df.columns:
        df["chip_serie"] = df["chip_serie"].apply(_normalizar_iccid)
    if "chip_telefone" in df.columns:
        df["chip_telefone"] = df["chip_telefone"].apply(_normalizar_telefone)
    if "placa" in df.columns:
        df["placa"] = df["placa"].apply(_normalizar_placa)
    return df


def normalizar_chips(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza o DataFrame de chips."""
    df = _mapear_colunas(df, COLUNAS_CHIPS)
    if "serie" in df.columns:
        df["serie"] = df["serie"].apply(_normalizar_iccid)
    if "telefone" in df.columns:
        df["telefone"] = df["telefone"].apply(_normalizar_telefone)
    if "imei" in df.columns:
        df["imei"] = df["imei"].apply(_normalizar_imei)
    return df


def normalizar_veiculos(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza o DataFrame de veículos."""
    df = _mapear_colunas(df, COLUNAS_VEICULOS)
    if "placa" in df.columns:
        df["placa"] = df["placa"].apply(_normalizar_placa)
    if "imei" in df.columns:
        df["imei"] = df["imei"].apply(_normalizar_imei)
    return df


def normalizar_cobranca(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza o DataFrame de cobrança M2M."""
    df = _mapear_colunas(df, COLUNAS_COBRANCA)
    if "telefone" in df.columns:
        df["telefone"] = df["telefone"].apply(_normalizar_telefone)
    if "valor" in df.columns:
        df["valor"] = pd.to_numeric(
            df["valor"].astype(str).str.replace(",", "."), errors="coerce"
        )
    return df
