
from init import init_logging
import logging
import func
import db as database
from init import envs
from psycopg2 import sql

init_logging()

offset_my = 1000


def fetch_coalitions(db, coalitions_id, offset=0, limit=offset_my):
    endpoint = f'coalitions/{coalitions_id}/participants?limit={limit}&offset={offset}'
    config = func.GraphqlConfig(
        base_url=envs['base_url'],
        api_version=envs['api_version'],
        db_manager=db,
        # token=db.fetch_auth_data(),
        test=envs['test']
    )
    graphql_client = func.Graphql(config)
    status_code, data = graphql_client.graphql_with_retry(endpoint)
    return data.get('participants', [])

def db_operations(db, coalition_id, objects):
    records = [(object, coalition_id) for object in objects]
    db.upsert_data(upsert_query, records)
    coalition_ids = tuple(object for object in objects)
    db.delete_missing_records(delete_query, (coalition_ids, coalition_id,))

def get_coalitions_participants():
    db = database.base.create_new_instance()
    db.create_table(create_table_query)

    coalition_ids = db.get_ids(coalition_ids_query)

    if not coalition_ids:
        logging.error("Не удалось получить идентификаторы coliation.")
        return

    for coalition_id in coalition_ids:
        offset = 0
        while True:
            coalitions = fetch_coalitions(db, coalition_id, offset)
            if not coalitions:
                break

            try:
                db_operations(db, coalition_id, coalitions)
            except KeyError as e:
                logging.error(f"Ошибка при распаковке данных коалиции: {e}")
                break
            except TypeError as e:
                logging.error(f"Ошибка типа данных при распаковке коалиций: {e}")
                break

            offset += offset_my  # или используйте ваше значение offset_my

    logging.error("Все coalitions успешно записаны в базу данных.")

coalition_ids_query = "SELECT coalitionId FROM parser.coalitions"

create_table_query = '''
CREATE TABLE IF NOT EXISTS parser.coalitions_participants (
    id TEXT PRIMARY KEY,
    coalitionId INT NOT NULL,
    last_updated TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_participant
        FOREIGN KEY (id)
        REFERENCES parser.participants(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_coalition
        FOREIGN KEY (coalitionId)
        REFERENCES parser.coalitions(coalitionId)
        ON DELETE CASCADE
)
'''

upsert_query = '''
INSERT INTO parser.coalitions_participants (id, coalitionId, last_updated)
VALUES (%s, %s, NOW())
ON CONFLICT (id) DO UPDATE SET
    coalitionId = EXCLUDED.coalitionId,
    last_updated = NOW()
'''

delete_query = sql.SQL('''
DELETE FROM parser.coalitions_participants
WHERE id NOT IN %s
AND coalitionId = %s
''')
