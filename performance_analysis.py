import sqlite3
import time
from pathlib import Path

import pandas as pd

CSV_PATH = Path('MICRODADOS.csv')
DB_PATH = Path('covid_dw.db')


def measure_csv_load():
    start = time.perf_counter()
    df = pd.read_csv(CSV_PATH, sep=';', encoding='latin1', low_memory=False)
    elapsed = time.perf_counter() - start
    memory = df.memory_usage(deep=True).sum() / 1024 ** 2
    return elapsed, memory, len(df)


def measure_dw_query():
    with sqlite3.connect(DB_PATH) as conn:
        start = time.perf_counter()
        count = pd.read_sql_query('SELECT COUNT(*) AS total FROM FATO_NOTIFICACOES', conn).iloc[0, 0]
        elapsed = time.perf_counter() - start
        return elapsed, count


def measure_response_times():
    with sqlite3.connect(DB_PATH) as conn:
        start = time.perf_counter()
        pd.read_sql_query(
            'SELECT l.municipio, COUNT(*) AS total FROM FATO_NOTIFICACOES f JOIN DIM_LOCALIZACAO l ON f.id_localizacao = l.id_localizacao GROUP BY l.municipio ORDER BY total DESC LIMIT 10',
            conn
        )
        query1 = time.perf_counter() - start

        start = time.perf_counter()
        pd.read_sql_query(
            "SELECT t.data, COUNT(*) AS total FROM FATO_NOTIFICACOES f JOIN DIM_TEMPO t ON f.id_tempo_notificacao = t.id_tempo GROUP BY t.data ORDER BY t.data LIMIT 100", conn
        )
        query2 = time.perf_counter() - start

    return query1, query2


def main():
    print('=== Análise de desempenho CSV vs DW ===')
    if not CSV_PATH.exists():
        raise FileNotFoundError('CSV não encontrado: ' + str(CSV_PATH))
    if not DB_PATH.exists():
        raise FileNotFoundError('DW não encontrado: ' + str(DB_PATH))

    csv_time, csv_memory, csv_rows = measure_csv_load()
    dw_time, dw_count = measure_dw_query()
    query1, query2 = measure_response_times()

    print(f'CSV load time: {csv_time:.2f}s | rows: {csv_rows:,} | memory: {csv_memory:.1f} MB')
    print(f'DW query time (count): {dw_time:.4f}s | rows in fact: {dw_count:,}')
    print(f'DW filter query time (top municípios): {query1:.4f}s')
    print(f'DW time-series query time: {query2:.4f}s')
    print('\nRecomendações:')
    print('- CSV é mais simples para protótipo, mas não escala bem quando múltiplos relatórios e filtros são necessários.')
    print('- DW permite reuso de dimensões, consultas SQL rápidas e menos processamento em memória por visualização.')

if __name__ == '__main__':
    main()
