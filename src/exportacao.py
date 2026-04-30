"""Exportação dos resultados de auditoria para CSV e Excel."""

import io
import pandas as pd


def exportar_csv(df: pd.DataFrame) -> bytes:
    """Serializa o DataFrame para bytes no formato CSV (UTF-8 com BOM).

    Parameters
    ----------
    df:
        DataFrame a ser exportado.

    Returns
    -------
    bytes
        Conteúdo CSV codificado em UTF-8 com BOM para compatibilidade com Excel.
    """
    return df.to_csv(index=False).encode("utf-8-sig")


def exportar_excel(df: pd.DataFrame) -> bytes:
    """Serializa o DataFrame para bytes no formato Excel (.xlsx).

    Parameters
    ----------
    df:
        DataFrame a ser exportado.

    Returns
    -------
    bytes
        Conteúdo do arquivo Excel.
    """
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Auditoria")
        workbook = writer.book
        worksheet = writer.sheets["Auditoria"]

        fmt_header = workbook.add_format(
            {"bold": True, "bg_color": "#1f3864", "font_color": "#ffffff", "border": 1}
        )
        fmt_critico = workbook.add_format({"bg_color": "#ffcccc", "border": 1})
        fmt_pendente = workbook.add_format({"bg_color": "#fff2cc", "border": 1})
        fmt_normal = workbook.add_format({"border": 1})

        for col_idx, col_name in enumerate(df.columns):
            worksheet.write(0, col_idx, col_name, fmt_header)

        col_critico = df.columns.get_loc("auditoria_critico") if "auditoria_critico" in df.columns else None
        col_pendente = df.columns.get_loc("auditoria_pendencia") if "auditoria_pendencia" in df.columns else None

        for row_idx, row in enumerate(df.itertuples(index=False), start=1):
            is_critico = getattr(row, "auditoria_critico", False) if col_critico is not None else False
            is_pendente = getattr(row, "auditoria_pendencia", False) if col_pendente is not None else False
            fmt = fmt_critico if is_critico else (fmt_pendente if is_pendente else fmt_normal)
            for col_idx, value in enumerate(row):
                worksheet.write(row_idx, col_idx, "" if pd.isna(value) else value, fmt)

        for col_idx, col_name in enumerate(df.columns):
            max_len = max(
                df[col_name].astype(str).str.len().max() if len(df) > 0 else 0,
                len(col_name),
            )
            worksheet.set_column(col_idx, col_idx, min(max_len + 2, 50))

    return buffer.getvalue()
