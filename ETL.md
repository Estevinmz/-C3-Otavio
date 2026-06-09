# 📋 Documentação do Pipeline de ETL

## 📌 Visão Geral

O pipeline de ETL (Extract, Transform, Load) processa dados de COVID-19 de um arquivo CSV (`MICRODADOS.csv`) para um Data Warehouse dimensional em SQLite (`covid_dw.db`). O processo envolve limpeza, normalização, deduplicação e carregamento em estrutura dimensional otimizada para análises.

---

## 🔄 Etapas do Pipeline

### 1️⃣ EXTRACT (Extração)

#### Fonte de Dados

- **Arquivo**: `MICRODADOS.csv`
- **Formato**: CSV delimitado
- **Origem**: Dados públicos de notificações de COVID-19
- **Tamanho**: Variável (pode conter milhões de registros)
- **Encoding**: Auto-detectado (UTF-8, Latin-1, ISO-8859-1)
- **Delimitador**: Auto-detectado (`;`, `,`, `\t`)

#### Campos Extraídos

```
Identificação: ID, DataNotificacao
Paciente: Sexo, FaixaEtaria, RacaCor, Escolaridade, Gestante, ProfissionalSaude, PossuiDeficiencia, MoradorDeRua
Localização: Municipio, Bairro
Datas: DataNotificacao, DataDiagnostico, DataEncerramento
Clínica: Febre, DificuldadeRespiratoria, Tosse, Coriza, DorGarganta, Diarreia, Cefaleia, Sintomas*
Comorbidades: ComorbidadePulmao, ComorbidadeCardio, ComorbidadeRenal, ComorbidadeDiabetes, ComorbidadeTabagismo, ComorbidadeObesidade
Testes: ResultadoRT_PCR, ResultadoTesteRapido, ResultadoSorologia, ResultadoSorologia_IGG, TipoTesteRapido
Situação: Classificacao, Evolucao, CriterioConfirmacao, StatusNotificacao
Medidas: Obito, FicouInternado
```

---

### 2️⃣ TRANSFORM (Transformação)

#### Transformações Aplicadas

##### **2.1 Limpeza de Dados**

| Transformação | Função | Exemplo |
|---------------|--------|---------|
| **Remoção de nulos** | Substitui valores nulos/vazios por defaults | `None`, `"null"`, `"na"` → "Não Informado" |
| **Trimming** | Remove espaços em branco | `" CONFIRMADO "` → `"CONFIRMADO"` |
| **Case normalization** | Padroniza maiúsculas/minúsculas | `"sim"`, `"SIM"`, `"Yes"` → `"Sim"` |
| **Tratamento de caracteres especiais** | Remove encoding inválido | Errors='replace' em leitura CSV |

**Funções implementadas:**
```python
normalize_text(value, default='Não Informado')
  - Trata nulo, vazio, strings inválidas
  - Retorna default se inválido
  
normalize_yes_no(value)
  - Converte para padrão binário
  - Retorna: "Sim" / "Não" / "Não se aplica"
  
parse_date(date_str)
  - Suporta múltiplos formatos:
    * YYYY-MM-DD
    * DD/MM/YYYY
    * "Mon DD YYYY" (em português e inglês)
  - Retorna datetime ou None
```

##### **2.2 Normalização Dimensional**

| Dimensão | Normalização |
|----------|--------------|
| **Datas** | Parsing de 6+ formatos de data; criação de atributos temporais (ano, mês, trimestre, dia da semana) |
| **Paciente** | Padronização de sexo, faixa etária, raça/cor; conversão S/N para Sim/Não |
| **Localização** | Inferência de região por município; suporte a mudança de localização (SCD Type 2) |
| **Clínica** | Conversão de booleanos e sintomas; normalização de comorbidades |
| **Testes** | Padronização de resultados (Positivo/Negativo/Indeterminado) |
| **Situação** | Mapeamento de classificações, evolução e status |

##### **2.3 Deduplicação**

- **Estratégia**: Constraint UNIQUE em dimensões
- **Exemplos**:
  - `DIM_PACIENTE`: Única por combinação de atributos demográficos
  - `DIM_LOCALIZACAO`: Única por (município, bairro, data_vigência)
  - `DIM_CLINICA`: Única por combinação de sintomas/comorbidades
  - `DIM_TESTE`: Única por combinação de resultados
  - `DIM_SITUACAO`: Única por (classificação, evolução, critério)

- **Benefício**: Reduz tamanho do DW e melhora performance de joins

##### **2.4 Agregação & Medidas**

| Medida | Tipo | Cálculo |
|--------|------|---------|
| `quantidade_casos` | Contagem | 1 por registro (ou agregado) |
| `confirmado` | Flag (0/1) | Se Classificacao = "Confirmado" |
| `obito` | Flag (0/1) | Se Evolucao = "Óbito" |
| `internado` | Flag (0/1) | Se FicouInternado = "Sim" |

#### Transformação de Data Tipo 2 (SCD Type 2)

A dimensão `DIM_LOCALIZACAO` mantém histórico de mudanças:

```sql
-- Quando município/bairro muda:
1. UPDATE DIM_LOCALIZACAO 
   SET data_fim = data_anterior - 1 dia, is_current = 0
   WHERE id = x

2. INSERT INTO DIM_LOCALIZACAO 
   (municipio, bairro, regiao, data_inicio, is_current)
   VALUES (novo_muni, novo_bairro, regiao, data_nova, 1)
```

---

### 3️⃣ LOAD (Carregamento)

#### Banco de Dados Alvo

- **SGBD**: SQLite
- **Arquivo**: `covid_dw.db`
- **Modo**: Transacional (BEGIN/COMMIT a cada batch)
- **Tamanho de batch**: 5.000 registros (configurável)

#### Tabelas Carregadas

| Tabela | Registros | Tipo |
|--------|-----------|------|
| `DIM_TEMPO` | ~2.557 | Pre-populada (2020-2026) |
| `DIM_PACIENTE` | Variável | Dimensão (deduplicada) |
| `DIM_LOCALIZACAO` | Variável | Dimensão com histórico |
| `DIM_CLINICA` | Variável | Dimensão (deduplicada) |
| `DIM_TESTE` | Variável | Dimensão (deduplicada) |
| `DIM_SITUACAO` | Variável | Dimensão (deduplicada) |
| `FATO_NOTIFICACOES` | N linhas | Tabela de fatos |

#### Estratégia de Carregamento

```
1. DROP tables antigas (limpeza)
2. CREATE schema novo com constraints e índices
3. Pre-populate DIM_TEMPO (2020-2026)
4. OPEN csv file
5. FOR EACH row in csv:
   a. Parse campos
   b. Normalize e clean
   c. Get/Create dimensão IDs (com cache em memória)
   d. Insert fact record
   e. Commit cada N linhas
6. CLOSE conexão
7. LOG: Total rows, tempo total, erros
```

#### Índices Criados

```sql
-- Performance de lookups
CREATE UNIQUE INDEX ux_localizacao_current 
ON DIM_LOCALIZACAO (municipio, bairro, is_current)

-- Foreign keys implícitos (PRAGMA foreign_keys = ON)
```

#### Controle de Transações

- **BEGIN TRANSACTION** antes de ler CSV
- **COMMIT** a cada 5.000 registros (batch)
- Reduz locks, melhora performance

---

## 🔍 Tratamento de Erros

### Stratégias de Recuperação

| Erro | Ação |
|------|------|
| **CSV não encontrado** | FileNotFoundError com mensagem clara |
| **Encoding inválido** | Auto-detect com fallbacks (utf-8 → latin-1 → iso-8859-1) |
| **Delimitador inválido** | Auto-detect testando `;`, `,`, `\t` |
| **Data inválida** | Parse com múltiplos formatos; fallback None |
| **Valor NULL/vazio** | Normalização para "Não Informado" ou default |
| **Constraint violation** | INSERT OR IGNORE + lookup no cache |

### Logging Detalhado

Todos os eventos são registrados em:
- **Console**: Para acompanhamento em tempo real
- **build_dw.log**: Arquivo de log persistente

**Exemplo de log:**
```
2026-06-09 14:32:15,123 [INFO] Criando esquema do Data Warehouse...
2026-06-09 14:32:15,456 [INFO] Pré-populando DIM_TEMPO de 2020 a 2026...
2026-06-09 14:32:16,789 [INFO] Lendo CSV com delimitador=";" e encoding="latin1"
2026-06-09 14:32:45,321 [INFO] ETL concluído: 1,234,567 linhas em 29.2s
```

---

## 📊 Exemplo de Fluxo para um Registro

### Registro Original (CSV)
```
DataNotificacao,DataDiagnostico,Sexo,FaixaEtaria,Municipio,Febre,DificuldadeRespiratoria,
2021-03-15,2021-03-13,M,40-59,Salvador,Sim,Não,Confirmado,Cura,RT_PCR_Positivo
```

### Transformações Aplicadas

1. **Parse de datas**: "2021-03-15" → datetime(2021,3,15)
2. **Criação de ID temporal**: datetime → id_tempo = 20210315
3. **Normalização de sexo**: "M" → Busca/cria em DIM_PACIENTE
4. **Normalização de sintomas**: "Sim"/"Não" → lookup/insert em DIM_CLINICA
5. **Localização**: "Salvador" → lookup/insert em DIM_LOCALIZACAO
6. **Teste**: "RT_PCR_Positivo" → lookup/insert em DIM_TESTE
7. **Situação**: "Confirmado", "Cura" → lookup/insert em DIM_SITUACAO

### Resultado Final (FATO_NOTIFICACOES)
```
id_fato=1234567
id_tempo_notificacao=20210315
id_paciente=456  (M, 40-59, ...)
id_localizacao=78 (Salvador, ...)
id_clinica=123   (Febre=Sim, DificuldadeRespiratoria=Não, ...)
id_teste=89      (RT_PCR=Positivo, ...)
id_situacao=45   (Confirmado, Cura, ...)
confirmado=1
obito=0
internado=0
```

---

## ⚙️ Configurações

### Variáveis em `dw_pipeline.py`

```python
DB_NAME = 'covid_dw.db'              # Nome do banco de dados
CSV_NAME = 'MICRODADOS.csv'          # Nome do arquivo de entrada
LOG_FILE = 'build_dw.log'            # Arquivo de log
ROW_LIMIT = None                     # Limite de linhas (None = sem limite)
batch_size = 5000                    # Tamanho do commit batch
```

### Ajustes de Desempenho

- **Aumentar `batch_size`**: Menos commits, mais rápido (mais memória)
- **Diminuir `batch_size`**: Mais commits, mais lento (menos memória)
- **Ativar `ROW_LIMIT`**: Teste com subset do CSV (desenvolvimento)
- **Índices adicionais**: Melhoram selects, desaceleram inserts

---

## 📈 Métricas de Execução

O pipeline registra:

| Métrica | Descrição |
|---------|-----------|
| **Tempo Total** | Início até fim do ETL |
| **Linhas Processadas** | Total de registros do CSV lidos |
| **Erros** | Quantidade de registros com problemas |
| **Taxa de Sucesso** | (Linhas - Erros) / Linhas |
| **Registros por Segundo** | Linhas / Tempo Total |

**Exemplo de output:**
```
ETL concluído em 28.5 segundos
Linhas processadas: 1,234,567
Erros: 0 (0%)
Taxa: 43,316 linhas/segundo
```

---

## 🔗 Integração com Outras Etapas

### Inputs
- `MICRODADOS.csv` (arquivo fonte)

### Outputs
- `covid_dw.db` (banco de dados)
- `build_dw.log` (arquivo de log)

### Próximas Etapas
- **streamlit_app.py**: Consome dados do DW para visualizações
- **performance_analysis.py**: Compara performance CSV vs DW

---

## 🚀 Como Executar

```bash
# Setup
pip install -r requirements.txt

# Executar ETL
python dw_pipeline.py

# Ver logs (em tempo real)
tail -f build_dw.log
```

## 📝 Checklist de Validação

- [ ] CSV foi detectado corretamente
- [ ] Encoding e delimitador auto-detectados
- [ ] Nenhum erro de parsing (Erros = 0 ou < 1%)
- [ ] DIM_TEMPO populada (2557 registros)
- [ ] Dimensões têm quantidade razoável de registros
- [ ] FATO_NOTIFICACOES tem N linhas (onde N = linhas do CSV)
- [ ] Arquivo `covid_dw.db` foi criado
- [ ] Log `build_dw.log` completo e sem exceções

---

**Documentação do ETL | COVID DW Projeto | 2026**
