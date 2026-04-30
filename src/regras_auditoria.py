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
    COL_AUD_CHIP_ENCONTRADO,
    COL_AUD_MOTIVOS_CADASTRO,
    COL_AUD_MOTIVOS_COBRANCA,
    COL_AUD_RISCO_CADASTRO,
    COL_AUD_RISCO_COBRANCA,
    COL_AUD_STATUS_DISPOSITIVO,
    DIAS_SEM_GPS,
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
    FLAGS_CADASTRAIS,
    FLAGS_COBRANCA,
    VALORES_ATIVO,
    VALORES_SIPROV_INADIMPLENTE,
    VALORES_SIPROV_INATIVO,
    COL_SIP_BENEFICIO_SITUACAO,
    COL_SIP_ENCONTRADO,
    COL_SIP_STATUS_REFERENCIA,
    COL_DISP_ATIVO,
    COL_DISP_DATA_GPS,
    COL_DISP_ICCID,
    COL_DISP_IMEI,
    COL_DISP_PLACA,
    COL_DISP_TELEFONE,
    COL_DISP_TELEFONE_CLIENTE,
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
    sem_iccid = pd.Series([True] * len(df), index=df.index)
    if COL_DISP_ICCID in df.columns:
        sem_iccid = df[COL_DISP_ICCID].apply(
            lambda v: str(v).strip() == "" if pd.notna(v) else True
        )

    sem_telefone_chip = pd.Series([True] * len(df), index=df.index)
    if COL_DISP_TELEFONE in df.columns:
        sem_telefone_chip = df[COL_DISP_TELEFONE].apply(
            lambda v: str(v).strip() == "" if pd.notna(v) else True
        )

    sem_identificador_chip = sem_iccid & sem_telefone_chip

    if COL_AUD_CHIP_ENCONTRADO in df.columns:
        chip_nao_encontrado = ~df[COL_AUD_CHIP_ENCONTRADO].fillna(False).astype(bool)
        df[FLAG_SEM_CHIP] = sem_identificador_chip | chip_nao_encontrado
    else:
        df[FLAG_SEM_CHIP] = sem_identificador_chip
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


def identificar_telefones_duplicados(df: pd.DataFrame) -> pd.DataFrame:
    """
    Marca registros cujo telefone do chip aparece mais de uma vez.
    Telefones vazios não são marcados como duplicados.
    """
    df = df.copy()
    if COL_DISP_TELEFONE in df.columns:
        telefone_valido = df[COL_DISP_TELEFONE].apply(
            lambda v: str(v).strip() != "" and pd.notna(v)
        )
        duplicados = df[COL_DISP_TELEFONE].duplicated(keep=False) & telefone_valido
        df[FLAG_TELEFONE_DUPLICADO] = duplicados
    else:
        df[FLAG_TELEFONE_DUPLICADO] = False
    return df


def identificar_telefones_cliente_duplicados(df: pd.DataFrame) -> pd.DataFrame:
    """
    Marca duplicidade de telefone de cliente (uso cadastral, não técnico de chip).
    """
    df = df.copy()
    if COL_DISP_TELEFONE_CLIENTE in df.columns:
        telefone_valido = df[COL_DISP_TELEFONE_CLIENTE].apply(
            lambda v: str(v).strip() != "" and pd.notna(v)
        )
        duplicados = df[COL_DISP_TELEFONE_CLIENTE].duplicated(keep=False) & telefone_valido
        df[FLAG_TELEFONE_CLIENTE_DUPLICADO] = duplicados
    else:
        df[FLAG_TELEFONE_CLIENTE_DUPLICADO] = False
    return df


def identificar_placas_duplicadas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Marca registros cuja placa aparece mais de uma vez.
    Placas vazias não são marcadas como duplicadas.
    """
    df = df.copy()
    if COL_DISP_PLACA in df.columns:
        placa_valida = df[COL_DISP_PLACA].apply(
            lambda v: str(v).strip() != "" and pd.notna(v)
        )
        duplicados = df[COL_DISP_PLACA].duplicated(keep=False) & placa_valida
        df[FLAG_PLACA_DUPLICADA] = duplicados
    else:
        df[FLAG_PLACA_DUPLICADA] = False
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


def classificar_status_dispositivo(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cria a coluna de status textual do dispositivo para facilitar a auditoria.
    """
    df = df.copy()
    if FLAG_DISPOSITIVO_INATIVO in df.columns:
        df[COL_AUD_STATUS_DISPOSITIVO] = df[FLAG_DISPOSITIVO_INATIVO].map(
            lambda inativo: "INATIVO" if bool(inativo) else "ATIVO"
        )
    else:
        df[COL_AUD_STATUS_DISPOSITIVO] = "INDEFINIDO"
    return df


def _normalizar_status_siprov(valor: object) -> str:
    texto = str(valor).strip().lower() if pd.notna(valor) else ""
    if not texto:
        return "INDEFINIDO"

    if any(chave in texto for chave in VALORES_SIPROV_INADIMPLENTE):
        return "INADIMPLENTE"
    if any(chave in texto for chave in VALORES_SIPROV_INATIVO):
        return "INATIVO"
    if "ativ" in texto or "adimpl" in texto:
        return "ATIVO"

    return "INDEFINIDO"


def classificar_status_siprov(df: pd.DataFrame) -> pd.DataFrame:
    """Classifica status oficial SIPROV para cruzamento com o prestador."""
    df = df.copy()
    if COL_SIP_BENEFICIO_SITUACAO in df.columns:
        df[COL_SIP_STATUS_REFERENCIA] = df[COL_SIP_BENEFICIO_SITUACAO].apply(_normalizar_status_siprov)
    elif COL_SIP_STATUS_REFERENCIA not in df.columns:
        df[COL_SIP_STATUS_REFERENCIA] = "INDEFINIDO"
    return df


def identificar_divergencias_siprov(df: pd.DataFrame) -> pd.DataFrame:
    """
    Marca divergências considerando SIPROV como referência primária.
    """
    df = df.copy()
    encontrou = df[COL_SIP_ENCONTRADO].fillna(False).astype(bool) if COL_SIP_ENCONTRADO in df.columns else pd.Series([False] * len(df), index=df.index)
    status_disp = df[COL_AUD_STATUS_DISPOSITIVO].astype(str).str.upper() if COL_AUD_STATUS_DISPOSITIVO in df.columns else pd.Series(["INDEFINIDO"] * len(df), index=df.index)
    status_sip = df[COL_SIP_STATUS_REFERENCIA].astype(str).str.upper() if COL_SIP_STATUS_REFERENCIA in df.columns else pd.Series(["INDEFINIDO"] * len(df), index=df.index)

    df[FLAG_SIPROV_SEM_CADASTRO] = ~encontrou
    df[FLAG_SIPROV_INATIVO_ATIVO_PRESTADOR] = encontrou & status_disp.eq("ATIVO") & status_sip.eq("INATIVO")
    df[FLAG_SIPROV_INADIMPLENTE_ATIVO_PRESTADOR] = encontrou & status_disp.eq("ATIVO") & status_sip.eq("INADIMPLENTE")
    return df


def _montar_motivos(df: pd.DataFrame, mapa_labels: dict[str, str], flags: list[str]) -> pd.Series:
    """Monta texto de motivos com base nas flags ativas em cada linha."""
    flags_presentes = [f for f in flags if f in df.columns]
    if not flags_presentes:
        return pd.Series([""] * len(df), index=df.index)

    def _motivos_linha(linha: pd.Series) -> str:
        ativos = [mapa_labels[f] for f in flags_presentes if bool(linha.get(f, False))]
        return "; ".join(ativos)

    return df.apply(_motivos_linha, axis=1)


def classificar_riscos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Classifica risco de cobrança e risco cadastral em eixos independentes.
    """
    df = df.copy()

    flags_cobranca_presentes = [f for f in FLAGS_COBRANCA if f in df.columns]
    flags_cadastro_presentes = [f for f in FLAGS_CADASTRAIS if f in df.columns]

    if flags_cobranca_presentes:
        risco_cobranca = df[flags_cobranca_presentes].any(axis=1)
    else:
        risco_cobranca = pd.Series([False] * len(df), index=df.index)

    if flags_cadastro_presentes:
        risco_cadastro = df[flags_cadastro_presentes].any(axis=1)
    else:
        risco_cadastro = pd.Series([False] * len(df), index=df.index)

    df[COL_AUD_RISCO_COBRANCA] = risco_cobranca.map(lambda v: "ALTO" if bool(v) else "BAIXO")
    df[COL_AUD_RISCO_CADASTRO] = risco_cadastro.map(lambda v: "ALTO" if bool(v) else "BAIXO")

    mapa_cobranca = {
        FLAG_DISPOSITIVO_INATIVO: "Dispositivo inativo",
        FLAG_SEM_PLACA: "Sem placa",
        FLAG_SEM_GPS_RECENTE: "Sem GPS recente",
        FLAG_SEM_CHIP: "Sem chip",
        FLAG_IMEI_DUPLICADO: "IMEI duplicado",
        FLAG_ICCID_DUPLICADO: "ICCID duplicado",
        FLAG_TELEFONE_DUPLICADO: "Telefone do chip duplicado",
        FLAG_PLACA_DUPLICADA: "Placa duplicada",
        FLAG_VEICULO_DESATIVADO: "Veículo desativado",
        FLAG_SIPROV_SEM_CADASTRO: "Sem correspondência no SIPROV",
        FLAG_SIPROV_INATIVO_ATIVO_PRESTADOR: "SIPROV inativo e prestador ativo",
        FLAG_SIPROV_INADIMPLENTE_ATIVO_PRESTADOR: "SIPROV inadimplente e prestador ativo",
    }
    mapa_cadastro = {
        FLAG_TELEFONE_CLIENTE_DUPLICADO: "Telefone do cliente duplicado",
    }

    df[COL_AUD_MOTIVOS_COBRANCA] = _montar_motivos(df, mapa_cobranca, FLAGS_COBRANCA)
    df[COL_AUD_MOTIVOS_CADASTRO] = _montar_motivos(df, mapa_cadastro, FLAGS_CADASTRAIS)
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
    df = identificar_telefones_duplicados(df)
    df = identificar_telefones_cliente_duplicados(df)
    df = identificar_placas_duplicadas(df)
    df = identificar_veiculos_desativados(df)
    df = classificar_status_dispositivo(df)
    df = classificar_status_siprov(df)
    df = identificar_divergencias_siprov(df)
    df = classificar_riscos(df)

    flags = FLAGS_COBRANCA
    flags_presentes = [f for f in flags if f in df.columns]
    if flags_presentes:
        df["suspeito"] = df[flags_presentes].any(axis=1)
    else:
        df["suspeito"] = False

    return df.reset_index(drop=True)
