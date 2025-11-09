
from init import init_logging
import logging
import func
import db as database
from init import envs
from psycopg2 import sql

init_logging()

offset_my = 1000

def fetch_sales(db, school_id, offset=0, limit=offset_my):
    endpoint = f'sales'
    config = func.GraphqlConfig(
        base_url=envs['base_url'],
        api_version=envs['api_version'],
        db_manager=db,
        # token=db.fetch_auth_data(),
        test=envs['test']
    )
    graphql_client = func.Graphql(config)
    status_code, data = graphql_client.graphql_with_retry(endpoint)
    return data.get('sales', [])

def db_operations(db, school_id, objects):
    records = [(school_id, object['type'], object['status'], object['startDateTime'], object['progressPercentage']) for object in objects]
    logging.info(f"Сохранение записей: {records}")
    db.upsert_data(upsert_query, records)

def get_sales():
    db = database.base.create_new_instance()
    db.create_table(create_table_query)

    school_ids = db.get_ids(school_ids_query)
    school_ids = ('6bfe3c56-0211-4fe1-9e59-51616caac4dd',) # пока недоступна выборка по кампусу


    if not school_ids:
        logging.error("Не удалось получить идентификаторы школ.")
        return

    for school_id in school_ids:
        sales = fetch_sales(db, school_id)
        if not sales:
            continue

        try:
            db_operations(db, school_id, sales)
        except KeyError as e:
            logging.error(f"Ошибка при распаковке данных коалиции: {e}")
            continue
        except TypeError as e:
            logging.error(f"Ошибка типа данных при распаковке коалиций: {e}")
            continue

    logging.info("Все sales успешно записаны в базу данных.")

school_ids_query = "SELECT id FROM parser.campuses"

create_table_query = '''
CREATE TABLE IF NOT EXISTS parser.sales (
    id UUID NOT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    startDateTime TIMESTAMP,
    progressPercentage INT,
    last_updated TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (id, type),
    CONSTRAINT fk_school
        FOREIGN KEY (id)
        REFERENCES parser.campuses(id)
        ON DELETE CASCADE
)
'''

upsert_query = '''
INSERT INTO parser.sales (id, type, status, startDateTime, progressPercentage, last_updated)
VALUES (%s, %s, %s, %s, %s, NOW())
ON CONFLICT (id, type) DO UPDATE SET
    status = EXCLUDED.status,
    startDateTime  = EXCLUDED.startDateTime,
    progressPercentage  = EXCLUDED.progressPercentage,
    last_updated = NOW()
'''
