"""
Módulo de leitura e extração de tabelas de arquivos PDF.

Utiliza pdfplumber para extrair tabelas de cada tipo de relatório
e retorna DataFrames normalizados.
"""

from __future__ import annotations

import io
import json
import logging
from typing import Union

import pandas as pd
import pdfplumber

from src.config import (
    COLUNAS_CHIPS,
    COLUNAS_DISPOSITIVOS,
    COLUNAS_SIPROV,
    COLUNAS_USUARIOS,
    COLUNAS_VEICULOS,
)
from src.normalizacao import (
    normalizar_dataframe_chips,
    normalizar_dataframe_dispositivos,
    normalizar_dataframe_siprov,
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


def _ler_conteudo_bytes(fonte: FontePDF) -> bytes:
    """Lê a fonte em bytes para processar CSV/HTML de forma uniforme."""
    if isinstance(fonte, str):
        with open(fonte, "rb") as f:
            return f.read()
    if isinstance(fonte, (bytes, bytearray)):
        return bytes(fonte)
    if hasattr(fonte, "read"):
        try:
            fonte.seek(0)
        except Exception:
            pass
        conteudo = fonte.read()
        if isinstance(conteudo, str):
            return conteudo.encode("utf-8")
        return conteudo
    raise TypeError("Fonte inválida para leitura de arquivo")


def _extrair_tabelas_csv(fonte: FontePDF) -> list[pd.DataFrame]:
    """Lê CSV e retorna uma lista com um DataFrame."""
    conteudo = _ler_conteudo_bytes(fonte)
    for encoding in ("utf-8-sig", "utf-8", "latin1"):
        try:
            texto = conteudo.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        texto = conteudo.decode("utf-8", errors="ignore")

    df = pd.read_csv(io.StringIO(texto), dtype=str)
    return [df]


def _extrair_tabelas_html(fonte: FontePDF) -> list[pd.DataFrame]:
    """Lê HTML e retorna todas as tabelas encontradas."""
    conteudo = _ler_conteudo_bytes(fonte)
    for encoding in ("utf-8-sig", "utf-8", "latin1"):
        try:
            texto = conteudo.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        texto = conteudo.decode("utf-8", errors="ignore")

    tabelas = pd.read_html(io.StringIO(texto), displayed_only=False)
    return [df.astype(str) for df in tabelas]


def _detectar_linha_cabecalho(df: pd.DataFrame, limite_busca: int = 15) -> int:
    """Detecta a linha de cabeçalho em planilhas exportadas com título acima."""
    if df.empty:
        return 0

    melhor_idx = 0
    melhor_score = -1

    fim = min(limite_busca, len(df))
    for i in range(fim):
        linha = df.iloc[i]
        nao_nulos = sum(1 for v in linha.tolist() if pd.notna(v) and str(v).strip() != "")
        score = int(nao_nulos)
        if score > melhor_score:
            melhor_score = score
            melhor_idx = i

    return melhor_idx


def _extrair_tabelas_excel(fonte: FontePDF) -> list[pd.DataFrame]:
    """Lê planilhas Excel tratando cabeçalhos deslocados por títulos de relatório."""
    conteudo = _ler_conteudo_bytes(fonte)
    buffer = io.BytesIO(conteudo)

    frames: list[pd.DataFrame] = []
    planilhas = pd.read_excel(buffer, sheet_name=None, header=None)

    for df_raw in planilhas.values():
        if df_raw.empty:
            continue

        idx_header = _detectar_linha_cabecalho(df_raw)
        cabecalho = [str(v).strip() if pd.notna(v) else "" for v in df_raw.iloc[idx_header].tolist()]

        df = df_raw.iloc[idx_header + 1 :].copy()
        df.columns = cabecalho
        df = df.dropna(how="all")
        df = df.loc[:, [c for c in df.columns if str(c).strip() != ""]]

        if not df.empty:
            frames.append(df.reset_index(drop=True))

    return frames


def _extrair_tabelas_json(fonte: FontePDF) -> list[pd.DataFrame]:
    """Lê JSON no formato lista de objetos ou objeto com lista em chave principal."""
    conteudo = _ler_conteudo_bytes(fonte)
    texto = conteudo.decode("utf-8", errors="ignore")
    payload = json.loads(texto)

    if isinstance(payload, list):
        return [pd.DataFrame(payload)]

    if isinstance(payload, dict):
        for _, valor in payload.items():
            if isinstance(valor, list):
                return [pd.DataFrame(valor)]
        return [pd.DataFrame([payload])]

    return [pd.DataFrame()]


def _detectar_extensao_fonte(fonte: FontePDF) -> str:
    """Obtém a extensão do arquivo (quando disponível) para escolher o parser."""
    nome = ""
    if isinstance(fonte, str):
        nome = fonte
    elif hasattr(fonte, "name"):
        nome = str(getattr(fonte, "name"))

    if "." not in nome:
        return ""
    return nome.rsplit(".", 1)[-1].lower()


def _extrair_tabelas_arquivo(fonte: FontePDF) -> list[pd.DataFrame]:
    """Extrai tabelas conforme extensão da fonte (pdf/csv/html)."""
    ext = _detectar_extensao_fonte(fonte)
    if ext == "pdf":
        return _extrair_tabelas_pdf(fonte)
    if ext == "csv":
        return _extrair_tabelas_csv(fonte)
    if ext in {"html", "htm"}:
        return _extrair_tabelas_html(fonte)
    if ext in {"xlsx", "xls"}:
        return _extrair_tabelas_excel(fonte)
    if ext == "json":
        return _extrair_tabelas_json(fonte)

    # Fallback para manter compatibilidade quando extensão não estiver disponível.
    try:
        return _extrair_tabelas_pdf(fonte)
    except Exception:
        pass
    try:
        return _extrair_tabelas_csv(fonte)
    except Exception:
        pass
    try:
        return _extrair_tabelas_excel(fonte)
    except Exception:
        pass
    try:
        return _extrair_tabelas_json(fonte)
    except Exception:
        pass
    return _extrair_tabelas_html(fonte)


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
    "dispositivo_ativo": [
        "ativo",
        "estado",
        "status",
        "ativação",
        "ativacao",
        "active",
        "estado de ativação do dispositivo",
        "estado de ativacao do dispositivo",
    ],
    "iccid": ["iccid", "número de série do chip", "numero de serie do chip", "serial chip"],
    "telefone_chip": [
        "telefone",
        "número de telefone",
        "numero de telefone",
        "phone",
        "número de telefone do chip",
        "numero de telefone do chip",
        "telefone do chip",
        "linha do chip",
        "msisdn do chip",
    ],
    "telefone_cliente": [
        "telefones dos usuários",
        "telefones dos usuarios",
        "telefone dos usuários",
        "telefone dos usuarios",
        "telefone do usuário",
        "telefone do usuario",
        "telefone do cliente",
        "celular do cliente",
    ],
    "operadora": ["operadora", "carrier", "operador", "operadora do chip"],
    "ultima_conexao_gps": [
        "última conexão gps",
        "ultima conexao gps",
        "ultima conexão",
        "last gps",
        "última data de conexão do gps",
        "ultima data de conexao do gps",
    ],
    "data_ultimo_gps": [
        "data do gps",
        "data gps",
        "data último gps",
        "data ultimo gps",
        "gps date",
        "última data do gps",
        "ultima data do gps",
    ],
    "placa": ["placa", "placa do veículo", "placa do veiculo", "plate"],
    "chassi": ["chassi", "chassis", "chassi do veículo", "chassi do veiculo"],
    "usuario": ["usuário", "usuario", "user", "nomes dos usuários", "nomes dos usuarios"],
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
    "iccid": [
        "iccid",
        "número de série",
        "numero de serie",
        "serial",
        "número de série do chip",
        "numero de serie do chip",
        "login",
        "#",
    ],
    "telefone": [
        "telefone",
        "número de telefone",
        "numero de telefone",
        "phone",
        "número de telefone do chip",
        "numero de telefone do chip",
        "msisdn",
    ],
    "imsi": ["imsi"],
    "operadora": ["operadora", "carrier", "operadora do chip"],
    "provedor_servico": [
        "provedor de serviço",
        "provedor de servico",
        "provedor",
        "service provider",
        "provedor de serviço do chip",
        "provedor de servico do chip",
    ],
    "origem_softruck": ["origem softruck", "origem", "origin", "origem softruck do chip"],
    "nome_dispositivo": ["nome do dispositivo", "dispositivo", "device"],
    "imei": ["imei", "imei do dispositivo"],
    "empresa": ["empresa", "company", "nome da empresa"],
}

MAPEAMENTO_USUARIOS: dict[str, list[str]] = {
    "usuario": ["usuário", "usuario", "username", "login"],
    "email": ["e-mail", "email"],
    "nome_completo": ["nome completo", "nome", "full name"],
    "telefones": [
        "telefone",
        "telefones",
        "phone",
        "telefone 1 do usuário",
        "telefone 1 do usuario",
        "telefone 2 do usuário",
        "telefone 2 do usuario",
        "telefone do cliente",
        "celular do cliente",
    ],
    "cpf": ["cpf"],
    "data_criacao": ["data de criação", "data de criacao", "created at", "criado em"],
    "data_desativacao": ["data de desativação", "data de desativacao", "deactivated at"],
    "empresa": ["empresa", "company"],
    "papel": ["papel", "role", "perfil"],
}

MAPEAMENTO_SIPROV: dict[str, list[str]] = {
    "siprov_associado_nome": [
        "associado_nome_razao_social",
        "associado - nome/razão social",
        "associado - nome/razao social",
    ],
    "siprov_beneficio_situacao": [
        "beneficio_situacao_atual",
        "benefício - situação atual",
        "beneficio - situacao atual",
    ],
    "siprov_associado_cpf_cnpj": [
        "associado_cpf_cnpj",
        "associado - cpf/cnpj",
    ],
    "siprov_associado_telefone": [
        "associado_telefone",
        "associado_telefone_celular_primeiro",
    ],
    "siprov_plano_adicional": [
        "beneficio_planos_adicionais",
        "beneficio_planos_adicionais_nomes",
    ],
    "siprov_valor_plano": [
        "beneficio_planos_principais_valor",
        "beneficio_valor",
    ],
    "siprov_associado_email": [
        "associado_email",
        "associado - email",
    ],
    "siprov_associado_data_cadastro": [
        "associado_data_cadastro",
        "associado - data de cadastro",
    ],
    "siprov_associado_recebe_email": [
        "associado_recebe_email",
        "associado - recebe email",
    ],
    "siprov_beneficio_tipo_pagamento": [
        "beneficio_tipo_pagamento",
        "benefício - tipo de pagamento",
        "beneficio - tipo de pagamento",
    ],
    "siprov_beneficio_usuario_ultima_situacao": [
        "beneficio_usuario_ultima_situacao",
        "benefício - usuário da última situação",
        "beneficio - usuario da ultima situacao",
    ],
    "siprov_veiculo_sem_placa": [
        "veiculo_sem_placa",
        "veículo - sem placa",
        "veiculo - sem placa",
    ],
    "siprov_placa": [
        "placa",
        "veiculo_placa",
        "veiculo_placa_veiculo",
        "veículo - placa",
    ],
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
    frames = _extrair_tabelas_arquivo(fonte)
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
    frames = _extrair_tabelas_arquivo(fonte)
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
    frames = _extrair_tabelas_arquivo(fonte)
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
    frames = _extrair_tabelas_arquivo(fonte)
    df = _combinar_frames(frames)
    if df.empty:
        logger.warning("Nenhuma tabela encontrada no PDF de usuários.")
        return pd.DataFrame(columns=COLUNAS_USUARIOS)
    df = _mapear_colunas(df, MAPEAMENTO_USUARIOS)
    return df.reset_index(drop=True)


def ler_pdf_siprov(fonte: FontePDF) -> pd.DataFrame:
    """
    Lê export oficial do SIPROV (JSON/XLSX/PDF/CSV/HTML) e retorna DataFrame normalizado.
    """
    frames = _extrair_tabelas_arquivo(fonte)
    df = _combinar_frames(frames)
    if df.empty:
        logger.warning("Nenhuma tabela encontrada no arquivo SIPROV.")
        return pd.DataFrame(columns=COLUNAS_SIPROV)

    df = _mapear_colunas(df, MAPEAMENTO_SIPROV)
    return normalizar_dataframe_siprov(df)
