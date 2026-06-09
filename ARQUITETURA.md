# 🏗️ Arquitetura do Data Warehouse - Modelo Dimensional

## Diagrama do Esquema Estrela

```mermaid
erDiagram
    FATO_NOTIFICACOES ||--o{ DIM_TEMPO : "id_tempo_notificacao"
    FATO_NOTIFICACOES ||--o{ DIM_PACIENTE : "id_paciente"
    FATO_NOTIFICACOES ||--o{ DIM_LOCALIZACAO : "id_localizacao"
    FATO_NOTIFICACOES ||--o{ DIM_CLINICA : "id_clinica"
    FATO_NOTIFICACOES ||--o{ DIM_TESTE : "id_teste"
    FATO_NOTIFICACOES ||--o{ DIM_SITUACAO : "id_situacao"

    FATO_NOTIFICACOES {
        int id_fato "PK, Auto"
        int id_tempo_notificacao "FK"
        int id_tempo_diagnostico "FK"
        int id_tempo_encerramento "FK"
        int id_paciente "FK"
        int id_localizacao "FK"
        int id_clinica "FK"
        int id_teste "FK"
        int id_situacao "FK"
        int quantidade_casos "Fato (medida)"
        int obito "Flag (medida)"
        int confirmado "Flag (medida)"
        int internado "Flag (medida)"
    }

    DIM_TEMPO {
        int id_tempo "PK"
        string data
        int ano
        int mes
        string mes_nome
        int dia
        string dia_semana
        int trimestre
    }

    DIM_PACIENTE {
        int id_paciente "PK, Auto"
        string sexo
        string faixa_etaria
        string raca_cor
        string escolaridade
        string gestante
        string profissional_saude
        string possui_deficiencia
        string morador_de_rua
    }

    DIM_LOCALIZACAO {
        int id_localizacao "PK, Auto"
        string municipio
        string bairro
        string regiao
        string data_inicio
        string data_fim
        int is_current
    }

    DIM_CLINICA {
        int id_clinica "PK, Auto"
        string febre
        string dificuldade_respiratoria
        string tosse
        string coriza
        string dor_garganta
        string diarreia
        string cefaleia
        string comorbidade_pulmao
        string comorbidade_cardio
        string comorbidade_renal
        string comorbidade_diabetes
        string comorbidade_tabagismo
        string comorbidade_obesidade
        string ficou_internado
    }

    DIM_TESTE {
        int id_teste "PK, Auto"
        string resultado_rt_pcr
        string resultado_teste_rapido
        string resultado_sorologia
        string resultado_sorologia_igg
        string tipo_teste_rapido
    }

    DIM_SITUACAO {
        int id_situacao "PK, Auto"
        string classificacao
        string evolucao
        string criterio_confirmacao
        string status_notificacao
    }
```

## 📊 Descrição Detalhada das Tabelas

### Tabela de Fatos: FATO_NOTIFICACOES

**Propósito**: Registro central de todas as notificações de COVID-19, conectando dimensões com medidas quantitativas.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id_fato` | INTEGER | Chave primária (auto-increment) |
| `id_tempo_notificacao` | INTEGER | FK → DIM_TEMPO (data da notificação) |
| `id_tempo_diagnostico` | INTEGER | FK → DIM_TEMPO (data do diagnóstico) |
| `id_tempo_encerramento` | INTEGER | FK → DIM_TEMPO (data de encerramento) |
| `id_paciente` | INTEGER | FK → DIM_PACIENTE |
| `id_localizacao` | INTEGER | FK → DIM_LOCALIZACAO |
| `id_clinica` | INTEGER | FK → DIM_CLINICA |
| `id_teste` | INTEGER | FK → DIM_TESTE |
| `id_situacao` | INTEGER | FK → DIM_SITUACAO |
| `quantidade_casos` | INTEGER | **Medida**: Número de casos (geralmente 1) |
| `obito` | INTEGER | **Medida**: Flag binária (0/1) |
| `confirmado` | INTEGER | **Medida**: Flag binária (0/1) |
| `internado` | INTEGER | **Medida**: Flag binária (0/1) |

**Granularidade**: Uma linha por notificação/caso

---

### Dimensão: DIM_TEMPO

**Propósito**: Hierarquia temporal para análises por período.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id_tempo` | INTEGER | Chave primária (YYYYMMDD format) |
| `data` | TEXT | Data no formato YYYY-MM-DD |
| `ano` | INTEGER | Ano (2020-2026) |
| `mes` | INTEGER | Mês (1-12) |
| `mes_nome` | TEXT | Nome do mês em português |
| `dia` | INTEGER | Dia do mês (1-31) |
| `dia_semana` | TEXT | Dia da semana em português |
| `trimestre` | INTEGER | Trimestre (1-4) |

**Registros especiais**: `id_tempo = -1` para datas não informadas

---

### Dimensão: DIM_PACIENTE

**Propósito**: Características demográficas e de risco do paciente.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id_paciente` | INTEGER | Chave primária (auto-increment) |
| `sexo` | TEXT | Masculino / Feminino / Não Informado |
| `faixa_etaria` | TEXT | Grupos etários (0-19, 20-39, 40-59, 60+, etc) |
| `raca_cor` | TEXT | Classificação de raça/cor |
| `escolaridade` | TEXT | Nível de escolaridade |
| `gestante` | TEXT | Sim / Não / Não se aplica |
| `profissional_saude` | TEXT | Sim / Não |
| `possui_deficiencia` | TEXT | Sim / Não |
| `morador_de_rua` | TEXT | Sim / Não |

**Constraint**: UNIQUE sobre todas as colunas (evita duplicatas)

---

### Dimensão: DIM_LOCALIZACAO

**Propósito**: Localização geográfica do paciente com histórico de mudanças.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id_localizacao` | INTEGER | Chave primária (auto-increment) |
| `municipio` | TEXT | Município de residência |
| `bairro` | TEXT | Bairro |
| `regiao` | TEXT | Região geográfica (inferida) |
| `data_inicio` | TEXT | Data de início da localização |
| `data_fim` | TEXT | Data de término (NULL se atual) |
| `is_current` | INTEGER | Flag (1 = registro atual, 0 = histórico) |

**Padrão**: SCD Type 2 (Slowly Changing Dimension)

---

### Dimensão: DIM_CLINICA

**Propósito**: Sintomas e comorbidades clínicas.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id_clinica` | INTEGER | Chave primária (auto-increment) |
| `febre` | TEXT | Presença de febre (Sim/Não) |
| `dificuldade_respiratoria` | TEXT | Dificuldade para respirar |
| `tosse` | TEXT | Presença de tosse |
| `coriza` | TEXT | Coriza/nariz entupido |
| `dor_garganta` | TEXT | Dor de garganta |
| `diarreia` | TEXT | Diarreia |
| `cefaleia` | TEXT | Dor de cabeça |
| `comorbidade_pulmao` | TEXT | Doença pulmonar crônica |
| `comorbidade_cardio` | TEXT | Doença cardíaca |
| `comorbidade_renal` | TEXT | Doença renal |
| `comorbidade_diabetes` | TEXT | Diabetes |
| `comorbidade_tabagismo` | TEXT | Histórico de tabagismo |
| `comorbidade_obesidade` | TEXT | Obesidade |
| `ficou_internado` | TEXT | Necessidade de internação |

**Constraint**: UNIQUE sobre todas as colunas

---

### Dimensão: DIM_TESTE

**Propósito**: Resultados de diferentes tipos de testes COVID-19.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id_teste` | INTEGER | Chave primária (auto-increment) |
| `resultado_rt_pcr` | TEXT | Resultado RT-PCR (Positivo/Negativo/Indeterminado) |
| `resultado_teste_rapido` | TEXT | Resultado teste rápido |
| `resultado_sorologia` | TEXT | Resultado sorologia (anticorpos) |
| `resultado_sorologia_igg` | TEXT | Resultado específico IgG |
| `tipo_teste_rapido` | TEXT | Tipo de teste rápido utilizado |

**Constraint**: UNIQUE sobre todas as colunas

---

### Dimensão: DIM_SITUACAO

**Propósito**: Status e classificação da notificação.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id_situacao` | INTEGER | Chave primária (auto-increment) |
| `classificacao` | TEXT | Confirmado / Descartado / Suspeito |
| `evolucao` | TEXT | Cura / Óbito / Internação / etc |
| `criterio_confirmacao` | TEXT | Critério usado para confirmar |
| `status_notificacao` | TEXT | Ativo / Encerrado / etc |

**Constraint**: UNIQUE sobre todas as colunas

---

## 🔄 Fluxo de Dados

```
MICRODADOS.csv (Origem)
         ↓
    [ETL Pipeline]
    - Limpeza
    - Normalização
    - Deduplicação
         ↓
  [DW SQLite]
    - DIM_TEMPO
    - DIM_PACIENTE
    - DIM_LOCALIZACAO
    - DIM_CLINICA
    - DIM_TESTE
    - DIM_SITUACAO
    - FATO_NOTIFICACOES
         ↓
  [Dashboard Streamlit]
    - Filtros
    - Gráficos
    - Métricas
```

## 🎯 Vantagens do Esquema Estrela

✅ **Simplicidade**: Estrutura intuitiva com fatos no centro e dimensões ao redor
✅ **Desempenho**: Joins eficientes com poucas tabelas
✅ **Reusabilidade**: Dimensões compartilhadas entre múltiplos fatos
✅ **Escalabilidade**: Fácil adicionar novas dimensões ou medidas
✅ **Análises**: Suporta slicing, dicing, drill-down e agregações

## 📈 Exemplos de Análises Possíveis

- Casos por município, bairro e data
- Taxas de mortalidade por faixa etária e sexo
- Evolução temporal de sintomas e comorbidades
- Comparação de eficácia de testes
- Distribuição de internações por período
- Análise de pacientes com múltiplas comorbidades

---

**Criado para o projeto COVID DW | 2026**
