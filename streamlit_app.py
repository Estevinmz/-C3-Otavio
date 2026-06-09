#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Dashboard COVID-19 - CSV vs Data Warehouse
Compara análises de dados usando CSV direto e Data Warehouse em SQLite

Versão: 2.0 (Dual-Source)
"""

import glob
import os
import sqlite3
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import time

# ============= CONFIGURAÇÃO INICIAL =============
st.set_page_config(
    page_title='Dashboard COVID (CSV vs DW)',
    layout='wide',
    initial_sidebar_state='expanded'
)

# Cores e estilos
COLORS = {
    'csv': '#FF6B6B',      # Vermelho
    'dw': '#4ECDC4',       # Verde/Azul
    'neutral': '#95E1D3'   # Verde claro
}

DB_PATHS = ['covid_dw.db']
CSV_PATH = 'MICRODADOS.csv'

# ============= CACHE E CONEXÕES =============

@st.cache_resource
def get_db_connection():
    """Conecta ao Data Warehouse SQLite"""
    fresh_candidates = sorted(glob.glob('covid_dw_fresh*.db'))
    db_path = fresh_candidates[-1] if fresh_candidates else (
        [p for p in DB_PATHS if os.path.exists(p)][0] if [p for p in DB_PATHS if os.path.exists(p)] else None
    )
    if not db_path:
        raise FileNotFoundError('Nenhum banco de dados DW encontrado. Execute dw_pipeline.py primeiro.')
    return sqlite3.connect(db_path, check_same_thread=False)

@st.cache_data
def load_csv_data():
    """Carrega dados do CSV"""
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f'Arquivo CSV não encontrado: {CSV_PATH}')
    
    return pd.read_csv(CSV_PATH, sep=';', encoding='latin1', low_memory=False)

@st.cache_data
def get_frame_dw(query, params=None):
    """Query no Data Warehouse"""
    conn = get_db_connection()
    return pd.read_sql_query(query, conn, params=params)


@st.cache_data
def get_unique_values_dw(column, table, where_clause=None):
    """Valores únicos do DW"""
    conn = get_db_connection()
    query = f'SELECT DISTINCT {column} FROM {table}'
    if where_clause:
        query += f' WHERE {where_clause}'
    return sorted([row[0] for row in conn.execute(query).fetchall() if row[0]])

@st.cache_data
def get_unique_values_csv(column, df):
    """Valores únicos do CSV"""
    return sorted([str(v) for v in df[column].unique() if pd.notna(v)])

@st.cache_data
def get_date_range_dw():
    """Range de datas no DW"""
    conn = get_db_connection()
    query = 'SELECT MIN(data), MAX(data) FROM DIM_TEMPO WHERE id_tempo != -1'
    row = conn.execute(query).fetchone()
    return row[0], row[1]

@st.cache_data
def get_date_range_csv(df):
    """Range de datas no CSV"""
    try:
        df_dates = pd.to_datetime(df['DataNotificacao'], errors='coerce')
        return str(df_dates.min().date()), str(df_dates.max().date())
    except:
        return None, None

# ============= FUNÇÕES DE ANÁLISE - DATA WAREHOUSE =============

@st.cache_data
def get_summary_dw(filters):
    """Resumo de notificações (DW)"""
    conn = get_db_connection()
    conditions = []
    params = []

    if filters.get('municipio'):
        conditions.append('l.municipio = ?')
        params.append(filters['municipio'])
    if filters.get('classificacao'):
        conditions.append('s.classificacao = ?')
        params.append(filters['classificacao'])
    if filters.get('data_inicio'):
        conditions.append('t.data >= ?')
        params.append(filters['data_inicio'])
    if filters.get('data_fim'):
        conditions.append('t.data <= ?')
        params.append(filters['data_fim'])

    where_sql = 'WHERE ' + ' AND '.join(conditions) if conditions else ''

    summary_query = f'''
        SELECT
            COUNT(*) AS total_notificacoes,
            SUM(f.confirmado) AS total_confirmados,
            SUM(f.obito) AS total_obitos,
            SUM(f.internado) AS total_internados
        FROM FATO_NOTIFICACOES f
        JOIN DIM_LOCALIZACAO l ON f.id_localizacao = l.id_localizacao
        JOIN DIM_SITUACAO s ON f.id_situacao = s.id_situacao
        JOIN DIM_TEMPO t ON f.id_tempo_notificacao = t.id_tempo
        {where_sql}
    '''
    return pd.read_sql_query(summary_query, conn, params=params)

@st.cache_data
def get_time_series_dw(filters):
    """Série temporal (DW)"""
    conn = get_db_connection()
    conditions = []
    params = []

    if filters.get('municipio'):
        conditions.append('l.municipio = ?')
        params.append(filters['municipio'])
    if filters.get('classificacao'):
        conditions.append('s.classificacao = ?')
        params.append(filters['classificacao'])
    if filters.get('data_inicio'):
        conditions.append('t.data >= ?')
        params.append(filters['data_inicio'])
    if filters.get('data_fim'):
        conditions.append('t.data <= ?')
        params.append(filters['data_fim'])

    where_sql = 'WHERE ' + ' AND '.join(conditions) if conditions else ''
    query = f'''
        SELECT t.data AS data, COUNT(*) AS notificacoes
        FROM FATO_NOTIFICACOES f
        JOIN DIM_TEMPO t ON f.id_tempo_notificacao = t.id_tempo
        JOIN DIM_LOCALIZACAO l ON f.id_localizacao = l.id_localizacao
        JOIN DIM_SITUACAO s ON f.id_situacao = s.id_situacao
        {where_sql}
        GROUP BY t.data
        ORDER BY t.data
    '''
    df = pd.read_sql_query(query, conn, params=params)
    if not df.empty:
        df['data'] = pd.to_datetime(df['data'])
        df = df.set_index('data')
    return df

@st.cache_data
def get_top_municipios_dw(filters, limit=10):
    """Top municípios (DW)"""
    conn = get_db_connection()
    conditions = []
    params = []

    if filters.get('classificacao'):
        conditions.append('s.classificacao = ?')
        params.append(filters['classificacao'])
    if filters.get('data_inicio'):
        conditions.append('t.data >= ?')
        params.append(filters['data_inicio'])
    if filters.get('data_fim'):
        conditions.append('t.data <= ?')
        params.append(filters['data_fim'])

    where_sql = 'WHERE ' + ' AND '.join(conditions) if conditions else ''
    query = f'''
        SELECT l.municipio AS municipio, COUNT(*) AS total
        FROM FATO_NOTIFICACOES f
        JOIN DIM_LOCALIZACAO l ON f.id_localizacao = l.id_localizacao
        JOIN DIM_TEMPO t ON f.id_tempo_notificacao = t.id_tempo
        JOIN DIM_SITUACAO s ON f.id_situacao = s.id_situacao
        {where_sql}
        GROUP BY l.municipio
        ORDER BY total DESC
        LIMIT {limit}
    '''
    return pd.read_sql_query(query, conn, params=params)

# ============= FUNÇÕES DE ANÁLISE - CSV =============

def get_summary_csv(df, filters):
    """Resumo de notificações (CSV)"""
    df_filtered = df.copy()
    
    if filters.get('municipio'):
        df_filtered = df_filtered[df_filtered['Municipio'] == filters['municipio']]
    if filters.get('classificacao'):
        df_filtered = df_filtered[df_filtered['Classificacao'] == filters['classificacao']]
    if filters.get('data_inicio'):
        df_filtered = df_filtered[pd.to_datetime(df_filtered['DataNotificacao'], errors='coerce') >= filters['data_inicio']]
    if filters.get('data_fim'):
        df_filtered = df_filtered[pd.to_datetime(df_filtered['DataNotificacao'], errors='coerce') <= filters['data_fim']]
    
    return pd.DataFrame({
        'total_notificacoes': [len(df_filtered)],
        'total_confirmados': [len(df_filtered[df_filtered['Classificacao'] == 'Confirmado']) if 'Classificacao' in df_filtered.columns else 0],
        'total_obitos': [len(df_filtered[(df_filtered['Evolucao'] == 'Óbito') | (df_filtered['Evolucao'] == 'Obito')]) if 'Evolucao' in df_filtered.columns else 0],
        'total_internados': [len(df_filtered[df_filtered['FicouInternado'] == 'Sim']) if 'FicouInternado' in df_filtered.columns else 0]
    })

def get_time_series_csv(df, filters):
    """Série temporal (CSV)"""
    df_filtered = df.copy()
    
    if filters.get('municipio'):
        df_filtered = df_filtered[df_filtered['Municipio'] == filters['municipio']]
    if filters.get('classificacao'):
        df_filtered = df_filtered[df_filtered['Classificacao'] == filters['classificacao']]
    if filters.get('data_inicio'):
        df_filtered = df_filtered[pd.to_datetime(df_filtered['DataNotificacao'], errors='coerce') >= filters['data_inicio']]
    if filters.get('data_fim'):
        df_filtered = df_filtered[pd.to_datetime(df_filtered['DataNotificacao'], errors='coerce') <= filters['data_fim']]
    
    df_filtered['data'] = pd.to_datetime(df_filtered['DataNotificacao'], errors='coerce')
    ts = df_filtered.groupby('data').size().reset_index(name='notificacoes')
    ts = ts.set_index('data')
    return ts

def get_top_municipios_csv(df, filters, limit=10):
    """Top municípios (CSV)"""
    df_filtered = df.copy()
    
    if filters.get('classificacao'):
        df_filtered = df_filtered[df_filtered['Classificacao'] == filters['classificacao']]
    if filters.get('data_inicio'):
        df_filtered = df_filtered[pd.to_datetime(df_filtered['DataNotificacao'], errors='coerce') >= filters['data_inicio']]
    if filters.get('data_fim'):
        df_filtered = df_filtered[pd.to_datetime(df_filtered['DataNotificacao'], errors='coerce') <= filters['data_fim']]
    
    top = df_filtered['Municipio'].value_counts().head(limit).reset_index()
    top.columns = ['municipio', 'total']
    return top


def main():
    st.set_page_config(page_title='Dashboard COVID DW', layout='wide')
    st.title('Dashboard COVID - Data Warehouse')

    data_inicio, data_fim = get_date_range()
    st.sidebar.header('Filtros de análise')

    municipios = get_unique_values('municipio', 'DIM_LOCALIZACAO')
    classificacoes = get_unique_values('classificacao', 'DIM_SITUACAO')

    selected_municipio = st.sidebar.selectbox('Município', ['Todos'] + municipios)
    selected_classificacao = st.sidebar.selectbox('Classificação', ['Todas'] + classificacoes)

    data_range = st.sidebar.date_input('Período de notificação', [datetime.fromisoformat(data_inicio).date(), datetime.fromisoformat(data_fim).date()])
    start_date = data_range[0].isoformat() if len(data_range) > 0 else data_inicio
    end_date = data_range[1].isoformat() if len(data_range) > 1 else data_fim

    filters = {
        'municipio': None if selected_municipio == 'Todos' else selected_municipio,
        'classificacao': None if selected_classificacao == 'Todas' else selected_classificacao,
        'data_inicio': start_date,
        'data_fim': end_date
    }

    summary = get_summary(filters)
    st.metric('Total de notificações', int(summary.at[0, 'total_notificacoes'] or 0))
    st.metric('Total confirmados', int(summary.at[0, 'total_confirmados'] or 0))
    st.metric('Total óbitos', int(summary.at[0, 'total_obitos'] or 0))
    st.metric('Total internados', int(summary.at[0, 'total_internados'] or 0))

    st.subheader('Série temporal de notificações')
    ts = get_time_series(filters)
    st.line_chart(ts)

    st.subheader('Top municípios')
    top = get_top_municipios(filters)
    st.bar_chart(top.rename(columns={'municipio': 'index'}).set_index('municipio'))

    if st.checkbox('Mostrar consultas SQL brutas'):
        st.code(get_time_series(filters).to_csv(index=True))

    st.subheader('Detalhes dos dados do DW')
    data_sql = f'''
        SELECT t.data AS data_notificacao, l.municipio, l.bairro, s.classificacao, s.evolucao, f.obito, f.confirmado, f.internado
        FROM FATO_NOTIFICACOES f
        JOIN DIM_TEMPO t ON f.id_tempo_notificacao = t.id_tempo
        JOIN DIM_LOCALIZACAO l ON f.id_localizacao = l.id_localizacao
        JOIN DIM_SITUACAO s ON f.id_situacao = s.id_situacao
        WHERE t.data BETWEEN ? AND ?
        ORDER BY t.data DESC
        LIMIT 200
    '''
    conn = get_connection()
    st.dataframe(pd.read_sql_query(data_sql, conn, params=[start_date, end_date]))

if __name__ == '__main__':
    main()
