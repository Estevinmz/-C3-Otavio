# COVID DW Projeto - Data Warehouse e Dashboard

📊 Pipeline de ETL + Data Warehouse dimensional em SQLite + Dashboard Streamlit com análise de desempenho

## 📋 Sobre o Projeto

Este projeto implementa uma solução completa de Business Intelligence para dados de COVID-19:
- **ETL Pipeline**: Extrai dados do `MICRODADOS.csv`, aplica transformações e normalização
- **Data Warehouse**: Modelo dimensional (esquema estrela) em SQLite para análises rápidas
- **Dashboard Interativo**: Interface Streamlit para visualizações e filtros
- **Análise de Desempenho**: Comparação CSV vs DW com métricas de tempo e memória

## 📁 Estrutura do Projeto

```
.
├── dw_pipeline.py              # ETL principal - cria DW e carrega dados
├── build_dw.py                 # Utilitários para construção do DW
├── streamlit_app.py            # Dashboard interativo
├── performance_analysis.py      # Análise de desempenho CSV vs DW
├── inspect_csv.py              # Inspeção dos dados brutos
├── MICRODADOS.csv              # Dados fonte (COVID-19)
├── covid_dw.db                 # Banco de dados dimensional (gerado)
├── requirements.txt            # Dependências Python
├── build_dw.log                # Logs do pipeline (gerado)
└── README.md                   # Este arquivo
```

## 🚀 Início Rápido

### 1. Clone e configure o ambiente

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/covid-dw-projeto.git
cd covid-dw-projeto

# Crie um ambiente virtual
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 2. Instale dependências

```bash
pip install -r requirements.txt
```

### 3. Execute o pipeline ETL

```bash
python dw_pipeline.py
```

Isso criará o banco de dados `covid_dw.db` com o modelo dimensional.

### 4. Inicie o dashboard Streamlit

```bash
streamlit run streamlit_app.py
```

Acesse em `http://localhost:8501`

### 5. Verifique o desempenho

```bash
python performance_analysis.py
```

## 🏗️ Modelo Dimensional

O Data Warehouse usa um **esquema estrela** com:

**Tabelas de Dimensão:**
- `DIM_TEMPO`: Datas e períodos (ano, mês, trimestre, dia da semana)
- `DIM_PACIENTE`: Informações do paciente (sexo, faixa etária, comorbidades)
- `DIM_LOCALIZACAO`: Localização geográfica (município, bairro, região)
- `DIM_CLINICA`: Sintomas e condições clínicas
- `DIM_TESTE`: Informações de testes (tipo, resultado)
- `DIM_SITUACAO`: Status da notificação (confirmado, descartado, etc)

**Tabela de Fatos:**
- `FATO_NOTIFICACOES`: Registros centrais ligando todas as dimensões

[Ver diagrama detalhado em ARQUITETURA.md](ARQUITETURA.md)

## 📊 Funcionalidades do Dashboard

- 📅 Filtros por data, município, sexo, faixa etária
- 📈 Gráficos interativos (tendências, distribuições, mapas)
- 🔍 Busca por localização geográfica
- 📑 Comparação de períodos
- 💾 Exportação de relatórios

## 📈 Análise de Desempenho

O projeto inclui benchmarks comparando:
- **CSV**: Tempo de carga, uso de memória
- **DW**: Tempo de consultas SQL, reuso de dimensões
- **Queries**: Tempo de resposta para diferentes filtros

Ver resultados em `performance_analysis.py`

## 🛠️ Tecnologias

- **Python 3.8+**
- **SQLite**: Banco de dados dimensional
- **Pandas**: Processamento de dados
- **Streamlit**: Dashboard web
- **Matplotlib/Seaborn**: Visualizações
- **Logging**: Rastreamento de ETL

## 📝 Documentação

- [ARQUITETURA.md](ARQUITETURA.md): Modelo dimensional e schema
- [ETL.md](ETL.md): Pipeline de transformação, fontes e logs
- [DESEMPENHO.md](DESEMPENHO.md): Relatório de análise e métricas



## 📄 Licença

MIT License - veja LICENSE.txt
