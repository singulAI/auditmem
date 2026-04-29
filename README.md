# Auditoria de Cobrança M2M

Dashboard local para leitura, cruzamento e auditoria de relatórios em PDF contendo dados de veículos, dispositivos/rastreadores, chips M2M e usuários.

O objetivo principal é identificar itens que podem estar sendo cobrados indevidamente, como dispositivos inativos, sem placa vinculada, sem conexão GPS recente, sem chip, duplicados ou vinculados a veículos desativados.

---

## Funcionalidades

- 📄 Leitura de relatórios exportados em PDF (dispositivos, veículos, chips M2M, usuários)
- 🔄 Cruzamento automático de dados entre as três bases
- 🧹 Normalização de IMEI, ICCID, telefone e placa
- 🚨 Identificação de inconsistências por regras configuráveis
- 🔍 Filtros interativos por critério de auditoria
- 💾 Exportação dos resultados em CSV ou Excel (.xlsx)

### Critérios de Auditoria

| Flag | Critério |
|------|----------|
| `flag_dispositivo_inativo` | Estado de ativação não indica "ativo" |
| `flag_sem_placa` | Placa do veículo vazia ou ausente |
| `flag_sem_gps_recente` | Sem conexão GPS nos últimos N dias (padrão: 30) |
| `flag_sem_chip` | ICCID vazio ou ausente |
| `flag_imei_duplicado` | IMEI aparece em mais de um registro |
| `flag_iccid_duplicado` | ICCID aparece em mais de um registro |
| `flag_veiculo_desativado` | Veículo vinculado possui data de desativação |

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

## Dependências principais

| Pacote | Uso |
|--------|-----|
| `streamlit` | Interface web local |
| `pdfplumber` | Extração de tabelas de PDFs |
| `pandas` | Manipulação de dados |
| `openpyxl` / `xlsxwriter` | Exportação Excel |
