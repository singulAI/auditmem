"""
Configurações globais do sistema de auditoria de cobrança M2M.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ENTRADA_DIR = DATA_DIR / "entrada"
PROCESSADO_DIR = DATA_DIR / "processado"
SAIDA_DIR = DATA_DIR / "saida"

# Garante que os diretórios existam em tempo de execução
for _d in (ENTRADA_DIR, PROCESSADO_DIR, SAIDA_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Nomes canônicos de colunas — relatório de dispositivos
# ---------------------------------------------------------------------------
COL_DISP_NOME = "nome_dispositivo"
COL_DISP_IMEI = "imei"
COL_DISP_ATIVO = "dispositivo_ativo"
COL_DISP_ICCID = "iccid"
COL_DISP_TELEFONE = "telefone_chip"
COL_DISP_TELEFONE_CLIENTE = "telefone_cliente"
COL_DISP_OPERADORA = "operadora"
COL_DISP_ULTIMA_CONEXAO = "ultima_conexao_gps"
COL_DISP_DATA_GPS = "data_ultimo_gps"
COL_DISP_PLACA = "placa"
COL_DISP_CHASSI = "chassi"
COL_DISP_USUARIO = "usuario"

COLUNAS_DISPOSITIVOS = [
    COL_DISP_NOME,
    COL_DISP_IMEI,
    COL_DISP_ATIVO,
    COL_DISP_ICCID,
    COL_DISP_TELEFONE,
    COL_DISP_TELEFONE_CLIENTE,
    COL_DISP_OPERADORA,
    COL_DISP_ULTIMA_CONEXAO,
    COL_DISP_DATA_GPS,
    COL_DISP_PLACA,
    COL_DISP_CHASSI,
    COL_DISP_USUARIO,
]

# ---------------------------------------------------------------------------
# Nomes canônicos de colunas — relatório de veículos
# ---------------------------------------------------------------------------
COL_VEIC_PLACA = "placa"
COL_VEIC_CHASSI = "chassi"
COL_VEIC_MARCA = "marca"
COL_VEIC_MODELO = "modelo"
COL_VEIC_ANO = "ano"
COL_VEIC_DATA_DESATIVACAO = "data_desativacao"
COL_VEIC_USUARIO = "usuario"
COL_VEIC_NOME_DISP = "nome_dispositivo"
COL_VEIC_IMEI = "imei"

COLUNAS_VEICULOS = [
    COL_VEIC_PLACA,
    COL_VEIC_CHASSI,
    COL_VEIC_MARCA,
    COL_VEIC_MODELO,
    COL_VEIC_ANO,
    COL_VEIC_DATA_DESATIVACAO,
    COL_VEIC_USUARIO,
    COL_VEIC_NOME_DISP,
    COL_VEIC_IMEI,
]

# ---------------------------------------------------------------------------
# Nomes canônicos de colunas — relatório de chips
# ---------------------------------------------------------------------------
COL_CHIP_ICCID = "iccid"
COL_CHIP_TELEFONE = "telefone"
COL_CHIP_IMSI = "imsi"
COL_CHIP_OPERADORA = "operadora"
COL_CHIP_PROVEDOR = "provedor_servico"
COL_CHIP_ORIGEM = "origem_softruck"
COL_CHIP_NOME_DISP = "nome_dispositivo"
COL_CHIP_IMEI = "imei"
COL_CHIP_EMPRESA = "empresa"

COLUNAS_CHIPS = [
    COL_CHIP_ICCID,
    COL_CHIP_TELEFONE,
    COL_CHIP_IMSI,
    COL_CHIP_OPERADORA,
    COL_CHIP_PROVEDOR,
    COL_CHIP_ORIGEM,
    COL_CHIP_NOME_DISP,
    COL_CHIP_IMEI,
    COL_CHIP_EMPRESA,
]

# ---------------------------------------------------------------------------
# Nomes canônicos de colunas — relatório de usuários
# ---------------------------------------------------------------------------
COL_USR_USUARIO = "usuario"
COL_USR_EMAIL = "email"
COL_USR_NOME = "nome_completo"
COL_USR_TELEFONES = "telefones"
COL_USR_CPF = "cpf"
COL_USR_DATA_CRIACAO = "data_criacao"
COL_USR_DATA_DESATIVACAO = "data_desativacao"
COL_USR_EMPRESA = "empresa"
COL_USR_PAPEL = "papel"

COLUNAS_USUARIOS = [
    COL_USR_USUARIO,
    COL_USR_EMAIL,
    COL_USR_NOME,
    COL_USR_TELEFONES,
    COL_USR_CPF,
    COL_USR_DATA_CRIACAO,
    COL_USR_DATA_DESATIVACAO,
    COL_USR_EMPRESA,
    COL_USR_PAPEL,
]

# ---------------------------------------------------------------------------
# Nomes canônicos de colunas — relatório SIPROV (referência oficial)
# ---------------------------------------------------------------------------
COL_SIP_ASSOCIADO_NOME = "siprov_associado_nome"
COL_SIP_ASSOCIADO_CPF_CNPJ = "siprov_associado_cpf_cnpj"
COL_SIP_BENEFICIO_SITUACAO = "siprov_beneficio_situacao"
COL_SIP_ASSOCIADO_EMAIL = "siprov_associado_email"
COL_SIP_ASSOCIADO_DATA_CADASTRO = "siprov_associado_data_cadastro"
COL_SIP_ASSOCIADO_RECEBE_EMAIL = "siprov_associado_recebe_email"
COL_SIP_BENEFICIO_TIPO_PAGAMENTO = "siprov_beneficio_tipo_pagamento"
COL_SIP_BENEFICIO_USUARIO_ULTIMA_SITUACAO = "siprov_beneficio_usuario_ultima_situacao"
COL_SIP_VEICULO_SEM_PLACA = "siprov_veiculo_sem_placa"
COL_SIP_PLACA = "siprov_placa"

COL_SIP_STATUS_REFERENCIA = "siprov_status_referencia"
COL_SIP_ENCONTRADO = "siprov_encontrado"
COL_SIP_CHAVE_CRUZAMENTO = "siprov_chave_cruzamento"
COL_SIP_CONFIANCA_CRUZAMENTO = "siprov_confianca_cruzamento"

COLUNAS_SIPROV = [
    COL_SIP_ASSOCIADO_NOME,
    COL_SIP_BENEFICIO_SITUACAO,
    COL_SIP_ASSOCIADO_CPF_CNPJ,
    COL_SIP_ASSOCIADO_EMAIL,
    COL_SIP_ASSOCIADO_DATA_CADASTRO,
    COL_SIP_ASSOCIADO_RECEBE_EMAIL,
    COL_SIP_BENEFICIO_TIPO_PAGAMENTO,
    COL_SIP_BENEFICIO_USUARIO_ULTIMA_SITUACAO,
    COL_SIP_VEICULO_SEM_PLACA,
    COL_SIP_PLACA,
]

# ---------------------------------------------------------------------------
# Flags de auditoria — colunas adicionadas ao relatório final
# ---------------------------------------------------------------------------
FLAG_DISPOSITIVO_INATIVO = "flag_dispositivo_inativo"
FLAG_SEM_PLACA = "flag_sem_placa"
FLAG_SEM_GPS_RECENTE = "flag_sem_gps_recente"
FLAG_SEM_CHIP = "flag_sem_chip"
FLAG_IMEI_DUPLICADO = "flag_imei_duplicado"
FLAG_ICCID_DUPLICADO = "flag_iccid_duplicado"
FLAG_TELEFONE_DUPLICADO = "flag_telefone_duplicado"
FLAG_TELEFONE_CLIENTE_DUPLICADO = "flag_telefone_cliente_duplicado"
FLAG_PLACA_DUPLICADA = "flag_placa_duplicada"
FLAG_VEICULO_DESATIVADO = "flag_veiculo_desativado"
FLAG_SIPROV_SEM_CADASTRO = "flag_siprov_sem_cadastro"
FLAG_SIPROV_INATIVO_ATIVO_PRESTADOR = "flag_siprov_inativo_ativo_prestador"
FLAG_SIPROV_INADIMPLENTE_ATIVO_PRESTADOR = "flag_siprov_inadimplente_ativo_prestador"

# Coluna derivada para visualização do status operacional do dispositivo
COL_AUD_STATUS_DISPOSITIVO = "status_dispositivo"
COL_AUD_CHIP_ENCONTRADO = "chip_encontrado"
COL_AUD_RISCO_COBRANCA = "risco_cobranca"
COL_AUD_MOTIVOS_COBRANCA = "motivos_cobranca"
COL_AUD_RISCO_CADASTRO = "risco_cadastro"
COL_AUD_MOTIVOS_CADASTRO = "motivos_cadastro"

FLAGS_AUDITORIA = [
    FLAG_DISPOSITIVO_INATIVO,
    FLAG_SEM_PLACA,
    FLAG_SEM_GPS_RECENTE,
    FLAG_SEM_CHIP,
    FLAG_IMEI_DUPLICADO,
    FLAG_ICCID_DUPLICADO,
    FLAG_TELEFONE_DUPLICADO,
    FLAG_TELEFONE_CLIENTE_DUPLICADO,
    FLAG_PLACA_DUPLICADA,
    FLAG_VEICULO_DESATIVADO,
    FLAG_SIPROV_SEM_CADASTRO,
    FLAG_SIPROV_INATIVO_ATIVO_PRESTADOR,
    FLAG_SIPROV_INADIMPLENTE_ATIVO_PRESTADOR,
]

FLAGS_COBRANCA = [
    FLAG_DISPOSITIVO_INATIVO,
    FLAG_SEM_PLACA,
    FLAG_SEM_GPS_RECENTE,
    FLAG_SEM_CHIP,
    FLAG_IMEI_DUPLICADO,
    FLAG_ICCID_DUPLICADO,
    FLAG_TELEFONE_DUPLICADO,
    FLAG_PLACA_DUPLICADA,
    FLAG_VEICULO_DESATIVADO,
    FLAG_SIPROV_SEM_CADASTRO,
    FLAG_SIPROV_INATIVO_ATIVO_PRESTADOR,
    FLAG_SIPROV_INADIMPLENTE_ATIVO_PRESTADOR,
]

FLAGS_CADASTRAIS = [
    FLAG_TELEFONE_CLIENTE_DUPLICADO,
]

# ---------------------------------------------------------------------------
# Parâmetros de auditoria
# ---------------------------------------------------------------------------
# Número de dias sem conexão GPS para considerar dispositivo "sem GPS recente"
DIAS_SEM_GPS = 30

# Valores aceitos como "ativo" na coluna de ativação do dispositivo
VALORES_ATIVO = {
    "ativo",
    "active",
    "sim",
    "yes",
    "1",
    "true",
    "verdadeiro",
    "s",
}

VALORES_SIPROV_INATIVO = {
    "inativo",
    "cancelado",
    "cancelada",
    "suspenso",
    "suspensa",
    "bloqueado",
    "bloqueada",
}

VALORES_SIPROV_INADIMPLENTE = {
    "inadimplente",
    "inadimplencia",
    "em atraso",
    "atrasado",
    "atrasada",
}

# ---------------------------------------------------------------------------
# Nomes de arquivos de saída
# ---------------------------------------------------------------------------
ARQUIVO_SAIDA_CSV = SAIDA_DIR / "auditoria_cobranca_m2m.csv"
ARQUIVO_SAIDA_EXCEL = SAIDA_DIR / "auditoria_cobranca_m2m.xlsx"
