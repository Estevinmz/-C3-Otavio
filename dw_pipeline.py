import csv
import logging
import os
import re
import sqlite3
import time
from datetime import date, datetime, timedelta

DB_NAME = 'covid_dw.db'
ALT_DB_NAME = 'covid_dw_fresh.db'
CSV_NAME = 'MICRODADOS.csv'
LOG_FILE = 'build_dw.log'
ROW_LIMIT = None  # Ajuste para depuração; None carrega todo o CSV.

month_map = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'fev': 2, 'abr': 4, 'mai': 5, 'ago': 8, 'set': 9, 'out': 10, 'dez': 12
}


def setup_logger():
    logger = logging.getLogger('dw_pipeline')
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def normalize_text(value, default='Não Informado'):
    if value is None:
        return default
    text = str(value).strip()
    if not text or text.lower() in ('nan', 'null', 'na', '-', 'nulo', 'não informado', 'desconhecido'):
        return default
    return text


def normalize_yes_no(value):
    if value is None:
        return 'Não'
    text = str(value).strip().lower()
    if text in ('sim', 's', 'yes', 'y', '1', 'true', 'verdadeiro'):
        return 'Sim'
    if text in ('nao', 'não', 'n', 'no', '0', 'false', 'f'):
        return 'Não'
    if text in ('não se aplica', 'nao se aplica', 'naoseaplica'):
        return 'Não se aplica'
    return normalize_text(value)


def infer_regiao(municipio):
    return 'Não Informado'


def parse_date(date_str):
    if not date_str:
        return None
    value = str(date_str).strip()
    if not value or value.lower() in ('null', 'na', '-', 'nulo', 'nan'):
        return None

    match_ymd = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', value)
    if match_ymd:
        try:
            return datetime(int(match_ymd.group(1)), int(match_ymd.group(2)), int(match_ymd.group(3)))
        except ValueError:
            return None

    match_dmy = re.match(r'^(\d{2})/(\d{2})/(\d{4})$', value)
    if match_dmy:
        try:
            return datetime(int(match_dmy.group(3)), int(match_dmy.group(2)), int(match_dmy.group(1)))
        except ValueError:
            return None

    parts = [p for p in re.split(r'\s+', value) if p]
    if len(parts) >= 3:
        month_str = parts[0].lower()[:3]
        if month_str in month_map:
            try:
                day = int(parts[1])
                year = int(parts[2][:4])
                return datetime(year, month_map[month_str], day)
            except (ValueError, IndexError):
                return None

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
    dia = date_obj.day
    dia_semana = date_obj.strftime('%A')
    trimestre = (mes - 1) // 3 + 1

    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR IGNORE INTO DIM_TEMPO (id_tempo, data, ano, mes, mes_nome, dia, dia_semana, trimestre) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (date_id, date_str, ano, mes, date_obj.strftime('%B'), dia, dia_semana, trimestre)
    )
    conn.commit()
    time_cache[date_id] = date_id
    return date_id


def init_caches(conn):
    caches = {
        'paciente': {},
        'localizacao': {},
        'clinica': {},
        'teste': {},
        'situacao': {},
        'tempo': {-1: -1}
    }
    cursor = conn.cursor()
    cursor.execute('SELECT id_tempo FROM DIM_TEMPO')
    caches['tempo'].update({row[0]: row[0] for row in cursor.fetchall()})

    cursor.execute('SELECT id_paciente, sexo, faixa_etaria, raca_cor, escolaridade, gestante, profissional_saude, possui_deficiencia, morador_de_rua FROM DIM_PACIENTE')
    for row in cursor.fetchall():
        key = tuple(row[1:])
        caches['paciente'][key] = row[0]

    cursor.execute('SELECT id_localizacao, municipio, bairro, regiao FROM DIM_LOCALIZACAO WHERE is_current = 1')
    for row in cursor.fetchall():
        key = (row[1], row[2])
        caches['localizacao'][key] = (row[0], row[3])

    cursor.execute('SELECT id_clinica, febre, dificuldade_respiratoria, tosse, coriza, dor_garganta, diarreia, cefaleia, comorbidade_pulmao, comorbidade_cardio, comorbidade_renal, comorbidade_diabetes, comorbidade_tabagismo, comorbidade_obesidade, ficou_internado FROM DIM_CLINICA')
    for row in cursor.fetchall():
        key = tuple(row[1:])
        caches['clinica'][key] = row[0]

    cursor.execute('SELECT id_teste, resultado_rt_pcr, resultado_teste_rapido, resultado_sorologia, resultado_sorologia_igg, tipo_teste_rapido FROM DIM_TESTE')
    for row in cursor.fetchall():
        key = tuple(row[1:])
        caches['teste'][key] = row[0]

    cursor.execute('SELECT id_situacao, classificacao, evolucao, criterio_confirmacao, status_notificacao FROM DIM_SITUACAO')
    for row in cursor.fetchall():
        key = tuple(row[1:])
        caches['situacao'][key] = row[0]

    return caches


def create_schema(conn):
    logger.info('Criando esquema do Data Warehouse...')
    cursor = conn.cursor()
    cursor.execute('PRAGMA foreign_keys = ON;')

    cursor.execute('DROP TABLE IF EXISTS FATO_NOTIFICACOES;')
    cursor.execute('DROP TABLE IF EXISTS DIM_TEMPO;')
    cursor.execute('DROP TABLE IF EXISTS DIM_PACIENTE;')
    cursor.execute('DROP TABLE IF EXISTS DIM_LOCALIZACAO;')
    cursor.execute('DROP TABLE IF EXISTS DIM_CLINICA;')
    cursor.execute('DROP TABLE IF EXISTS DIM_TESTE;')
    cursor.execute('DROP TABLE IF EXISTS DIM_SITUACAO;')

    cursor.execute('''
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
    ''')
    cursor.execute("INSERT INTO DIM_TEMPO (id_tempo, data, ano, mes, mes_nome, dia, dia_semana, trimestre) VALUES (-1, 'Não Informado', 0, 0, 'Não Informado', 0, 'Não Informado', 0)")

    logger.info('Pré-populando DIM_TEMPO de 2020 a 2026...')
    start_date = date(2020, 1, 1)
    end_date = date(2026, 12, 31)
    time_records = []
    meses_pt = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho',
        7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }
    dias_pt = {
        0: 'Segunda-feira', 1: 'Terça-feira', 2: 'Quarta-feira', 3: 'Quinta-feira',
        4: 'Sexta-feira', 5: 'Sábado', 6: 'Domingo'
    }
    cursor.executemany(
        'INSERT INTO DIM_TEMPO (id_tempo, data, ano, mes, mes_nome, dia, dia_semana, trimestre) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        [
            (int(dt.strftime('%Y%m%d')), dt.strftime('%Y-%m-%d'), dt.year, dt.month, meses_pt[dt.month], dt.day, dias_pt[dt.weekday()], (dt.month - 1) // 3 + 1)
            for dt in (start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1))
        ]
    )

    cursor.execute('''
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
    ''')

    cursor.execute('''
        CREATE TABLE DIM_LOCALIZACAO (
            id_localizacao INTEGER PRIMARY KEY AUTOINCREMENT,
            municipio TEXT,
            bairro TEXT,
            regiao TEXT,
            data_inicio TEXT NOT NULL,
            data_fim TEXT,
            is_current INTEGER NOT NULL DEFAULT 1
        );
    ''')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_localizacao_current ON DIM_LOCALIZACAO (municipio, bairro, is_current)')

    cursor.execute('''
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
            UNIQUE(febre, dificuldade_respiratoria, tosse, coriza, dor_garganta, diarreia, cefaleia, comorbidade_pulmao, comorbidade_cardio, comorbidade_renal, comorbidade_diabetes, comorbidade_tabagismo, comorbidade_obesidade, ficou_internado)
        );
    ''')

    cursor.execute('''
        CREATE TABLE DIM_TESTE (
            id_teste INTEGER PRIMARY KEY AUTOINCREMENT,
            resultado_rt_pcr TEXT,
            resultado_teste_rapido TEXT,
            resultado_sorologia TEXT,
            resultado_sorologia_igg TEXT,
            tipo_teste_rapido TEXT,
            UNIQUE(resultado_rt_pcr, resultado_teste_rapido, resultado_sorologia, resultado_sorologia_igg, tipo_teste_rapido)
        );
    ''')

    cursor.execute('''
        CREATE TABLE DIM_SITUACAO (
            id_situacao INTEGER PRIMARY KEY AUTOINCREMENT,
            classificacao TEXT,
            evolucao TEXT,
            criterio_confirmacao TEXT,
            status_notificacao TEXT,
            UNIQUE(classificacao, evolucao, criterio_confirmacao, status_notificacao)
        );
    ''')

    cursor.execute('''
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
    ''')

    conn.commit()
    logger.info('Esquema criado com sucesso.')


def get_or_create_localizacao_id(conn, cursor, municipio, bairro, data_inicio, caches):
    key = (municipio, bairro)
    if key in caches['localizacao']:
        return caches['localizacao'][key][0]

    cursor.execute(
        'SELECT id_localizacao, regiao FROM DIM_LOCALIZACAO WHERE municipio = ? AND bairro = ? AND is_current = 1',
        key
    )
    row = cursor.fetchone()
    regiao = infer_regiao(municipio)
    if row:
        current_id, current_regiao = row
        if current_regiao != regiao:
            end_date = (datetime.strptime(data_inicio, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
            cursor.execute(
                'UPDATE DIM_LOCALIZACAO SET data_fim = ?, is_current = 0 WHERE id_localizacao = ?',
                (end_date, current_id)
            )
            cursor.execute(
                'INSERT INTO DIM_LOCALIZACAO (municipio, bairro, regiao, data_inicio, is_current) VALUES (?, ?, ?, ?, 1)',
                (municipio, bairro, regiao, data_inicio)
            )
            new_id = cursor.lastrowid
            caches['localizacao'][key] = (new_id, regiao)
            return new_id
        caches['localizacao'][key] = (current_id, current_regiao)
        return current_id

    cursor.execute(
        'INSERT INTO DIM_LOCALIZACAO (municipio, bairro, regiao, data_inicio, is_current) VALUES (?, ?, ?, ?, 1)',
        (municipio, bairro, regiao, data_inicio)
    )
    new_id = cursor.lastrowid
    caches['localizacao'][key] = (new_id, regiao)
    return new_id


def run_etl(conn, csv_path):
    logger.info('Iniciando o processo de ETL...')
    cursor = conn.cursor()
    caches = init_caches(conn)

    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f'Arquivo CSV não encontrado: {csv_path}')

    delimiters = [';', ',', '\t']
    encodings = ['utf-8', 'latin1', 'iso-8859-1']
    detected_delimiter = ';'
    detected_encoding = 'latin1'

    for enc in encodings:
        for delim in delimiters:
            try:
                with open(csv_path, 'r', encoding=enc) as f:
                    first_line = f.readline()
                    if delim in first_line:
                        detected_delimiter = delim
                        detected_encoding = enc
                        raise StopIteration
            except StopIteration:
                break
            except Exception:
                continue
        else:
            continue
        break

    logger.info(f'Lendo CSV com delimitador="{detected_delimiter}" e encoding="{detected_encoding}"')

    start_time = time.time()
    total_rows = 0
    batch_size = 5000
    facts_to_insert = []
    errors = 0

    with open(csv_path, 'r', encoding=detected_encoding, errors='replace') as f:
        reader = csv.reader(f, delimiter=detected_delimiter)
        headers = next(reader)
        col_idx = {col: idx for idx, col in enumerate(headers)}
        conn.execute('BEGIN TRANSACTION;')

        for row in reader:
            if not row:
                continue

            total_rows += 1
            if ROW_LIMIT and total_rows > ROW_LIMIT:
                break

            def get_val(col_name, default=''):
                idx = col_idx.get(col_name)
                if idx is not None and idx < len(row):
                    return row[idx].strip()
                return default

            try:
                dt_notif = parse_date(get_val('DataNotificacao'))
                dt_diag = parse_date(get_val('DataDiagnostico'))
                dt_enc = parse_date(get_val('DataEncerramento'))

                id_t_notif = get_or_create_time_id(conn, dt_notif, caches['tempo'])
                id_t_diag = get_or_create_time_id(conn, dt_diag, caches['tempo'])
                id_t_enc = get_or_create_time_id(conn, dt_enc, caches['tempo'])

                paciente_key = (
                    normalize_text(get_val('Sexo', 'I')),
                    normalize_text(get_val('FaixaEtaria', 'Ignorado')),
                    normalize_text(get_val('RacaCor', 'Ignorado')),
                    normalize_text(get_val('Escolaridade', 'Ignorado')),
                    normalize_text(get_val('Gestante', 'Não se aplica')),
                    normalize_yes_no(get_val('ProfissionalSaude', 'Não')),
                    normalize_yes_no(get_val('PossuiDeficiencia', 'Não')),
                    normalize_yes_no(get_val('MoradorDeRua', 'Não'))
                )
                if paciente_key not in caches['paciente']:
                    cursor.execute(
                        'INSERT OR IGNORE INTO DIM_PACIENTE (sexo, faixa_etaria, raca_cor, escolaridade, gestante, profissional_saude, possui_deficiencia, morador_de_rua) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        paciente_key
                    )
                    if cursor.lastrowid:
                        caches['paciente'][paciente_key] = cursor.lastrowid
                    else:
                        cursor.execute('SELECT id_paciente FROM DIM_PACIENTE WHERE sexo=? AND faixa_etaria=? AND raca_cor=? AND escolaridade=? AND gestante=? AND profissional_saude=? AND possui_deficiencia=? AND morador_de_rua=?', paciente_key)
                        caches['paciente'][paciente_key] = cursor.fetchone()[0]
                id_paciente = caches['paciente'][paciente_key]

                municipio = normalize_text(get_val('Municipio'))
                bairro = normalize_text(get_val('Bairro'))
                data_inicio = dt_notif.strftime('%Y-%m-%d') if dt_notif else '1900-01-01'
                id_localizacao = get_or_create_localizacao_id(conn, cursor, municipio, bairro, data_inicio, caches)

                clinica_key = (
                    normalize_yes_no(get_val('Febre', 'Não')),
                    normalize_yes_no(get_val('DificuldadeRespiratoria', 'Não')),
                    normalize_yes_no(get_val('Tosse', 'Não')),
                    normalize_yes_no(get_val('Coriza', 'Não')),
                    normalize_yes_no(get_val('DorGarganta', 'Não')),
                    normalize_yes_no(get_val('Diarreia', 'Não')),
                    normalize_yes_no(get_val('Cefaleia', 'Não')),
                    normalize_yes_no(get_val('ComorbidadePulmao', 'Não')),
                    normalize_yes_no(get_val('ComorbidadeCardio', 'Não')),
                    normalize_yes_no(get_val('ComorbidadeRenal', 'Não')),
                    normalize_yes_no(get_val('ComorbidadeDiabetes', 'Não')),
                    normalize_yes_no(get_val('ComorbidadeTabagismo', 'Não')),
                    normalize_yes_no(get_val('ComorbidadeObesidade', 'Não')),
                    normalize_yes_no(get_val('FicouInternado', 'Não'))
                )
                if clinica_key not in caches['clinica']:
                    cursor.execute(
                        'INSERT OR IGNORE INTO DIM_CLINICA (febre, dificuldade_respiratoria, tosse, coriza, dor_garganta, diarreia, cefaleia, comorbidade_pulmao, comorbidade_cardio, comorbidade_renal, comorbidade_diabetes, comorbidade_tabagismo, comorbidade_obesidade, ficou_internado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                        clinica_key
                    )
                    if cursor.lastrowid:
                        caches['clinica'][clinica_key] = cursor.lastrowid
                    else:
                        cursor.execute('SELECT id_clinica FROM DIM_CLINICA WHERE febre=? AND dificuldade_respiratoria=? AND tosse=? AND coriza=? AND dor_garganta=? AND diarreia=? AND cefaleia=? AND comorbidade_pulmao=? AND comorbidade_cardio=? AND comorbidade_renal=? AND comorbidade_diabetes=? AND comorbidade_tabagismo=? AND comorbidade_obesidade=? AND ficou_internado=?', clinica_key)
                        caches['clinica'][clinica_key] = cursor.fetchone()[0]
                id_clinica = caches['clinica'][clinica_key]

                teste_key = (
                    normalize_text(get_val('ResultadoRT_PCR', 'Não Informado')),
                    normalize_text(get_val('ResultadoTesteRapido', 'Não Informado')),
                    normalize_text(get_val('ResultadoSorologia', 'Não Informado')),
                    normalize_text(get_val('ResultadoSorologia_IGG', 'Não Informado')),
                    normalize_text(get_val('TipoTesteRapido', 'Não Informado'))
                )
                if teste_key not in caches['teste']:
                    cursor.execute(
                        'INSERT OR IGNORE INTO DIM_TESTE (resultado_rt_pcr, resultado_teste_rapido, resultado_sorologia, resultado_sorologia_igg, tipo_teste_rapido) VALUES (?, ?, ?, ?, ?)',
                        teste_key
                    )
                    if cursor.lastrowid:
                        caches['teste'][teste_key] = cursor.lastrowid
                    else:
                        cursor.execute('SELECT id_teste FROM DIM_TESTE WHERE resultado_rt_pcr=? AND resultado_teste_rapido=? AND resultado_sorologia=? AND resultado_sorologia_igg=? AND tipo_teste_rapido=?', teste_key)
                        caches['teste'][teste_key] = cursor.fetchone()[0]
                id_teste = caches['teste'][teste_key]

                situacao_key = (
                    normalize_text(get_val('Classificacao', 'Suspeito')),
                    normalize_text(get_val('Evolucao', '-')),
                    normalize_text(get_val('CriterioConfirmacao', '-')),
                    normalize_text(get_val('StatusNotificacao', 'Em Aberto'))
                )
                if situacao_key not in caches['situacao']:
                    cursor.execute(
                        'INSERT OR IGNORE INTO DIM_SITUACAO (classificacao, evolucao, criterio_confirmacao, status_notificacao) VALUES (?, ?, ?, ?)',
                        situacao_key
                    )
                    if cursor.lastrowid:
                        caches['situacao'][situacao_key] = cursor.lastrowid
                    else:
                        cursor.execute('SELECT id_situacao FROM DIM_SITUACAO WHERE classificacao=? AND evolucao=? AND criterio_confirmacao=? AND status_notificacao=?', situacao_key)
                        caches['situacao'][situacao_key] = cursor.fetchone()[0]
                id_situacao = caches['situacao'][situacao_key]

                evolucao = normalize_text(get_val('Evolucao', '-')).lower()
                data_obito = normalize_text(get_val('DataObito', ''))
                obito = 1 if 'obito' in evolucao or 'óbito' in evolucao or data_obito != 'Não Informado' else 0
                confirmado = 1 if normalize_text(get_val('Classificacao'), 'Suspeito') == 'Confirmados' else 0
                internado = 1 if normalize_yes_no(get_val('FicouInternado', 'Não')) == 'Sim' else 0

                facts_to_insert.append((
                    id_t_notif, id_t_diag, id_t_enc,
                    id_paciente, id_localizacao, id_clinica, id_teste, id_situacao,
                    1, obito, confirmado, internado
                ))

                if len(facts_to_insert) >= batch_size:
                    cursor.executemany(
                        'INSERT INTO FATO_NOTIFICACOES (id_tempo_notificacao, id_tempo_diagnostico, id_tempo_encerramento, id_paciente, id_localizacao, id_clinica, id_teste, id_situacao, quantidade_casos, obito, confirmado, internado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                        facts_to_insert
                    )
                    conn.commit()
                    conn.execute('BEGIN TRANSACTION;')
                    facts_to_insert = []
                    logger.info('Processadas %d linhas...', total_rows)

            except Exception as exc:
                errors += 1
                logger.exception('Erro na linha %d: %s', total_rows, exc)

        if facts_to_insert:
            cursor.executemany(
                'INSERT INTO FATO_NOTIFICACOES (id_tempo_notificacao, id_tempo_diagnostico, id_tempo_encerramento, id_paciente, id_localizacao, id_clinica, id_teste, id_situacao, quantidade_casos, obito, confirmado, internado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                facts_to_insert
            )
        conn.commit()

    elapsed = time.time() - start_time
    logger.info('ETL concluído: %d linhas processadas em %.2f segundos.', total_rows, elapsed)
    logger.info('Erros registrados: %d', errors)
    logger.info('Taxa de processamento: %.1f linhas/segundo.', total_rows / elapsed if elapsed else 0)


def analyze_db(conn):
    logger.info('Analisando contagens finais do DW...')
    cursor = conn.cursor()
    tables = ['DIM_TEMPO', 'DIM_PACIENTE', 'DIM_LOCALIZACAO', 'DIM_CLINICA', 'DIM_TESTE', 'DIM_SITUACAO', 'FATO_NOTIFICACOES']
    for table in tables:
        cursor.execute(f'SELECT COUNT(*) FROM {table}')
        logger.info('Tabela %s: %d registros', table, cursor.fetchone()[0])

    cursor.execute('''
        SELECT l.municipio, l.bairro, COUNT(*) AS total
        FROM FATO_NOTIFICACOES f
        JOIN DIM_LOCALIZACAO l ON f.id_localizacao = l.id_localizacao
        WHERE l.is_current = 1
        GROUP BY l.municipio, l.bairro
        ORDER BY total DESC
        LIMIT 10
    ''')
    rows = cursor.fetchall()
    if rows:
        logger.info('Top 10 localidades por notificações:')
        for municipio, bairro, total in rows:
            logger.info('  %s / %s: %d', municipio, bairro, total)


def try_connect(db_path):
    return sqlite3.connect(db_path, timeout=30, check_same_thread=False)


def resolve_db_path():
    if os.path.exists(DB_NAME):
        logger.warning('Arquivo %s já existe; criando base fresca de DW.', DB_NAME)
        if os.path.exists(ALT_DB_NAME):
            try:
                os.remove(ALT_DB_NAME)
            except PermissionError:
                suffix = int(time.time())
                alt_path = f'covid_dw_fresh_{suffix}.db'
                logger.warning('Não foi possível remover %s; usando %s', ALT_DB_NAME, alt_path)
                return alt_path
        return ALT_DB_NAME
    return DB_NAME


def main():
    global logger
    logger = setup_logger()
    logger.info('Início do pipeline de Data Warehouse')

    db_path = resolve_db_path()
    conn = None

    try:
        conn = try_connect(db_path)

        with conn:
            conn.execute('PRAGMA busy_timeout = 30000;')
            conn.execute('PRAGMA journal_mode = OFF;')
            conn.execute('PRAGMA synchronous = OFF;')
            conn.execute('PRAGMA temp_store = MEMORY;')
            conn.execute('PRAGMA cache_size = -500000;')

            create_schema(conn)
            run_etl(conn, CSV_NAME)
            analyze_db(conn)

        logger.info('Pipeline finalizado. Base usada: %s', db_path)
    except sqlite3.OperationalError as exc:
        if 'database is locked' in str(exc).lower() and db_path == DB_NAME:
            logger.warning('Arquivo %s travado durante operação. Tentando fallback em %s', db_path, ALT_DB_NAME)
            if conn:
                conn.close()
            db_path = ALT_DB_NAME
            with try_connect(db_path) as conn:
                conn.execute('PRAGMA busy_timeout = 30000;')
                conn.execute('PRAGMA journal_mode = OFF;')
                conn.execute('PRAGMA synchronous = OFF;')
                conn.execute('PRAGMA temp_store = MEMORY;')
                conn.execute('PRAGMA cache_size = -500000;')

                create_schema(conn)
                run_etl(conn, CSV_NAME)
                analyze_db(conn)

            logger.info('Pipeline finalizado em base alternativa: %s', db_path)
        else:
            raise


if __name__ == '__main__':
    main()
