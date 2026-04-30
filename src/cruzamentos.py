"""Cruzamento de dados entre dispositivos, chips, veículos e cobrança."""

import pandas as pd


def cruzar_dados(
    df_disp: pd.DataFrame | None = None,
    df_chips: pd.DataFrame | None = None,
    df_veic: pd.DataFrame | None = None,
    df_cob: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Cruza os dados disponíveis e retorna um DataFrame unificado para auditoria.

    Parameters
    ----------
    df_disp:
        DataFrame de dispositivos (normalizado).
    df_chips:
        DataFrame de chips (normalizado).
    df_veic:
        DataFrame de veículos (normalizado).
    df_cob:
        DataFrame de cobrança M2M (normalizado).

    Returns
    -------
    pd.DataFrame
        DataFrame cruzado com informações de cobrança, dispositivo, chip e veículo.
    """
    if df_disp is None or df_disp.empty:
        return pd.DataFrame()

    base = df_disp.copy()

    # Cruzar com chips por ICCID/série ou por telefone
    if df_chips is not None and not df_chips.empty:
        base = _cruzar_chips(base, df_chips)

    # Cruzar com veículos por placa
    if df_veic is not None and not df_veic.empty:
        base = _cruzar_veiculos(base, df_veic)

    # Cruzar com cobrança por telefone do chip
    if df_cob is not None and not df_cob.empty:
        base = _cruzar_cobranca(base, df_cob)

    return base


def _cruzar_chips(base: pd.DataFrame, df_chips: pd.DataFrame) -> pd.DataFrame:
    """Junta informações de chips na base de dispositivos."""
    cols_chip = {}

    if "serie" in df_chips.columns and "chip_serie" in base.columns:
        df_c = df_chips.rename(columns={"serie": "chip_serie"})
        chave = "chip_serie"
    elif "telefone" in df_chips.columns and "chip_telefone" in base.columns:
        df_c = df_chips.rename(columns={"telefone": "chip_telefone"})
        chave = "chip_telefone"
    else:
        return base

    colunas_extra = [c for c in df_c.columns if c not in base.columns and c != chave]
    if not colunas_extra:
        return base

    df_c = df_c[[chave] + colunas_extra].drop_duplicates(subset=[chave])
    return base.merge(df_c, on=chave, how="left")


def _cruzar_veiculos(base: pd.DataFrame, df_veic: pd.DataFrame) -> pd.DataFrame:
    """Junta informações de veículos na base de dispositivos por placa."""
    if "placa" not in base.columns or "placa" not in df_veic.columns:
        return base

    colunas_extra = [
        c for c in df_veic.columns if c not in base.columns and c != "placa"
    ]
    if not colunas_extra:
        return base

    df_v = df_veic[["placa"] + colunas_extra].drop_duplicates(subset=["placa"])
    return base.merge(df_v, on="placa", how="left")


def _cruzar_cobranca(base: pd.DataFrame, df_cob: pd.DataFrame) -> pd.DataFrame:
    """Junta informações de cobrança na base de dispositivos por telefone do chip."""
    chave_base = "chip_telefone" if "chip_telefone" in base.columns else None
    chave_cob = "telefone" if "telefone" in df_cob.columns else None

    if chave_base is None or chave_cob is None:
        return base

    colunas_extra = [
        c for c in df_cob.columns if c not in base.columns and c != chave_cob
    ]
    if not colunas_extra:
        return base

    df_c = df_cob[[chave_cob] + colunas_extra].drop_duplicates(subset=[chave_cob])
    df_c = df_c.rename(columns={chave_cob: chave_base})
    return base.merge(df_c, on=chave_base, how="left")
