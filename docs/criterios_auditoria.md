# Critérios de Auditoria de Cobrança M2M

Este documento descreve as regras aplicadas pelo sistema para identificar dispositivos, chips e veículos com indícios de cobrança indevida.

---

## Regras de Auditoria

### 1. Dispositivo Inativo (`flag_dispositivo_inativo`)

**Critério:** O campo de estado/ativação do dispositivo não contém nenhum dos valores considerados "ativo":
`ativo`, `active`, `sim`, `yes`, `1`, `true`, `s` (insensível a maiúsculas/minúsculas).

**Significado:** O rastreador está cadastrado mas desativado na plataforma. Não deveria gerar cobrança.

---

### 2. Sem Placa Vinculada (`flag_sem_placa`)

**Critério:** O campo de placa do dispositivo está vazio ou ausente.

**Significado:** O dispositivo não está associado a nenhum veículo. Pode ser um rastreador em estoque, descartado ou orphan.

---

### 3. Sem GPS Recente (`flag_sem_gps_recente`)

**Critério:** A data da última conexão GPS é mais antiga do que o limiar configurado (padrão: **30 dias**).
Dispositivos sem data de GPS registrada também são marcados.

**Significado:** O rastreador não está transmitindo dados. Pode estar quebrado, desligado, sem chip ou fisicamente removido.

---

### 4. Sem Chip / ICCID Ausente (`flag_sem_chip`)

**Critério:** O campo ICCID (número de série do chip) está vazio ou ausente.

**Significado:** O dispositivo não possui chip M2M associado. Não deveria gerar cobrança de conectividade.

---

### 5. IMEI Duplicado (`flag_imei_duplicado`)

**Critério:** O IMEI do dispositivo aparece em mais de um registro no relatório (desconsiderando IMEIs em branco).

**Significado:** O mesmo rastreador pode estar cadastrado múltiplas vezes, gerando cobranças duplicadas.

---

### 6. ICCID Duplicado (`flag_iccid_duplicado`)

**Critério:** O ICCID do chip aparece em mais de um registro (desconsiderando ICCIDs em branco).

**Significado:** O mesmo chip pode estar associado a múltiplos dispositivos, o que é uma inconsistência que pode gerar cobranças duplas.

---

### 7. Veículo Desativado (`flag_veiculo_desativado`)

**Critério:** O veículo vinculado ao dispositivo possui uma data de desativação preenchida no relatório de veículos.

**Significado:** O veículo foi desativado na plataforma, mas o dispositivo ainda pode estar gerando cobrança.

---

## Campo `suspeito`

O campo `suspeito` é `True` quando **ao menos uma** das flags acima está ativada para aquele registro.
Use este campo para filtrar rapidamente os itens que precisam de revisão.

---

## Configurações Ajustáveis

| Parâmetro | Padrão | Descrição |
|-----------|--------|-----------|
| Dias sem GPS | 30 | Limiar de dias sem conexão GPS para marcar como suspeito |

O limiar de dias sem GPS pode ser ajustado diretamente na barra lateral do dashboard.

---

## Priorização de Revisão

Recomenda-se revisar na seguinte ordem de prioridade:

1. **IMEI duplicado** — risco imediato de cobrança duplicada
2. **ICCID duplicado** — risco imediato de cobrança duplicada de chip
3. **Dispositivo inativo + sem GPS** — candidatos a cancelamento
4. **Sem placa + sem chip** — dispositivos orphan
5. **Veículo desativado** — revisar necessidade de manter rastreador ativo
