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


def para_pdf_bytes(
    df: pd.DataFrame,
    titulo: str = "Relatorio Completo de Auditoria M2M",
    subtitulo: str | None = None,
    max_linhas: int = 250,
) -> bytes:
    """Gera um PDF tabular do resultado atual da auditoria."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.8 * cm,
        rightMargin=0.8 * cm,
        topMargin=0.8 * cm,
        bottomMargin=0.8 * cm,
    )

    styles = getSampleStyleSheet()
    elementos = [Paragraph(titulo, styles["Title"])]
    if subtitulo:
        elementos.append(Paragraph(subtitulo, styles["Normal"]))
    elementos.append(Spacer(1, 0.35 * cm))

    if df.empty:
        elementos.append(Paragraph("Nenhum registro disponivel para exportacao.", styles["Normal"]))
        doc.build(elementos)
        buffer.seek(0)
        return buffer.read()

    df_pdf = df.head(max_linhas).copy()
    colunas = [str(c) for c in df_pdf.columns]
    dados = [colunas]
    for _, linha in df_pdf.iterrows():
        dados.append([
            "" if pd.isna(valor) else str(valor)[:80]
            for valor in linha.tolist()
        ])

    largura_total = 27 * cm
    largura_coluna = largura_total / max(len(colunas), 1)
    tabela = Table(dados, repeatRows=1, colWidths=[largura_coluna] * len(colunas))
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elementos.append(tabela)

    if len(df) > max_linhas:
        elementos.append(Spacer(1, 0.25 * cm))
        elementos.append(
            Paragraph(
                f"PDF limitado aos primeiros {max_linhas} registros de um total de {len(df)}.",
                styles["Italic"],
            )
        )

    doc.build(elementos)
    buffer.seek(0)
    return buffer.read()
