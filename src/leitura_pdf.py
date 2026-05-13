"""Leitura de arquivos PDF e CSV para o dashboard de auditoria M2M."""

import io
import pandas as pd
import pdfplumber


def ler_arquivo(arquivo) -> pd.DataFrame:
    """Lê um arquivo carregado (PDF ou CSV) e retorna um DataFrame.

    Parameters
    ----------
    arquivo:
        Objeto de arquivo (Streamlit UploadedFile ou path-like).

    Returns
    -------
    pd.DataFrame
        Dados extraídos do arquivo.
    """
    nome = getattr(arquivo, "name", str(arquivo))
    if nome.lower().endswith(".pdf"):
        return _ler_pdf(arquivo)
    elif nome.lower().endswith(".csv"):
        return _ler_csv(arquivo)
    else:
        raise ValueError(f"Formato não suportado: {nome}. Use PDF ou CSV.")


def _ler_pdf(arquivo) -> pd.DataFrame:
    """Extrai tabelas de um PDF usando pdfplumber."""
    conteudo = arquivo.read() if hasattr(arquivo, "read") else open(arquivo, "rb").read()
    frames = []
    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        for pagina in pdf.pages:
            tabelas = pagina.extract_tables()
            for tabela in tabelas:
                if not tabela:
                    continue
                cabecalho = tabela[0]
                linhas = tabela[1:]
                df = pd.DataFrame(linhas, columns=cabecalho)
                frames.append(df)
    if not frames:
        return pd.DataFrame()
    resultado = pd.concat(frames, ignore_index=True)
    resultado = resultado.dropna(how="all")
    return resultado


def _ler_csv(arquivo) -> pd.DataFrame:
    """Lê um arquivo CSV com detecção automática de encoding e separador."""
    conteudo = arquivo.read() if hasattr(arquivo, "read") else open(arquivo, "rb").read()
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            texto = conteudo.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        texto = conteudo.decode("latin-1", errors="replace")

    for sep in (",", ";", "\t"):
        try:
            df = pd.read_csv(io.StringIO(texto), sep=sep, dtype=str)
            if df.shape[1] > 1:
                return df.fillna("-")
        except Exception:
            continue
    return pd.read_csv(io.StringIO(texto), dtype=str).fillna("-")
