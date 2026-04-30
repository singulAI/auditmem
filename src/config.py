# Colunas esperadas para cada tipo de relatório
COLUNAS_DISPOSITIVOS = {
    "imei": ["IMEI do dispositivo", "imei", "IMEI"],
    "nome": ["Nome do dispositivo", "nome", "Nome"],
    "ativo": ["Estado de ativação do dispositivo", "Estado de ativação", "ativo"],
    "chip_serie": ["Número de série do chip", "serie_chip", "ICCID"],
    "chip_telefone": ["Número de telefone do chip", "telefone_chip", "Telefone"],
    "gps_data": ["Última data de conexão do GPS", "Última data do GPS", "gps_data"],
    "placa": ["Placa do veículo", "placa", "Placa"],
    "chassi": ["Chassi do veículo", "chassi"],
    "usuario": ["Nomes dos usuários", "usuario"],
    "operadora": ["Operadora do chip", "operadora"],
}

COLUNAS_CHIPS = {
    "serie": ["Número de série do chip", "ICCID", "serie"],
    "telefone": ["Número de telefone do chip", "MSISDN", "telefone"],
    "imsi": ["IMSI do chip", "imsi"],
    "operadora": ["Operadora do chip", "Operadora", "operadora"],
    "provedor": ["Provedor de serviço do chip", "provedor"],
    "imei": ["IMEI do dispositivo", "imei"],
    "nome_dispositivo": ["Nome do dispositivo", "nome"],
    "empresa": ["Nome da empresa", "empresa"],
}

COLUNAS_VEICULOS = {
    "placa": ["Placa do veículo", "Placa", "placa"],
    "chassi": ["Chassi do veículo", "Chassi", "chassi"],
    "marca": ["Marca do veículo", "Marca", "marca"],
    "modelo": ["Modelo do veículo", "Modelo", "modelo"],
    "ano": ["Ano do veículo", "Ano", "ano"],
    "desativacao": ["Data de desativação do veículo", "Data de desativação", "desativacao"],
    "imei": ["IMEI do dispositivo", "imei"],
    "usuario": ["Nomes dos usuários", "usuario"],
}

COLUNAS_COBRANCA = {
    "telefone": ["MSISDN", "Número de telefone do chip", "telefone"],
    "status": ["Status", "status"],
    "valor": ["Total", "Valor", "valor"],
    "data_fatura": ["Data Fatura", "data_fatura"],
    "operadora": ["Operadora", "operadora"],
    "login": ["Login", "login"],
}

VALOR_INATIVO = ["Falso", "falso", "FALSE", "false", "0", "inativo", "Inativo", "INACTIVE"]
VALOR_ATIVO = ["Verdadeiro", "verdadeiro", "TRUE", "true", "1", "ativo", "Ativo", "ACTIVE"]

LIMITE_GPS_DIAS = 30

APP_TITULO = "Auditoria de Cobrança M2M"
APP_SUBTITULO = "Dashboard de análise de cobranças de rastreadores e chips M2M"
