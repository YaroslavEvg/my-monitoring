
from init import init_logging
import logging
import func
import db as database
from init import envs
from psycopg2 import sql

init_logging()

offset_my = 1000


def fetch_coalitions(db, school_id, offset=0, limit=offset_my):
    endpoint = f'campuses/{school_id}/coalitions?limit={limit}&offset={offset}'
    config = func.GraphqlConfig(
        base_url=envs['base_url'],
        api_version=envs['api_version'],
        db_manager=db,
        # token=db.fetch_auth_data(),
        test=envs['test']
    )
    graphql_client = func.Graphql(config)
    status_code, data = graphql_client.graphql_with_retry(endpoint)
    return data.get('coalitions', [])

def db_operations(db, school_id, objects):
    records = [(object['coalitionId'], object['name'], school_id) for object in objects]
    logging.info(f"Сохранение записей: {records}")
    db.upsert_data(upsert_query, records)
    coalition_ids = tuple(object['coalitionId'] for object in objects)
    db.delete_missing_records(delete_query, (coalition_ids, school_id,))

def get_coalitions():
    db = database.base.create_new_instance()
    db.create_table(create_table_query)

    school_ids = db.get_ids(school_ids_query)

    if not school_ids:
        logging.error("Не удалось получить идентификаторы школ.")
        return

    for school_id in school_ids:
        offset = 0
        while True:
            coalitions = fetch_coalitions(db, school_id, offset)
            if not coalitions:
                break

            try:
                db_operations(db, school_id, coalitions)
            except KeyError as e:
                logging.error(f"Ошибка при распаковке данных коалиции: {e}")
                break
            except TypeError as e:
                logging.error(f"Ошибка типа данных при распаковке коалиций: {e}")
                break

            offset += offset_my

    logging.error("Все coalitions успешно записаны в базу данных.")

school_ids_query = "SELECT id FROM parser.campuses"

create_table_query = '''
CREATE TABLE IF NOT EXISTS parser.coalitions (
    coalitionId INT PRIMARY KEY,
    name TEXT NOT NULL,
    schoolId UUID NOT NULL,
    last_updated TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_school
        FOREIGN KEY (schoolId)
        REFERENCES parser.campuses(id)
        ON DELETE CASCADE
)
'''

upsert_query = '''
INSERT INTO parser.coalitions (coalitionId, name, schoolId, last_updated)
VALUES (%s, %s, %s, NOW())
ON CONFLICT (coalitionId) DO UPDATE SET
    name = EXCLUDED.name,
    schoolId = EXCLUDED.schoolId,
    last_updated = NOW()
'''

delete_query = sql.SQL('''
DELETE FROM parser.coalitions
WHERE coalitionId NOT IN %s
AND schoolId = %s
''')

# ALTER TABLE parser.coalitions_participants
# DROP CONSTRAINT fk_coalition,
# ADD CONSTRAINT fk_coalition
# FOREIGN KEY (coalitionid)
# REFERENCES parser.coalitions(coalitionId)
# ON DELETE CASCADE;
