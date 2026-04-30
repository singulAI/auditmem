# Exemplos de Relatórios Esperados

Este documento descreve o formato e os cabeçalhos esperados nos relatórios PDF de entrada.
O sistema tenta mapear automaticamente os nomes de colunas, mas quanto mais próximos estiverem dos exemplos abaixo, maior a precisão da extração.

---

## 1. Relatório de Dispositivos

Cabeçalhos esperados (exemplos aceitos):

| Coluna Canônica | Variantes aceitas no PDF |
|---|---|
| `nome_dispositivo` | Nome do Dispositivo, Dispositivo, Nome |
| `imei` | IMEI, IMEI do Dispositivo |
| `dispositivo_ativo` | Ativo, Estado, Status, Ativação |
| `iccid` | ICCID, Número de Série do Chip, Serial Chip |
| `telefone_chip` | Telefone, Número de Telefone |
| `operadora` | Operadora, Carrier |
| `ultima_conexao_gps` | Última Conexão GPS, Ultima Conexao GPS |
| `data_ultimo_gps` | Data do GPS, Data GPS, Data Último GPS |
| `placa` | Placa, Placa do Veículo |
| `chassi` | Chassi, Chassis |
| `usuario` | Usuário, Usuario |

### Exemplo de tabela no PDF:

```
| Nome do Dispositivo | IMEI            | Ativo | ICCID           | Telefone      | Operadora | Data GPS   | Placa   |
|---------------------|-----------------|-------|-----------------|---------------|-----------|------------|---------|
| Rastreador-001      | 123456789012345 | Ativo | 89550123456789  | 11999990000   | Claro     | 2024-03-01 | ABC1234 |
| Rastreador-002      | 987654321098765 | Inativo |               |               | Vivo      |            |         |
```

---

## 2. Relatório de Veículos

| Coluna Canônica | Variantes aceitas no PDF |
|---|---|
| `placa` | Placa, Placa do Veículo |
| `chassi` | Chassi, Chassis |
| `marca` | Marca, Brand |
| `modelo` | Modelo, Model |
| `ano` | Ano, Year |
| `data_desativacao` | Data de Desativação, Desativado em |
| `usuario` | Usuário, Usuario |
| `nome_dispositivo` | Nome do Dispositivo, Device Name |
| `imei` | IMEI |

### Exemplo de tabela no PDF:

```
| Placa   | Chassi              | Marca     | Modelo | Ano  | Data de Desativação | Usuário    | IMEI            |
|---------|---------------------|-----------|--------|------|---------------------|------------|-----------------|
| ABC1234 | 9BWZZZ377VT004251   | Volkswagen | Gol   | 2020 |                     | joao.silva | 123456789012345 |
| XYZ5678 | 9BWZZZ377VT009999   | Fiat      | Palio  | 2018 | 2024-01-15          | maria.santos|                |
```

---

## 3. Relatório de Chips M2M

| Coluna Canônica | Variantes aceitas no PDF |
|---|---|
| `iccid` | ICCID, Número de Série, Serial |
| `telefone` | Telefone, Número de Telefone |
| `imsi` | IMSI |
| `operadora` | Operadora, Carrier |
| `provedor_servico` | Provedor de Serviço, Provedor |
| `origem_softruck` | Origem Softruck, Origem |
| `nome_dispositivo` | Nome do Dispositivo, Device |
| `imei` | IMEI |
| `empresa` | Empresa, Company |

### Exemplo de tabela no PDF:

```
| ICCID           | Telefone    | IMSI            | Operadora | Dispositivo    | IMEI            | Empresa      |
|-----------------|-------------|-----------------|-----------|----------------|-----------------|--------------|
| 89550123456789  | 11999990000 | 724050123456789 | Claro     | Rastreador-001 | 123456789012345 | Empresa XYZ  |
| 89550987654321  |             | 724050987654321 | Vivo      |                |                 | Empresa XYZ  |
```

---

## 4. Relatório de Usuários (Opcional)

| Coluna Canônica | Variantes aceitas no PDF |
|---|---|
| `usuario` | Usuário, Username, Login |
| `email` | E-mail, Email |
| `nome_completo` | Nome Completo, Nome |
| `telefones` | Telefone, Telefones |
| `cpf` | CPF |
| `data_criacao` | Data de Criação, Criado em |
| `data_desativacao` | Data de Desativação |
| `empresa` | Empresa |
| `papel` | Papel, Role, Perfil |

---

## Dicas para melhor extração

1. **Exporte os PDFs diretamente da plataforma** sem conversões intermediárias.
2. Verifique se as tabelas no PDF possuem **bordas visíveis** — isso melhora a detecção pelo pdfplumber.
3. Se a extração não reconhecer automaticamente as colunas, **renomeie os cabeçalhos** no PDF original para corresponder às variantes listadas acima.
4. Relatórios com **múltiplas páginas** são suportados — todas as tabelas são combinadas automaticamente.
