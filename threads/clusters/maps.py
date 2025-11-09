
from init import init_logging
import logging
import func
import db as database
from init import envs
from psycopg2 import sql

init_logging()

offset_my = 1000

def fetch_maps(db, cluster_id, offset=0, limit=offset_my):
    endpoint = f'clusters/{cluster_id}/map'
    config = func.GraphqlConfig(
        base_url=envs['base_url'],
        api_version=envs['api_version'],
        db_manager=db,
        # token=db.fetch_auth_data(),
        test=envs['test']
    )
    graphql_client = func.Graphql(config)
    status_code, data = graphql_client.graphql_with_retry(endpoint)
    return data.get('clusterMap', [])

def db_operations(db, cluster_id, objects):
    records = [(cluster_id, object['row'], object['number'], object['login']) for object in objects]
    logging.info(f"Сохранение записей: {records}")
    db.upsert_data(upsert_query, records)
    json_rows = tuple(object['row'] for object in objects)
    json_numbers = tuple(object['number'] for object in objects)
    db.delete_missing_records(delete_query, (json_rows, json_numbers, cluster_id,))

def get_maps():
    db = database.base.create_new_instance()
    db.create_table(create_table_query)

    cluster_ids = db.get_ids(cluster_ids_query)

    if not cluster_ids:
        logging.error("Не удалось получить идентификаторы школ.")
        return

    for cluster_id in cluster_ids:
        maps = fetch_maps(db, cluster_id)
        if not maps:
            continue

        try:
            db_operations(db, cluster_id, maps)
        except KeyError as e:
            logging.error(f"Ошибка при распаковке данных коалиции: {e}")
            continue
        except TypeError as e:
            logging.error(f"Ошибка типа данных при распаковке коалиций: {e}")
            continue

    logging.error("Все maps успешно записаны в базу данных.")


cluster_ids_query = "SELECT id FROM parser.clusters"

create_table_query = '''
CREATE TABLE IF NOT EXISTS parser.clusterMaps (
    id INT PRIMARY KEY,
    row TEXT NOT NULL,
    number INT NOT NULL,
    login TEXT,
    last_updated TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_cluster
        FOREIGN KEY (id)
        REFERENCES parser.clusters(id)
        ON DELETE CASCADE
)
'''

upsert_query = '''
INSERT INTO parser.clusterMaps (id, row, number, login, last_updated)
VALUES (%s, %s, %s, %s, NOW())
ON CONFLICT (id) DO UPDATE SET
    row = EXCLUDED.row,
    number = EXCLUDED.number,
    login  = EXCLUDED.login,
    last_updated = NOW()
'''

delete_query = sql.SQL('''
DELETE FROM parser.clusterMaps
WHERE row NOT IN %s
AND number NOT IN %s
AND id = %s
''')
