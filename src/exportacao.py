"""
Módulo de exportação dos resultados da auditoria.

Suporta exportação para CSV e Excel (xlsx) com formatação básica.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Union

import pandas as pd

from src.config import ARQUIVO_SAIDA_CSV, ARQUIVO_SAIDA_EXCEL


# ---------------------------------------------------------------------------
# Exportação para disco
# ---------------------------------------------------------------------------

def exportar_csv(
    df: pd.DataFrame,
    caminho: Union[str, Path] = ARQUIVO_SAIDA_CSV,
    encoding: str = "utf-8-sig",
) -> Path:
    """
    Exporta o DataFrame para CSV.

    Parameters
    ----------
    df:
        DataFrame a exportar.
    caminho:
        Caminho de destino.
    encoding:
        Codificação do arquivo (padrão ``utf-8-sig`` para compatibilidade
        com Excel no Windows).

    Returns
    -------
    Path do arquivo gerado.
    """
    destino = Path(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(destino, index=False, encoding=encoding)
    return destino


def exportar_excel(
    df: pd.DataFrame,
    caminho: Union[str, Path] = ARQUIVO_SAIDA_EXCEL,
    nome_aba: str = "Auditoria M2M",
) -> Path:
    """
    Exporta o DataFrame para Excel (.xlsx) com formatação básica.

    A primeira linha (cabeçalho) é negritada e a largura das colunas
    é ajustada automaticamente.

    Parameters
    ----------
    df:
        DataFrame a exportar.
    caminho:
        Caminho de destino.
    nome_aba:
        Nome da aba no arquivo Excel.

    Returns
    -------
    Path do arquivo gerado.
    """
    destino = Path(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(destino, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name=nome_aba)
        workbook = writer.book
        worksheet = writer.sheets[nome_aba]

        # Formato para cabeçalho
        fmt_header = workbook.add_format({"bold": True, "bg_color": "#D9E1F2", "border": 1})

        # Reescreve cabeçalho com formatação
        for col_num, col_name in enumerate(df.columns):
            worksheet.write(0, col_num, col_name, fmt_header)

        # Ajusta largura das colunas
        for col_num, col_name in enumerate(df.columns):
            serie = df[col_name]
            max_conteudo = serie.map(lambda v: len(str(v)) if pd.notna(v) else 0).max()
            largura = max(len(str(col_name)), int(max_conteudo) if pd.notna(max_conteudo) else 0)
            largura = min(max(largura + 2, 10), 60)  # limita entre 10 e 60
            worksheet.set_column(col_num, col_num, largura)

    return destino


# ---------------------------------------------------------------------------
# Exportação para bytes (uso no Streamlit)
# ---------------------------------------------------------------------------

def para_csv_bytes(
    df: pd.DataFrame,
    encoding: str = "utf-8-sig",
) -> bytes:
    """Retorna o DataFrame serializado como bytes CSV."""
    return df.to_csv(index=False, encoding=encoding).encode(encoding)


def para_excel_bytes(df: pd.DataFrame, nome_aba: str = "Auditoria M2M") -> bytes:
    """Retorna o DataFrame serializado como bytes Excel (.xlsx)."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name=nome_aba)
        workbook = writer.book
        worksheet = writer.sheets[nome_aba]

        fmt_header = workbook.add_format({"bold": True, "bg_color": "#D9E1F2", "border": 1})
        for col_num, col_name in enumerate(df.columns):
            worksheet.write(0, col_num, col_name, fmt_header)

        for col_num, col_name in enumerate(df.columns):
            serie = df[col_name]
            max_conteudo = serie.map(lambda v: len(str(v)) if pd.notna(v) else 0).max()
            largura = max(len(str(col_name)), int(max_conteudo) if pd.notna(max_conteudo) else 0)
            largura = min(max(largura + 2, 10), 60)
            worksheet.set_column(col_num, col_num, largura)

    buffer.seek(0)
    return buffer.read()
