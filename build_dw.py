import os
import csv
import sqlite3
import re
from datetime import datetime
import time

DB_NAME = 'covid_dw.db'
CSV_NAME = 'MICRODADOS.csv'
ROW_LIMIT = None  # Full load enabled.

# Date parsing utils
month_map = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'fev': 2, 'abr': 4, 'mai': 5, 'ago': 8, 'set': 9, 'out': 10, 'dez': 12
}

def parse_date(date_str):
    if not date_str or date_str.strip() == '' or date_str.lower() in ('null', 'na', '-', 'nulo'):
        return None
    
    date_str = date_str.strip()
    
    # 1. Format: YYYY-MM-DD
    match_ymd = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', date_str)
    if match_ymd:
        try:
            return datetime(int(match_ymd.group(1)), int(match_ymd.group(2)), int(match_ymd.group(3)))
        except ValueError:
            pass
            
    # 2. Format: DD/MM/YYYY
    match_dmy = re.match(r'^(\d{2})/(\d{2})/(\d{4})$', date_str)
    if match_dmy:
        try:
            return datetime(int(match_dmy.group(3)), int(match_dmy.group(2)), int(match_dmy.group(1)))
        except ValueError:
            pass

    # 3. Format: May 15 2026 12:00AM or May  7 2026 12:00AM
    parts = [p for p in re.split(r'\s+', date_str) if p]
    if len(parts) >= 3:
        month_str = parts[0].lower()[:3]
        if month_str in month_map:
            month = month_map[month_str]
            try:
                day = int(parts[1])
                year = int(parts[2][:4])
                return datetime(year, month, day)
            except (ValueError, IndexError):
                pass
                
    return None

def get_or_create_time_id(conn, date_obj, time_cache):
    if date_obj is None:
        return -1
    
    date_id = int(date_obj.strftime('%Y%m%d'))
    if date_id in time_cache:
        return date_id
        
    date_str = date_obj.strftime('%Y-%m-%d')
    ano = date_obj.year
    mes = date_obj.month
    
    meses_pt = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho',
        7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }
    mes_name = meses_pt.get(mes, 'Não Informado')
    dia = date_obj.day
    
    dias_pt = {
        0: 'Segunda-feira', 1: 'Terça-feira', 2: 'Quarta-feira', 3: 'Quinta-feira',
        4: 'Sexta-feira', 5: 'Sábado', 6: 'Domingo'
    }
    dia_semana = dias_pt.get(date_obj.weekday(), 'Não Informado')
    trimestre = (mes - 1) // 3 + 1
    
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO DIM_TEMPO (id_tempo, data, ano, mes, mes_nome, dia, dia_semana, trimestre)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (date_id, date_str, ano, mes, mes_name, dia, dia_semana, trimestre))
    time_cache[date_id] = date_id
    return date_id

# Helper to load existing dims into cache to allow resuming or safe execution
def init_caches(conn):
    caches = {
        'paciente': {},
        'localizacao': {},
        'clinica': {},
        'teste': {},
        'situacao': {},
        'tempo': { -1: -1 }
    }
    cursor = conn.cursor()
    
    # Load tempo
    cursor.execute("SELECT id_tempo FROM DIM_TEMPO")
    for r in cursor.fetchall():
        caches['tempo'][r[0]] = r[0]
        
    # Load paciente
    cursor.execute("SELECT id_paciente, sexo, faixa_etaria, raca_cor, escolaridade, gestante, profissional_saude, possui_deficiencia, morador_de_rua FROM DIM_PACIENTE")
    for r in cursor.fetchall():
        key = (r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8])
        caches['paciente'][key] = r[0]
        
    # Load localizacao
    cursor.execute("SELECT id_localizacao, municipio, bairro FROM DIM_LOCALIZACAO")
    for r in cursor.fetchall():
        key = (r[1], r[2])
        caches['localizacao'][key] = r[0]
        
    # Load clinica
    cursor.execute("SELECT id_clinica, febre, dificuldade_respiratoria, tosse, coriza, dor_garganta, diarreia, cefaleia, comorbidade_pulmao, comorbidade_cardio, comorbidade_renal, comorbidade_diabetes, comorbidade_tabagismo, comorbidade_obesidade, ficou_internado FROM DIM_CLINICA")
    for r in cursor.fetchall():
        key = (r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12], r[13], r[14])
        caches['clinica'][key] = r[0]
        
    # Load teste
    cursor.execute("SELECT id_teste, resultado_rt_pcr, resultado_teste_rapido, resultado_sorologia, resultado_sorologia_igg, tipo_teste_rapido FROM DIM_TESTE")
    for r in cursor.fetchall():
        key = (r[1], r[2], r[3], r[4], r[5])
        caches['teste'][key] = r[0]
        
    # Load situacao
    cursor.execute("SELECT id_situacao, classificacao, evolucao, criterio_confirmacao, status_notificacao FROM DIM_SITUACAO")
    for r in cursor.fetchall():
        key = (r[1], r[2], r[3], r[4])
        caches['situacao'][key] = r[0]
        
    return caches

def create_schema(conn):
    print("Criando o esquema do DW...")
    cursor = conn.cursor()
    
    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    cursor.execute("DROP TABLE IF EXISTS FATO_NOTIFICACOES;")
    cursor.execute("DROP TABLE IF EXISTS DIM_TEMPO;")
    cursor.execute("DROP TABLE IF EXISTS DIM_PACIENTE;")
    cursor.execute("DROP TABLE IF EXISTS DIM_LOCALIZACAO;")
    cursor.execute("DROP TABLE IF EXISTS DIM_CLINICA;")
    cursor.execute("DROP TABLE IF EXISTS DIM_TESTE;")
    cursor.execute("DROP TABLE IF EXISTS DIM_SITUACAO;")
    
    # 1. DIM_TEMPO
    cursor.execute("""
    CREATE TABLE DIM_TEMPO (
        id_tempo INTEGER PRIMARY KEY,
        data TEXT NOT NULL,
        ano INTEGER NOT NULL,
        mes INTEGER NOT NULL,
        mes_nome TEXT NOT NULL,
        dia INTEGER NOT NULL,
        dia_semana TEXT NOT NULL,
        trimestre INTEGER NOT NULL
    );
    """)
    
    # Insert Sentinel Row for Missing Dates
    cursor.execute("""
    INSERT INTO DIM_TEMPO (id_tempo, data, ano, mes, mes_nome, dia, dia_semana, trimestre)
    VALUES (-1, 'Não Informado', 0, 0, 'Não Informado', 0, 'Não Informado', 0);
    """)
    
    # Pre-populate calendar days from 2020-01-01 to 2026-12-31
    print("Pré-populando a dimensão tempo (2020 a 2026)...")
    from datetime import date, timedelta
    start_date = date(2020, 1, 1)
    end_date = date(2026, 12, 31)
    
    meses_pt = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho',
        7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }
    dias_pt = {
        0: 'Segunda-feira', 1: 'Terça-feira', 2: 'Quarta-feira', 3: 'Quinta-feira',
        4: 'Sexta-feira', 5: 'Sábado', 6: 'Domingo'
    }
    
    curr = start_date
    time_records = []
    while curr <= end_date:
        date_id = int(curr.strftime('%Y%m%d'))
        date_str = curr.strftime('%Y-%m-%d')
        ano = curr.year
        mes = curr.month
        mes_nome = meses_pt[mes]
        dia = curr.day
        dia_semana = dias_pt[curr.weekday()]
        trimestre = (mes - 1) // 3 + 1
        
        time_records.append((date_id, date_str, ano, mes, mes_nome, dia, dia_semana, trimestre))
        curr += timedelta(days=1)
        
    cursor.executemany("""
        INSERT INTO DIM_TEMPO (id_tempo, data, ano, mes, mes_nome, dia, dia_semana, trimestre)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, time_records)

    
    # 2. DIM_PACIENTE
    cursor.execute("""
    CREATE TABLE DIM_PACIENTE (
        id_paciente INTEGER PRIMARY KEY AUTOINCREMENT,
        sexo TEXT,
        faixa_etaria TEXT,
        raca_cor TEXT,
        escolaridade TEXT,
        gestante TEXT,
        profissional_saude TEXT,
        possui_deficiencia TEXT,
        morador_de_rua TEXT,
        UNIQUE(sexo, faixa_etaria, raca_cor, escolaridade, gestante, profissional_saude, possui_deficiencia, morador_de_rua)
    );
    """)
    
    # 3. DIM_LOCALIZACAO
    cursor.execute("""
    CREATE TABLE DIM_LOCALIZACAO (
        id_localizacao INTEGER PRIMARY KEY AUTOINCREMENT,
        municipio TEXT,
        bairro TEXT,
        UNIQUE(municipio, bairro)
    );
    """)
    
    # 4. DIM_CLINICA
    cursor.execute("""
    CREATE TABLE DIM_CLINICA (
        id_clinica INTEGER PRIMARY KEY AUTOINCREMENT,
        febre TEXT,
        dificuldade_respiratoria TEXT,
        tosse TEXT,
        coriza TEXT,
        dor_garganta TEXT,
        diarreia TEXT,
        cefaleia TEXT,
        comorbidade_pulmao TEXT,
        comorbidade_cardio TEXT,
        comorbidade_renal TEXT,
        comorbidade_diabetes TEXT,
        comorbidade_tabagismo TEXT,
        comorbidade_obesidade TEXT,
        ficou_internado TEXT,
        UNIQUE(febre, dificuldade_respiratoria, tosse, coriza, dor_garganta, diarreia, cefaleia, 
               comorbidade_pulmao, comorbidade_cardio, comorbidade_renal, comorbidade_diabetes, 
               comorbidade_tabagismo, comorbidade_obesidade, ficou_internado)
    );
    """)
    
    # 5. DIM_TESTE
    cursor.execute("""
    CREATE TABLE DIM_TESTE (
        id_teste INTEGER PRIMARY KEY AUTOINCREMENT,
        resultado_rt_pcr TEXT,
        resultado_teste_rapido TEXT,
        resultado_sorologia TEXT,
        resultado_sorologia_igg TEXT,
        tipo_teste_rapido TEXT,
        UNIQUE(resultado_rt_pcr, resultado_teste_rapido, resultado_sorologia, resultado_sorologia_igg, tipo_teste_rapido)
    );
    """)
    
    # 6. DIM_SITUACAO
    cursor.execute("""
    CREATE TABLE DIM_SITUACAO (
        id_situacao INTEGER PRIMARY KEY AUTOINCREMENT,
        classificacao TEXT,
        evolucao TEXT,
        criterio_confirmacao TEXT,
        status_notificacao TEXT,
        UNIQUE(classificacao, evolucao, criterio_confirmacao, status_notificacao)
    );
    """)
    
    # 7. FATO_NOTIFICACOES
    cursor.execute("""
    CREATE TABLE FATO_NOTIFICACOES (
        id_fato INTEGER PRIMARY KEY AUTOINCREMENT,
        id_tempo_notificacao INTEGER,
        id_tempo_diagnostico INTEGER,
        id_tempo_encerramento INTEGER,
        id_paciente INTEGER,
        id_localizacao INTEGER,
        id_clinica INTEGER,
        id_teste INTEGER,
        id_situacao INTEGER,
        quantidade_casos INTEGER DEFAULT 1,
        obito INTEGER DEFAULT 0,
        confirmado INTEGER DEFAULT 0,
        internado INTEGER DEFAULT 0,
        FOREIGN KEY(id_tempo_notificacao) REFERENCES DIM_TEMPO(id_tempo),
        FOREIGN KEY(id_tempo_diagnostico) REFERENCES DIM_TEMPO(id_tempo),
        FOREIGN KEY(id_tempo_encerramento) REFERENCES DIM_TEMPO(id_tempo),
        FOREIGN KEY(id_paciente) REFERENCES DIM_PACIENTE(id_paciente),
        FOREIGN KEY(id_localizacao) REFERENCES DIM_LOCALIZACAO(id_localizacao),
        FOREIGN KEY(id_clinica) REFERENCES DIM_CLINICA(id_clinica),
        FOREIGN KEY(id_teste) REFERENCES DIM_TESTE(id_teste),
        FOREIGN KEY(id_situacao) REFERENCES DIM_SITUACAO(id_situacao)
    );
    """)
    
    conn.commit()
    print("Tabelas criadas com sucesso!")

def run_etl(conn, csv_path):
    print("Iniciando processo de ETL...")
    cursor = conn.cursor()
    caches = init_caches(conn)
    
    # Detect delimiter and encoding dynamically
    delimiters = [';', ',', '\t']
    encodings = ['utf-8', 'latin1', 'iso-8859-1']
    detected_delimiter = ';'
    detected_encoding = 'latin1'
    
    for encoding in encodings:
        for delimiter in delimiters:
            try:
                with open(csv_path, 'r', encoding=encoding) as f:
                    first_line = f.readline()
                    if delimiter in first_line:
                        detected_delimiter = delimiter
                        detected_encoding = encoding
                        break
            except Exception:
                continue
        if detected_delimiter:
            break
            
    print(f"Lendo CSV com delimitador='{detected_delimiter}' e encoding='{detected_encoding}'")
    
    start_time = time.time()
    
    with open(csv_path, 'r', encoding=detected_encoding) as f:
        reader = csv.reader(f, delimiter=detected_delimiter)
        headers = next(reader)
        
        # Build column index mapping
        col_idx = {col: i for i, col in enumerate(headers)}
        
        facts_to_insert = []
        batch_size = 10000
        count = 0
        
        # Start a big transaction for execution speed
        conn.execute("BEGIN TRANSACTION;")
        
        for row in reader:
            if not row:
                continue
                
            count += 1
            if ROW_LIMIT and count > ROW_LIMIT:
                break
                
            # Safely fetch field values by name
            def get_val(col_name, default=''):
                idx = col_idx.get(col_name)
                if idx is not None and idx < len(row):
                    return row[idx].strip()
                return default

            # 1. Parse Dates and Get time dimension IDs
            dt_notif = parse_date(get_val('DataNotificacao'))
            dt_diag = parse_date(get_val('DataDiagnostico'))
            dt_enc = parse_date(get_val('DataEncerramento'))
            
            id_t_notif = get_or_create_time_id(conn, dt_notif, caches['tempo'])
            id_t_diag = get_or_create_time_id(conn, dt_diag, caches['tempo'])
            id_t_enc = get_or_create_time_id(conn, dt_enc, caches['tempo'])
            
            # 2. DIM_PACIENTE
            paciente_key = (
                get_val('Sexo', 'I'),
                get_val('FaixaEtaria', 'Ignorado'),
                get_val('RacaCor', 'Ignorado'),
                get_val('Escolaridade', 'Ignorado'),
                get_val('Gestante', 'Não se aplica'),
                get_val('ProfissionalSaude', 'Não'),
                get_val('PossuiDeficiencia', 'Não'),
                get_val('MoradorDeRua', 'Não')
            )
            if paciente_key not in caches['paciente']:
                cursor.execute("""
                    INSERT OR IGNORE INTO DIM_PACIENTE (sexo, faixa_etaria, raca_cor, escolaridade, gestante, profissional_saude, possui_deficiencia, morador_de_rua)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, paciente_key)
                cursor.execute("""
                    SELECT id_paciente FROM DIM_PACIENTE 
                    WHERE sexo=? AND faixa_etaria=? AND raca_cor=? AND escolaridade=? AND gestante=? AND profissional_saude=? AND possui_deficiencia=? AND morador_de_rua=?
                """, paciente_key)
                caches['paciente'][paciente_key] = cursor.fetchone()[0]
            id_paciente = caches['paciente'][paciente_key]
            
            # 3. DIM_LOCALIZACAO
            loc_key = (
                get_val('Municipio', 'Não Informado'),
                get_val('Bairro', 'Não Informado')
            )
            if loc_key not in caches['localizacao']:
                cursor.execute("""
                    INSERT OR IGNORE INTO DIM_LOCALIZACAO (municipio, bairro)
                    VALUES (?, ?)
                """, loc_key)
                cursor.execute("SELECT id_localizacao FROM DIM_LOCALIZACAO WHERE municipio=? AND bairro=?", loc_key)
                caches['localizacao'][loc_key] = cursor.fetchone()[0]
            id_localizacao = caches['localizacao'][loc_key]
            
            # 4. DIM_CLINICA
            clinica_key = (
                get_val('Febre', 'Não'),
                get_val('DificuldadeRespiratoria', 'Não'),
                get_val('Tosse', 'Não'),
                get_val('Coriza', 'Não'),
                get_val('DorGarganta', 'Não'),
                get_val('Diarreia', 'Não'),
                get_val('Cefaleia', 'Não'),
                get_val('ComorbidadePulmao', 'Não'),
                get_val('ComorbidadeCardio', 'Não'),
                get_val('ComorbidadeRenal', 'Não'),
                get_val('ComorbidadeDiabetes', 'Não'),
                get_val('ComorbidadeTabagismo', 'Não'),
                get_val('ComorbidadeObesidade', 'Não'),
                get_val('FicouInternado', 'Não')
            )
            if clinica_key not in caches['clinica']:
                cursor.execute("""
                    INSERT OR IGNORE INTO DIM_CLINICA (febre, dificuldade_respiratoria, tosse, coriza, dor_garganta, diarreia, cefaleia, 
                           comorbidade_pulmao, comorbidade_cardio, comorbidade_renal, comorbidade_diabetes, 
                           comorbidade_tabagismo, comorbidade_obesidade, ficou_internado)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, clinica_key)
                cursor.execute("""
                    SELECT id_clinica FROM DIM_CLINICA 
                    WHERE febre=? AND dificuldade_respiratoria=? AND tosse=? AND coriza=? AND dor_garganta=? AND diarreia=? AND cefaleia=? 
                      AND comorbidade_pulmao=? AND comorbidade_cardio=? AND comorbidade_renal=? AND comorbidade_diabetes=? 
                      AND comorbidade_tabagismo=? AND comorbidade_obesidade=? AND ficou_internado=?
                """, clinica_key)
                caches['clinica'][clinica_key] = cursor.fetchone()[0]
            id_clinica = caches['clinica'][clinica_key]
            
            # 5. DIM_TESTE
            teste_key = (
                get_val('ResultadoRT_PCR', 'Não Informado'),
                get_val('ResultadoTesteRapido', 'Não Informado'),
                get_val('ResultadoSorologia', 'Não Informado'),
                get_val('ResultadoSorologia_IGG', 'Não Informado'),
                get_val('TipoTesteRapido', 'Não Informado')
            )
            if teste_key not in caches['teste']:
                cursor.execute("""
                    INSERT OR IGNORE INTO DIM_TESTE (resultado_rt_pcr, resultado_teste_rapido, resultado_sorologia, resultado_sorologia_igg, tipo_teste_rapido)
                    VALUES (?, ?, ?, ?, ?)
                """, teste_key)
                cursor.execute("""
                    SELECT id_teste FROM DIM_TESTE 
                    WHERE resultado_rt_pcr=? AND resultado_teste_rapido=? AND resultado_sorologia=? AND resultado_sorologia_igg=? AND tipo_teste_rapido=?
                """, teste_key)
                caches['teste'][teste_key] = cursor.fetchone()[0]
            id_teste = caches['teste'][teste_key]
            
            # 6. DIM_SITUACAO
            situacao_key = (
                get_val('Classificacao', 'Suspeito'),
                get_val('Evolucao', '-'),
                get_val('CriterioConfirmacao', '-'),
                get_val('StatusNotificacao', 'Em Aberto')
            )
            if situacao_key not in caches['situacao']:
                cursor.execute("""
                    INSERT OR IGNORE INTO DIM_SITUACAO (classificacao, evolucao, criterio_confirmacao, status_notificacao)
                    VALUES (?, ?, ?, ?)
                """, situacao_key)
                cursor.execute("""
                    SELECT id_situacao FROM DIM_SITUACAO 
                    WHERE classificacao=? AND evolucao=? AND criterio_confirmacao=? AND status_notificacao=?
                """, situacao_key)
                caches['situacao'][situacao_key] = cursor.fetchone()[0]
            id_situacao = caches['situacao'][situacao_key]
            
            # 7. Fact Table Metrics
            # obito = 1 if Evolucao contains "Óbito" or DataObito is not null/empty
            evolucao = get_val('Evolucao').lower()
            data_obito = get_val('DataObito')
            obito = 1 if ('obito' in evolucao or 'óbito' in evolucao or (data_obito and data_obito.strip() != '')) else 0
            
            # confirmado = 1 if Classificacao is "Confirmados"
            confirmado = 1 if get_val('Classificacao') == 'Confirmados' else 0
            
            # internado = 1 if FicouInternado == 'Sim'
            internado = 1 if get_val('FicouInternado') == 'Sim' else 0
            
            facts_to_insert.append((
                id_t_notif, id_t_diag, id_t_enc,
                id_paciente, id_localizacao, id_clinica, id_teste, id_situacao,
                1, obito, confirmado, internado
            ))
            
            # Commit and insert in batches
            if len(facts_to_insert) >= batch_size:
                cursor.executemany("""
                    INSERT INTO FATO_NOTIFICACOES (
                        id_tempo_notificacao, id_tempo_diagnostico, id_tempo_encerramento,
                        id_paciente, id_localizacao, id_clinica, id_teste, id_situacao,
                        quantidade_casos, obito, confirmado, internado
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, facts_to_insert)
                facts_to_insert = []
                
                # Commit current chunk to release locks periodically
                conn.commit()
                conn.execute("BEGIN TRANSACTION;")
                print(f"Processadas {count} linhas...")
                
        # Insert any remaining facts
        if facts_to_insert:
            cursor.executemany("""
                INSERT INTO FATO_NOTIFICACOES (
                    id_tempo_notificacao, id_tempo_diagnostico, id_tempo_encerramento,
                    id_paciente, id_localizacao, id_clinica, id_teste, id_situacao,
                    quantidade_casos, obito, confirmado, internado
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, facts_to_insert)
            
        conn.commit()
        
    end_time = time.time()
    elapsed = end_time - start_time
    print(f"\nETL finalizado com sucesso!")
    print(f"Total de registros importados para a fato: {count}")
    print(f"Tempo total gasto: {elapsed:.2f} segundos ({count / elapsed:.1f} linhas/segundo)")

def analyze_db(conn):
    print("\n=== ESTATÍSTICAS DO BANCO DE DADOS (DW) ===")
    cursor = conn.cursor()
    tables = ['DIM_TEMPO', 'DIM_PACIENTE', 'DIM_LOCALIZACAO', 'DIM_CLINICA', 'DIM_TESTE', 'DIM_SITUACAO', 'FATO_NOTIFICACOES']
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"Tabela '{table}': {cursor.fetchone()[0]} registros")

if __name__ == '__main__':
    conn = sqlite3.connect(DB_NAME)
    
    # Speed optimizations for SQLite
    conn.execute("PRAGMA journal_mode = OFF;")
    conn.execute("PRAGMA synchronous = OFF;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA cache_size = -500000;") # 500MB cache

    
    # Create the Schema
    create_schema(conn)
    
    # Run the ETL Process
    run_etl(conn, CSV_NAME)
    
    # Analyze final database counts
    analyze_db(conn)
    
    conn.close()
