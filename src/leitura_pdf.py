"""
Módulo de leitura e extração de tabelas de arquivos PDF.

Utiliza pdfplumber para extrair tabelas de cada tipo de relatório
e retorna DataFrames normalizados.
"""

from __future__ import annotations

import io
import logging
from typing import Union

import pandas as pd
import pdfplumber

from src.config import (
    COLUNAS_CHIPS,
    COLUNAS_DISPOSITIVOS,
    COLUNAS_USUARIOS,
    COLUNAS_VEICULOS,
)
from src.normalizacao import (
    normalizar_dataframe_chips,
    normalizar_dataframe_dispositivos,
    normalizar_dataframe_veiculos,
)

logger = logging.getLogger(__name__)

# Tipo de fonte aceito: caminho (str/Path) ou bytes (upload Streamlit)
FontePDF = Union[str, bytes, io.IOBase]


# ---------------------------------------------------------------------------
# Utilitários internos
# ---------------------------------------------------------------------------

def _extrair_tabelas_pdf(fonte: FontePDF) -> list[pd.DataFrame]:
    """
    Abre um PDF e extrai todas as tabelas encontradas em todas as páginas.
    Retorna uma lista de DataFrames (um por tabela).
    """
    frames: list[pd.DataFrame] = []

    with pdfplumber.open(fonte) as pdf:
        for pagina in pdf.pages:
            tabelas = pagina.extract_tables()
            for tabela in tabelas:
                if not tabela:
                    continue
                # Primeira linha como cabeçalho
                cabecalho = [str(c).strip() if c else f"unnamed_column_{i}"
                             for i, c in enumerate(tabela[0])]
                linhas = tabela[1:]
                df = pd.DataFrame(linhas, columns=cabecalho)
                frames.append(df)

    return frames


def _combinar_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Combina múltiplos DataFrames (mesma estrutura) em um só."""
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _mapear_colunas(df: pd.DataFrame, mapeamento: dict[str, list[str]]) -> pd.DataFrame:
    """
    Renomeia colunas do DataFrame de acordo com o mapeamento.
    O mapeamento tem a forma {nome_canonico: [possíveis nomes no PDF]}.
    """
    rename_map: dict[str, str] = {}
    colunas_lower = {c.lower().strip(): c for c in df.columns}

    for nome_canonico, variantes in mapeamento.items():
        for variante in variantes:
            chave = variante.lower().strip()
            if chave in colunas_lower:
                rename_map[colunas_lower[chave]] = nome_canonico
                break

    return df.rename(columns=rename_map)


# ---------------------------------------------------------------------------
# Mapeamentos de colunas por tipo de relatório
# ---------------------------------------------------------------------------

MAPEAMENTO_DISPOSITIVOS: dict[str, list[str]] = {
    "nome_dispositivo": ["nome do dispositivo", "dispositivo", "nome"],
    "imei": ["imei", "imei do dispositivo"],
    "dispositivo_ativo": ["ativo", "estado", "status", "ativação", "ativacao", "active"],
    "iccid": ["iccid", "número de série do chip", "numero de serie do chip", "serial chip"],
    "telefone_chip": ["telefone", "número de telefone", "numero de telefone", "phone"],
    "operadora": ["operadora", "carrier", "operador"],
    "ultima_conexao_gps": ["última conexão gps", "ultima conexao gps", "ultima conexão", "last gps"],
    "data_ultimo_gps": ["data do gps", "data gps", "data último gps", "data ultimo gps", "gps date"],
    "placa": ["placa", "placa do veículo", "placa do veiculo", "plate"],
    "chassi": ["chassi", "chassis"],
    "usuario": ["usuário", "usuario", "user"],
}

MAPEAMENTO_VEICULOS: dict[str, list[str]] = {
    "placa": ["placa", "placa do veículo", "placa do veiculo", "plate"],
    "chassi": ["chassi", "chassis"],
    "marca": ["marca", "brand"],
    "modelo": ["modelo", "model"],
    "ano": ["ano", "year"],
    "data_desativacao": ["data de desativação", "data de desativacao", "desativado em", "deactivation date"],
    "usuario": ["usuário", "usuario", "user"],
    "nome_dispositivo": ["nome do dispositivo", "dispositivo", "device name"],
    "imei": ["imei", "imei do dispositivo"],
}

MAPEAMENTO_CHIPS: dict[str, list[str]] = {
    "iccid": ["iccid", "número de série", "numero de serie", "serial"],
    "telefone": ["telefone", "número de telefone", "numero de telefone", "phone"],
    "imsi": ["imsi"],
    "operadora": ["operadora", "carrier"],
    "provedor_servico": ["provedor de serviço", "provedor de servico", "provedor", "service provider"],
    "origem_softruck": ["origem softruck", "origem", "origin"],
    "nome_dispositivo": ["nome do dispositivo", "dispositivo", "device"],
    "imei": ["imei"],
    "empresa": ["empresa", "company"],
}

MAPEAMENTO_USUARIOS: dict[str, list[str]] = {
    "usuario": ["usuário", "usuario", "username", "login"],
    "email": ["e-mail", "email"],
    "nome_completo": ["nome completo", "nome", "full name"],
    "telefones": ["telefone", "telefones", "phone"],
    "cpf": ["cpf"],
    "data_criacao": ["data de criação", "data de criacao", "created at", "criado em"],
    "data_desativacao": ["data de desativação", "data de desativacao", "deactivated at"],
    "empresa": ["empresa", "company"],
    "papel": ["papel", "role", "perfil"],
}


# ---------------------------------------------------------------------------
# Funções públicas
# ---------------------------------------------------------------------------

def ler_pdf_dispositivos(fonte: FontePDF) -> pd.DataFrame:
    """
    Lê um PDF de dispositivos e retorna DataFrame normalizado.

    Parameters
    ----------
    fonte:
        Caminho do arquivo, objeto de bytes ou file-like object.
    """
    frames = _extrair_tabelas_pdf(fonte)
    df = _combinar_frames(frames)
    if df.empty:
        logger.warning("Nenhuma tabela encontrada no PDF de dispositivos.")
        return pd.DataFrame(columns=COLUNAS_DISPOSITIVOS)
    df = _mapear_colunas(df, MAPEAMENTO_DISPOSITIVOS)
    return normalizar_dataframe_dispositivos(df)


def ler_pdf_veiculos(fonte: FontePDF) -> pd.DataFrame:
    """
    Lê um PDF de veículos e retorna DataFrame normalizado.
    """
    frames = _extrair_tabelas_pdf(fonte)
    df = _combinar_frames(frames)
    if df.empty:
        logger.warning("Nenhuma tabela encontrada no PDF de veículos.")
        return pd.DataFrame(columns=COLUNAS_VEICULOS)
    df = _mapear_colunas(df, MAPEAMENTO_VEICULOS)
    return normalizar_dataframe_veiculos(df)


def ler_pdf_chips(fonte: FontePDF) -> pd.DataFrame:
    """
    Lê um PDF de chips e retorna DataFrame normalizado.
    """
    frames = _extrair_tabelas_pdf(fonte)
    df = _combinar_frames(frames)
    if df.empty:
        logger.warning("Nenhuma tabela encontrada no PDF de chips.")
        return pd.DataFrame(columns=COLUNAS_CHIPS)
    df = _mapear_colunas(df, MAPEAMENTO_CHIPS)
    return normalizar_dataframe_chips(df)


def ler_pdf_usuarios(fonte: FontePDF) -> pd.DataFrame:
    """
    Lê um PDF de usuários e retorna DataFrame.
    (Relatório opcional — sem normalização específica de campo.)
    """
    frames = _extrair_tabelas_pdf(fonte)
    df = _combinar_frames(frames)
    if df.empty:
        logger.warning("Nenhuma tabela encontrada no PDF de usuários.")
        return pd.DataFrame(columns=COLUNAS_USUARIOS)
    df = _mapear_colunas(df, MAPEAMENTO_USUARIOS)
    return df.reset_index(drop=True)
