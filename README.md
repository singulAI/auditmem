# auditmem# Auditoria de Cobrança M2M

Dashboard local para leitura, cruzamento e auditoria de relatórios em PDF contendo dados de veículos, dispositivos/rastreadores, chips M2M e usuários.

O objetivo principal é identificar itens que podem estar sendo cobrados indevidamente, como dispositivos inativos, sem placa vinculada, sem conexão GPS recente, sem chip, duplicados ou vinculados a veículos desativados.

---

## Objetivo do projeto

Este sistema foi criado para ajudar na análise de cobranças relacionadas a rastreadores, chips M2M e veículos cadastrados.

A ferramenta permite:

- Ler relatórios exportados em PDF.
- Extrair tabelas dos PDFs.
- Normalizar dados como IMEI, ICCID, telefone e placa.
- Cruzar dispositivos, chips e veículos.
- Identificar inconsistências.
- Filtrar itens inativos, sem placa ou sem GPS recente.
- Gerar relatório em CSV ou Excel para contestação ou revisão de cobrança.

---

## Fontes de dados esperadas

O dashboard trabalha principalmente com três tipos de relatórios.

### 1. Relatório de veículos

Contém informações como:

- Placa do veículo
- Chassi
- Marca
- Modelo
- Ano
- Data de desativação
- Usuário vinculado
- Nome do dispositivo
- IMEI do dispositivo

Esse relatório é usado para identificar veículos ativos/inativos, placas sem dispositivo, veículos desativados e vínculos entre placa e IMEI.  
Fonte esperada: relatório de veículos. :contentReference[oaicite:0]{index=0}

---

### 2. Relatório de dispositivos

Contém informações como:

- Nome do dispositivo
- IMEI do dispositivo
- Estado de ativação do dispositivo
- Número de série do chip
- Número de telefone do chip
- Operadora
- Última conexão GPS
- Última data do GPS
- Placa do veículo
- Chassi
- Usuário vinculado

Esse é o relatório mais importante para a auditoria, pois mostra o estado do rastreador, o chip vinculado, o GPS e a placa associada.  
Fonte esperada: relatório de dispositivos. :contentReference[oaicite:1]{index=1}

---

### 3. Relatório de chips

Contém informações como:

- Número de série do chip
- Número de telefone do chip
- IMSI
- Operadora
- Provedor de serviço
- Origem Softruck
- Nome do dispositivo
- IMEI do dispositivo
- Empresa

Esse relatório é usado para verificar chips ativos, chips duplicados, chips sem rastreador e vínculos entre ICCID, telefone e IMEI.  
Fonte esperada: relatório de chips. :contentReference[oaicite:2]{index=2}

---

### 4. Relatório de usuários, opcional

Pode conter:

- Nome de usuário
- E-mail
- Nome completo
- Telefones
- CPF
- Data de criação
- Data de desativação
- Empresa
- Papel do usuário

Esse relatório pode ser usado em versões futuras para identificar usuários desativados, cadastros duplicados ou veículos vinculados a usuários sem atividade.  
Fonte esperada: relatório de usuários. :contentReference[oaicite:3]{index=3}

---

## Estrutura recomendada do projeto

```text
auditoria-cobranca-m2m/
│
├── app.py
├── requirements.txt
├── README.md
│
├── data/
│   ├── entrada/
│   │   ├── veiculos.pdf
│   │   ├── dispositivos.pdf
│   │   └── chips.pdf
│   │
│   ├── processado/
│   │   ├── base_dispositivos.csv
│   │   ├── base_veiculos.csv
│   │   ├── base_chips.csv
│   │   └── base_auditoria.csv
│   │
│   └── saida/
│       ├── auditoria_cobranca_m2m.csv
│       └── auditoria_cobranca_m2m.xlsx
│
├── src/
│   ├── __init__.py
│   ├── leitura_pdf.py
│   ├── normalizacao.py
│   ├── cruzamentos.py
│   ├── regras_auditoria.py
│   ├── exportacao.py
│   └── config.py
│
└── docs/
    ├── criterios_auditoria.md
    └── exemplos_relatorios.md
