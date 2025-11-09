from init import init_logging
import logging
import func
import db as database
import json
import psycopg2
from psycopg2 import sql
import time
from init import envs
from datetime import datetime

init_logging()

offset_my = 1000
weeks = 8
#
def fetch_events(db, school_id, offset=0, limit=offset_my):
    start_date_str, end_date_str = func.generates_dates(weeks)
    # logging.info(f"{start_date_str} {end_date_str}")
    endpoint = f'events?from={start_date_str}&to={end_date_str}&limit={limit}&offset={offset}'
    config = func.GraphqlConfig(
        base_url=envs['base_url'],
        api_version=envs['api_version'],
        db_manager=db,
        # token=db.fetch_auth_data(),
        test=envs['test']
    )
    graphql_client = func.Graphql(config)
    status_code, data = graphql_client.graphql_with_retry(endpoint)
    return data.get('events', [])

def make_records(objects, school_id):
    records = []
    for obj in objects:
        try:
            record = [
                school_id,
                obj['id'],
                obj['type'],
                obj['name'],
                obj.get('description', ''),  # Используем пустую строку, если описания нет
                obj['location'],
                obj['startDateTime'],
                obj['endDateTime'],
                json.dumps(obj.get('organizers', [])),  # Преобразование списка организаторов в JSON строку, используем пустой список, если организаторов нет
                obj['capacity'],
                obj['registerCount']
            ]
            records.append(record)
        except KeyError as e:
            logging.error(f"Ошибка: отсутствует ключ {e} в объекте {obj}")
        except Exception as e:
            logging.error(f"Произошла непредвиденная ошибка: {e}")
    return records

def normalize_record(record):
    """ Преобразование кортежа в список и приведение типов данных к общему формату для сравнения """
    normalized = list(record)
    if isinstance(normalized[8], str):
        try:
            normalized[8] = json.loads(normalized[8])
        except json.JSONDecodeError:
            pass  # если не удалось декодировать строку, оставляем как есть
    if normalized[8] == '[]':
        normalized[8] = []
    return normalized

def records_equal(record1, record2):
    """ Сравнение двух записей после нормализации """
    # logging.info(f"\n{normalize_record(record1)}\n{normalize_record(record2)}\n")
    return normalize_record(record1) == normalize_record(record2)

# Функция для обрезки времени до секунд и преобразования в datetime
def truncate_to_seconds(time_str):
    # logging.info(time_str)
    # Обрезаем строку до секунд
    truncated_str = time_str.split('.')[0]
    try:
        truncated_str = truncated_str.split('Z')[0]
    except:
        pass
    # Преобразуем обрезанную строку в datetime
    return datetime.strptime(truncated_str, '%Y-%m-%dT%H:%M:%S')


def db_operations(db, school_id, objects):
    records = make_records(objects, school_id)
    # logging.info(f"Сохранение записей: {records}")
    try:
        for record in records:
            try:
                db_record_tuple = db.execute_query_with_retry(get_one_event, (record[1],))[0]  # Предполагается, что id находится на первом месте
                db_record = normalize_record(db_record_tuple)
            except:
                db_record = 0
            # logging.info(record[6])
            # logging.info(record[7])
            # Применяем функцию к строкам времени
            record[6] = truncate_to_seconds(record[6])
            record[7] = truncate_to_seconds(record[7])
            # # Преобразование строк времени из record в объекты datetime
            # record[6] = datetime.strptime(record[6], '%Y-%m-%dT%H:%M:%S')
            # record[7] = datetime.strptime(record[7], '%Y-%m-%dT%H:%M:%S')
            # logging.info(record[6])
            # logging.info(record[7])
            db.upsert_data(upsert_query, [record])  # Передаем каждый record отдельно
            if db_record and not records_equal(db_record, record):
                db.execute_query_with_retry(set_flag_update, (record[1],))  # Передаем record, требующий обновления

    except Exception as e:
        logging.error(f"Ошибка при выполнении upsert: {e}")
        raise

def get_events():
    db = database.base.create_new_instance()
    db.create_table(create_table_query)
    # logging.info("Создал таблицу")
    school_ids = db.get_ids(school_ids_query)
    school_ids = ('6bfe3c56-0211-4fe1-9e59-51616caac4dd',)  # пока недоступна выборка по кампусу

    if not school_ids:
        logging.error("Не удалось получить идентификаторы школ.")
        return

    for school_id in school_ids:
        events = fetch_events(db, school_id)
        if not events:
            continue

        try:
            db_operations(db, school_id, events)
            events_ids = tuple(event['id'] for event in  events)
            db.delete_missing_records(delete_query, (events_ids, school_id,))
        except KeyError as e:
            logging.error(f"Ошибка при распаковке данных коалиции: {e}")
            continue
        except TypeError as e:
            logging.error(f"Ошибка типа данных при распаковке коалиций: {e}")
            continue

    logging.info("Все events успешно записаны в базу данных.")

school_ids_query = "SELECT id FROM parser.campuses"
set_flag_update = "UPDATE parser.events SET update = TRUE, update_rocket = TRUE WHERE id = %s"
get_one_event = '''
SELECT
    school_id,
    id,
    type,
    name,
    description,
    location,
    start_datetime,
    end_datetime,
    organizers,
    capacity,
    register_count
FROM parser.events
WHERE id = %s
'''

create_table_query = '''
CREATE TABLE IF NOT EXISTS parser.events (
    school_id UUID NOT NULL,
    id INT NOT NULL,
    type TEXT,
    name TEXT,
    description TEXT,
    location TEXT,
    start_datetime TIMESTAMP,
    end_datetime TIMESTAMP,
    organizers JSONB DEFAULT NULL,
    capacity INT,
    register_count INT,
    last_updated TIMESTAMP DEFAULT NOW(),
    message_id int,
    sended BOOL DEFAULT FALSE,
    update BOOL DEFAULT FALSE,
    rocket_chat_message_id TEXT,
    sended_rocket BOOL DEFAULT FALSE,
    update_rocket BOOL DEFAULT FALSE,
    PRIMARY KEY (school_id, id),
    CONSTRAINT fk_school
        FOREIGN KEY (school_id)
        REFERENCES parser.campuses(id)
        ON DELETE CASCADE
)
'''

upsert_query = '''
INSERT INTO parser.events (school_id, id, type, name, description, location, start_datetime, end_datetime, organizers, capacity, register_count, last_updated)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
ON CONFLICT (school_id, id) DO UPDATE SET
    type = EXCLUDED.type,
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    location = EXCLUDED.location,
    start_datetime = EXCLUDED.start_datetime,
    end_datetime = EXCLUDED.end_datetime,
    organizers = EXCLUDED.organizers,
    capacity = EXCLUDED.capacity,
    register_count = EXCLUDED.register_count,
    last_updated = NOW()
'''

delete_query = sql.SQL('''
DELETE FROM parser.events
WHERE id NOT IN %s
AND school_id = %s
''')
