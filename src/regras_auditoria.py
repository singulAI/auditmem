"""Regras de auditoria para identificação de cobranças irregulares M2M."""

from datetime import datetime, timedelta
import pandas as pd
from src.config import VALOR_INATIVO, LIMITE_GPS_DIAS


MOTIVO_INATIVO = "Dispositivo inativo"
MOTIVO_SEM_PLACA = "Sem placa vinculada"
MOTIVO_SEM_GPS = f"Sem GPS há mais de {LIMITE_GPS_DIAS} dias"
MOTIVO_SEM_CHIP = "Sem chip vinculado"
MOTIVO_DUPLICADO = "IMEI duplicado"
MOTIVO_VEICULO_DESATIVADO = "Veículo desativado"
MOTIVO_CHIP_SEM_DISPOSITIVO = "Chip sem dispositivo vinculado"


def aplicar_regras(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica as regras de auditoria e retorna o DataFrame com colunas de auditoria.

    Colunas adicionadas:
    - ``auditoria_motivos``: lista de motivos separados por "; ".
    - ``auditoria_pendencia``: True se houver ao menos um motivo.
    - ``auditoria_critico``: True se o motivo for considerado crítico.

    Parameters
    ----------
    df:
        DataFrame cruzado de dispositivos.

    Returns
    -------
    pd.DataFrame
        DataFrame com colunas de auditoria adicionadas.
    """
    resultado = df.copy()
    resultado["auditoria_motivos"] = ""

    resultado = _regra_dispositivo_inativo(resultado)
    resultado = _regra_sem_placa(resultado)
    resultado = _regra_sem_gps(resultado)
    resultado = _regra_sem_chip(resultado)
    resultado = _regra_imei_duplicado(resultado)
    resultado = _regra_veiculo_desativado(resultado)

    resultado["auditoria_pendencia"] = resultado["auditoria_motivos"].str.len() > 0
    resultado["auditoria_critico"] = resultado["auditoria_motivos"].apply(
        lambda m: any(
            motivo in m
            for motivo in [MOTIVO_INATIVO, MOTIVO_DUPLICADO, MOTIVO_VEICULO_DESATIVADO]
        )
    )
    return resultado


def _adicionar_motivo(df: pd.DataFrame, mascara: pd.Series, motivo: str) -> pd.DataFrame:
    """Adiciona um motivo de auditoria nas linhas indicadas pela máscara."""
    tem_motivo = df["auditoria_motivos"].str.len() > 0
    df.loc[mascara & tem_motivo, "auditoria_motivos"] += "; " + motivo
    df.loc[mascara & ~tem_motivo, "auditoria_motivos"] = motivo
    return df


def _regra_dispositivo_inativo(df: pd.DataFrame) -> pd.DataFrame:
    """Marca dispositivos cujo estado de ativação é inativo."""
    if "ativo" not in df.columns:
        return df
    mascara = df["ativo"].isin(VALOR_INATIVO)
    return _adicionar_motivo(df, mascara, MOTIVO_INATIVO)


def _regra_sem_placa(df: pd.DataFrame) -> pd.DataFrame:
    """Marca dispositivos sem placa vinculada."""
    if "placa" not in df.columns:
        return df
    mascara = df["placa"].fillna("").isin(["", "-"])
    return _adicionar_motivo(df, mascara, MOTIVO_SEM_PLACA)


def _regra_sem_gps(df: pd.DataFrame) -> pd.DataFrame:
    """Marca dispositivos sem conexão GPS há mais de LIMITE_GPS_DIAS dias."""
    col_gps = None
    for c in ["gps_data", "Última data de conexão do GPS", "Última data do GPS"]:
        if c in df.columns:
            col_gps = c
            break
    if col_gps is None:
        return df

    limite = datetime.now() - timedelta(days=LIMITE_GPS_DIAS)
    mascara = df[col_gps].apply(lambda v: _data_ausente_ou_antiga(v, limite))
    return _adicionar_motivo(df, mascara, MOTIVO_SEM_GPS)


def _data_ausente_ou_antiga(valor, limite: datetime) -> bool:
    """Retorna True se a data for ausente ('-', vazia) ou anterior ao limite."""
    if pd.isna(valor) or str(valor).strip() in ("-", "", "None"):
        return True
    for fmt in ("%d/%m/%Y, %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            data = datetime.strptime(str(valor).strip(), fmt)
            return data < limite
        except ValueError:
            continue
    return True


def _regra_sem_chip(df: pd.DataFrame) -> pd.DataFrame:
    """Marca dispositivos sem chip vinculado (ICCID vazio)."""
    col_chip = None
    for c in ["chip_serie", "serie"]:
        if c in df.columns:
            col_chip = c
            break
    if col_chip is None:
        return df
    mascara = df[col_chip].fillna("").isin(["", "-"])
    return _adicionar_motivo(df, mascara, MOTIVO_SEM_CHIP)


def _regra_imei_duplicado(df: pd.DataFrame) -> pd.DataFrame:
    """Marca IMEIs que aparecem mais de uma vez."""
    if "imei" not in df.columns:
        return df
    imei_valido = df["imei"].fillna("").replace("", pd.NA).dropna()
    duplicados = imei_valido[imei_valido.duplicated(keep=False)].index
    mascara = df.index.isin(duplicados)
    return _adicionar_motivo(df, mascara, MOTIVO_DUPLICADO)


def _regra_veiculo_desativado(df: pd.DataFrame) -> pd.DataFrame:
    """Marca dispositivos vinculados a veículos com data de desativação preenchida."""
    col_desativ = None
    for c in ["desativacao", "Data de desativação do veículo", "Data de desativação"]:
        if c in df.columns:
            col_desativ = c
            break
    if col_desativ is None:
        return df
    mascara = ~df[col_desativ].fillna("").isin(["", "-", "None"])
    return _adicionar_motivo(df, mascara, MOTIVO_VEICULO_DESATIVADO)


def resumo_auditoria(df: pd.DataFrame) -> dict:
    """Retorna um dicionário com contagens por motivo de auditoria."""
    motivos = [
        MOTIVO_INATIVO,
        MOTIVO_SEM_PLACA,
        MOTIVO_SEM_GPS,
        MOTIVO_SEM_CHIP,
        MOTIVO_DUPLICADO,
        MOTIVO_VEICULO_DESATIVADO,
    ]
    contagens = {}
    if "auditoria_motivos" not in df.columns:
        return contagens
    for m in motivos:
        contagens[m] = df["auditoria_motivos"].str.contains(m, regex=False).sum()
    contagens["Total com pendência"] = df["auditoria_pendencia"].sum() if "auditoria_pendencia" in df.columns else 0
    contagens["Total crítico"] = df["auditoria_critico"].sum() if "auditoria_critico" in df.columns else 0
    return contagens
