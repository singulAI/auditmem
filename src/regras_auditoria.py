"""
Módulo de regras de auditoria de cobrança M2M.

Cada função identifica um tipo de inconsistência e adiciona uma coluna
de flag booleana ao DataFrame. A função `aplicar_todas_regras` aplica
todas as regras em sequência e retorna o DataFrame anotado.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from src.config import (
    DIAS_SEM_GPS,
    FLAG_DISPOSITIVO_INATIVO,
    FLAG_ICCID_DUPLICADO,
    FLAG_IMEI_DUPLICADO,
    FLAG_SEM_CHIP,
    FLAG_SEM_GPS_RECENTE,
    FLAG_SEM_PLACA,
    FLAG_VEICULO_DESATIVADO,
    VALORES_ATIVO,
    COL_DISP_ATIVO,
    COL_DISP_DATA_GPS,
    COL_DISP_ICCID,
    COL_DISP_IMEI,
    COL_DISP_PLACA,
    COL_VEIC_DATA_DESATIVACAO,
)


# ---------------------------------------------------------------------------
# Regras individuais
# ---------------------------------------------------------------------------

def identificar_dispositivos_inativos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Marca dispositivos cujo campo de ativação indica estado inativo.

    A coluna ``dispositivo_ativo`` é comparada contra o conjunto
    ``VALORES_ATIVO`` (insensível a maiúsculas/minúsculas).
    Dispositivos com campo vazio ou ausente são considerados inativos.
    """
    df = df.copy()
    if COL_DISP_ATIVO in df.columns:
        df[FLAG_DISPOSITIVO_INATIVO] = ~df[COL_DISP_ATIVO].apply(
            lambda v: str(v).strip().lower() in VALORES_ATIVO
            if pd.notna(v) and str(v).strip() != ""
            else False
        )
    else:
        df[FLAG_DISPOSITIVO_INATIVO] = True
    return df


def identificar_sem_placa(df: pd.DataFrame) -> pd.DataFrame:
    """
    Marca dispositivos sem placa de veículo vinculada.
    """
    df = df.copy()
    if COL_DISP_PLACA in df.columns:
        df[FLAG_SEM_PLACA] = df[COL_DISP_PLACA].apply(
            lambda v: str(v).strip() == "" if pd.notna(v) else True
        )
    else:
        df[FLAG_SEM_PLACA] = True
    return df


def identificar_sem_gps_recente(
    df: pd.DataFrame,
    dias: int = DIAS_SEM_GPS,
    data_referencia: datetime | None = None,
) -> pd.DataFrame:
    """
    Marca dispositivos sem conexão GPS nos últimos ``dias`` dias.

    Se a coluna de data GPS não existir ou não puder ser parseada,
    o dispositivo é marcado como sem GPS recente.

    Parameters
    ----------
    df:
        DataFrame de dispositivos.
    dias:
        Limiar de dias sem GPS para considerar inativo.
    data_referencia:
        Data de referência para o cálculo (padrão: agora em UTC).
    """
    df = df.copy()
    if data_referencia is None:
        data_referencia = datetime.now(tz=timezone.utc)

    if COL_DISP_DATA_GPS in df.columns:
        # Converte para datetime ciente de fuso (UTC).
        # Datas sem informação de timezone são assumidas como UTC.
        # Se os dados originais estiverem em outro fuso horário, ajuste
        # a conversão antes de chamar esta função.
        datas = pd.to_datetime(df[COL_DISP_DATA_GPS], errors="coerce", utc=True)
        df[FLAG_SEM_GPS_RECENTE] = datas.apply(
            lambda d: True if pd.isna(d) else (data_referencia - d).days > dias
        )
    else:
        df[FLAG_SEM_GPS_RECENTE] = True
    return df


def identificar_sem_chip(df: pd.DataFrame) -> pd.DataFrame:
    """
    Marca dispositivos sem chip (ICCID ausente ou vazio).
    """
    df = df.copy()
    if COL_DISP_ICCID in df.columns:
        df[FLAG_SEM_CHIP] = df[COL_DISP_ICCID].apply(
            lambda v: str(v).strip() == "" if pd.notna(v) else True
        )
    else:
        df[FLAG_SEM_CHIP] = True
    return df


def identificar_imeis_duplicados(df: pd.DataFrame) -> pd.DataFrame:
    """
    Marca registros cujo IMEI aparece mais de uma vez no DataFrame.
    IMEIs em branco não são marcados como duplicados.
    """
    df = df.copy()
    if COL_DISP_IMEI in df.columns:
        imei_valido = df[COL_DISP_IMEI].apply(
            lambda v: str(v).strip() != "" and pd.notna(v)
        )
        duplicados = df[COL_DISP_IMEI].duplicated(keep=False) & imei_valido
        df[FLAG_IMEI_DUPLICADO] = duplicados
    else:
        df[FLAG_IMEI_DUPLICADO] = False
    return df


def identificar_iccids_duplicados(df: pd.DataFrame) -> pd.DataFrame:
    """
    Marca registros cujo ICCID aparece mais de uma vez no DataFrame.
    ICCIDs em branco não são marcados como duplicados.
    """
    df = df.copy()
    if COL_DISP_ICCID in df.columns:
        iccid_valido = df[COL_DISP_ICCID].apply(
            lambda v: str(v).strip() != "" and pd.notna(v)
        )
        duplicados = df[COL_DISP_ICCID].duplicated(keep=False) & iccid_valido
        df[FLAG_ICCID_DUPLICADO] = duplicados
    else:
        df[FLAG_ICCID_DUPLICADO] = False
    return df


def identificar_veiculos_desativados(df: pd.DataFrame) -> pd.DataFrame:
    """
    Marca registros vinculados a veículos com data de desativação preenchida.
    """
    df = df.copy()
    if COL_VEIC_DATA_DESATIVACAO in df.columns:
        df[FLAG_VEICULO_DESATIVADO] = df[COL_VEIC_DATA_DESATIVACAO].apply(
            lambda v: pd.notna(v) and str(v).strip() not in ("", "NaT", "nan")
        )
    else:
        df[FLAG_VEICULO_DESATIVADO] = False
    return df


# ---------------------------------------------------------------------------
# Aplicação de todas as regras
# ---------------------------------------------------------------------------

def aplicar_todas_regras(
    df: pd.DataFrame,
    dias_sem_gps: int = DIAS_SEM_GPS,
    data_referencia: datetime | None = None,
) -> pd.DataFrame:
    """
    Aplica todas as regras de auditoria ao DataFrame e adiciona coluna
    ``suspeito`` indicando se ao menos uma flag foi ativada.

    Parameters
    ----------
    df:
        DataFrame consolidado (saída de ``cruzar_completo``).
    dias_sem_gps:
        Limiar de dias sem GPS.
    data_referencia:
        Data de referência (padrão: agora em UTC).

    Returns
    -------
    DataFrame com colunas de flag adicionadas.
    """
    df = identificar_dispositivos_inativos(df)
    df = identificar_sem_placa(df)
    df = identificar_sem_gps_recente(df, dias=dias_sem_gps, data_referencia=data_referencia)
    df = identificar_sem_chip(df)
    df = identificar_imeis_duplicados(df)
    df = identificar_iccids_duplicados(df)
    df = identificar_veiculos_desativados(df)

    flags = [
        FLAG_DISPOSITIVO_INATIVO,
        FLAG_SEM_PLACA,
        FLAG_SEM_GPS_RECENTE,
        FLAG_SEM_CHIP,
        FLAG_IMEI_DUPLICADO,
        FLAG_ICCID_DUPLICADO,
        FLAG_VEICULO_DESATIVADO,
    ]
    flags_presentes = [f for f in flags if f in df.columns]
    if flags_presentes:
        df["suspeito"] = df[flags_presentes].any(axis=1)
    else:
        df["suspeito"] = False

    return df.reset_index(drop=True)
