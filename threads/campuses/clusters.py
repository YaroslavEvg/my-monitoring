
from init import init_logging
import logging
import func
import db as database
from init import envs
from psycopg2 import sql

init_logging()


def fetch_clusters(db, school_id):
    endpoint = f'campuses/{school_id}/clusters'
    config = func.GraphqlConfig(
        base_url=envs['base_url'],
        api_version=envs['api_version'],
        db_manager=db,
        # token=db.fetch_auth_data(),
        test=envs['test']
    )
    graphql_client = func.Graphql(config)
    status_code, data = graphql_client.graphql_with_retry(endpoint)
    return data.get('clusters', [])

def db_operations(db, school_id, objects):
    records = [(object['id'], object['name'], object['capacity'],
                object['availableCapacity'], object['floor'],
                school_id) for object in objects]
    logging.info(f"Сохранение записей: {records}")
    db.upsert_data(upsert_query, records)
    json_ids = tuple(object['id'] for object in objects)
    db.delete_missing_records(delete_query, (json_ids, school_id,))

def get_clusters():
    db = database.base.create_new_instance()
    db.create_table(create_table_query)

    school_ids = db.get_ids(school_ids_query)

    if not school_ids:
        logging.error("Не удалось получить идентификаторы школ.")
        return

    for school_id in school_ids:
        clusters = fetch_clusters(db, school_id)
        if not clusters:
            continue

        try:
            db_operations(db, school_id, clusters)
        except KeyError as e:
            logging.error(f"Ошибка при распаковке данных коалиции: {e}")
            continue
        except TypeError as e:
            logging.error(f"Ошибка типа данных при распаковке коалиций: {e}")
            continue

    logging.error("Все clusters успешно записаны в базу данных.")

school_ids_query = "SELECT id FROM parser.campuses"

create_table_query = '''
CREATE TABLE IF NOT EXISTS parser.clusters (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    capacity INT NOT NULL,
    availableCapacity INT NOT NULL,
    floor INT NOT NULL,
    school_id UUID NOT NULL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_cluster_school UNIQUE (id, school_id),
    CONSTRAINT fk_school
        FOREIGN KEY (school_id)
        REFERENCES parser.campuses(id)
        ON DELETE CASCADE
)
'''

upsert_query = '''
INSERT INTO parser.clusters (id, name, capacity, availableCapacity, floor,  schoolId, last_updated)
VALUES (%s, %s, %s, %s, %s, %s, NOW())
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    capacity = EXCLUDED.capacity,
    availableCapacity  = EXCLUDED.availableCapacity,
    floor  = EXCLUDED.floor,
    schoolId = EXCLUDED.schoolId,
    last_updated = NOW()
'''

delete_query = sql.SQL('''
DELETE FROM parser.clusters
WHERE id NOT IN %s
AND schoolId = %s
''')
