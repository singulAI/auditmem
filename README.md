# Auditoria de Cobrança M2M

Dashboard BI para auditoria de cobranças M2M: leitura, cruzamento e análise de relatórios de dispositivos/rastreadores, chips M2M, veículos e usuários, com suporte a múltiplos formatos (PDF, CSV, HTML) e duas prestadoras simultâneas.

Acesso em produção: **https://auditoria.anadm.site**

O objetivo é identificar itens cobrados indevidamente, como dispositivos inativos, sem placa, sem GPS recente, sem chip, duplicados, vinculados a veículos desativados, ou cobrados por dois prestadores ao mesmo tempo.

---

## Objetivo do projeto

Este sistema foi criado para auditar cobranças M2M de rastreadores, chips e veículos cadastrados em duas prestadoras: **Base Principal** e **M2Data**.

A ferramenta permite:

- Ler relatórios em PDF, CSV ou HTML.
- Extrair e normalizar dados como IMEI, ICCID, telefone e placa.
- Cruzar dispositivos, chips e veículos entre as duas bases.
- Identificar inconsistências classificando por dois eixos de risco.
- Detectar chips cobrados por ambas as prestadoras (cobrança dupla).
- Simular o impacto financeiro por prestadora.
- Gerar relatório em CSV ou Excel para contestação.

---

## Funcionalidades

- 📄 Leitura de relatórios em **PDF, CSV e HTML** (dispositivos, veículos, chips M2M, usuários)
- 🏢 Suporte a duas prestadoras: **Base Principal** e **M2Data** (chips-only)
- 🔄 Cruzamento automático de dados com deduplicação antes do join
- 🧹 Normalização de IMEI, ICCID, telefone e placa
- 🚨 Dois eixos de risco independentes: **risco de cobrança** e **risco cadastral**
- 🔍 Filtros interativos e triagem por prioridade de auditoria
- 💰 Simulação financeira por prestadora (valor médio ou valor total/quantidade)
- 🔁 Detecção de chips cobrados por ambas as prestadoras simultaneamente
- 💾 Exportação dos resultados em CSV ou Excel (.xlsx)

### Critérios de Auditoria

| Flag | Eixo | Critério |
|------|------|----------|
| `flag_dispositivo_inativo` | Cobrança | Estado de ativação não indica "ativo" |
| `flag_sem_placa` | Cobrança | Placa do veículo vazia ou ausente |
| `flag_sem_gps_recente` | Cobrança | Sem conexão GPS nos últimos N dias (padrão: 30) |
| `flag_sem_chip` | Cobrança | ICCID vazio ou sem correspondência na base de chips |
| `flag_imei_duplicado` | Cobrança | IMEI aparece em mais de um registro |
| `flag_iccid_duplicado` | Cobrança | ICCID aparece em mais de um registro |
| `flag_telefone_duplicado` | Cobrança | Telefone do chip (M2M) duplicado |
| `flag_veiculo_desativado` | Cobrança | Veículo vinculado possui data de desativação |
| `flag_placa_duplicada` | Cadastro | Mesma placa em mais de um dispositivo |
| `flag_telefone_cliente_duplicado` | Cadastro | Telefone do cliente duplicado (risco cadastral) |

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

---

### 4. Relatório de usuários (opcional)

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

---

## Estrutura do Projeto

```text
auditmem/
│
├── app.py                    # Dashboard Streamlit (ponto de entrada)
├── requirements.txt
├── README.md
│
├── data/
│   ├── entrada/              # Coloque os PDFs aqui
│   ├── processado/           # CSVs intermediários (gerados automaticamente)
│   └── saida/                # Resultados da auditoria
│
├── src/
│   ├── __init__.py
│   ├── config.py             # Colunas, caminhos e parâmetros
│   ├── leitura_pdf.py        # Extração de tabelas dos PDFs
│   ├── normalizacao.py       # Normalização de IMEI, ICCID, placa, etc.
│   ├── cruzamentos.py        # Merge entre dispositivos, veículos e chips
│   ├── regras_auditoria.py   # Regras de identificação de inconsistências
│   └── exportacao.py         # Exportação CSV e Excel
│
└── docs/
    ├── criterios_auditoria.md
    └── exemplos_relatorios.md
```

---

## Instalação

```bash
pip install -r requirements.txt
```

---

## Execução

```bash
streamlit run app.py
```

O dashboard abrirá no navegador em `http://localhost:8501`.

---

## Uso

1. Na barra lateral, faça upload dos relatórios em PDF:
   - **Dispositivos** *(obrigatório)*
   - **Veículos** *(recomendado)*
   - **Chips M2M** *(recomendado)*
   - **Usuários** *(opcional)*
2. Ajuste o limiar de dias sem GPS se necessário (padrão: 30 dias).
3. Clique em **Processar Auditoria**.
4. Utilize os filtros interativos para explorar os resultados.
5. Exporte o relatório em CSV ou Excel para contestação.

---

## Fontes de dados

Consulte [`docs/exemplos_relatorios.md`](docs/exemplos_relatorios.md) para ver os formatos de PDF esperados e variações de cabeçalho aceitas.

Consulte [`docs/criterios_auditoria.md`](docs/criterios_auditoria.md) para a descrição detalhada de cada regra de auditoria.

---

## Regra crítica: não confundir telefone do chip com telefone do cliente

O sistema deve separar rigorosamente os telefones M2M dos telefones de clientes/usuários.

### Telefone do chip

Representa a linha instalada no rastreador/dispositivo M2M.

Nomes de coluna esperados:

```text
Número de telefone do chip
Telefone do chip
Linha do chip
MSISDN do chip
```

Nome interno recomendado:

```text
telefone_chip
```

Esse campo deve ser usado para:

```text
Identificar chip M2M
Validar vínculo chip → dispositivo
Encontrar telefone de chip duplicado
Comparar cobrança da operadora
Verificar chip sem uso
Verificar chip sem dispositivo
```

### Telefone do cliente

Representa o telefone pessoal ou comercial do usuário/associado.

Nomes de coluna esperados:

```text
Telefone 1 do usuário
Telefone 2 do usuário
Telefones dos usuários
Telefone do cliente
Celular do cliente
```

Nome interno recomendado:

```text
telefone_cliente
```

Esse campo deve ser usado apenas para:

```text
Contato com o cliente
Validação cadastral do usuário
Identificação de usuário duplicado
Conferência de cadastro
```

## Proibição de cruzamento incorreto

Nunca usar `telefone_cliente` para identificar chip.

Nunca usar `telefone_cliente` para decidir se um chip está duplicado.

Nunca usar `telefone_cliente` para contestar cobrança de M2M.

Nunca misturar:

```text
telefone_chip != telefone_cliente
```

Mesmo que ambos tenham formato parecido, eles representam coisas diferentes.

## Cruzamento correto

O vínculo correto deve ser:

```text
Placa
    ↓
IMEI do dispositivo
    ↓
Número de série do chip / ICCID
    ↓
Número de telefone do chip
    ↓
Operadora do chip
```

O telefone do cliente fica fora dessa cadeia técnica:

```text
Usuário / Cliente
    ↓
Telefone do cliente
```

O telefone do cliente pode ajudar a identificar o proprietário do veículo, mas não deve ser usado como prova de vínculo técnico entre chip, rastreador e cobrança.

---

## Dependências principais

| Pacote | Uso |
|--------|-----|
| `streamlit` | Interface web local |
| `pdfplumber` | Extração de tabelas de PDFs |
| `pandas` | Manipulação de dados |
| `openpyxl` / `xlsxwriter` | Exportação Excel |

