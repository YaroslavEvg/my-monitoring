from init import init_logging
import logging
import func
import db as database
from init import envs
from psycopg2 import sql

init_logging()

offset_my = 1000

def fetch_participants(db, school_id, offset=0, limit=offset_my):
    endpoint = f'campuses/{school_id}/participants?limit={limit}&offset={offset}'
    config = func.GraphqlConfig(
        base_url=envs['base_url'],
        api_version=envs['api_version'],
        db_manager=db,
        test=envs['test']
    )
    graphql_client = func.Graphql(config)
    status_code, data = graphql_client.graphql_with_retry(endpoint)
    return data.get('participants', [])

def get_participants():
    db = database.base.create_new_instance()
    db.create_table(create_table_query)

    school_ids = db.get_ids(school_ids_query)

    if not school_ids:
        logging.error("Не удалось получить идентификаторы школ.")
        return

    logging.info(f"Количество кампусов: {len(school_ids)}")
    for school_id in school_ids:
        offset = 0
        participants_for_records_count = 0
        participants_for_del = []

        while True:
            participants = fetch_participants(db, school_id, offset)
            if not participants:
                break

            logging.info(f"Количество логинов: {len(participants)} для кампуса: {school_id}")
            participants_for_records =[(participant, school_id) for participant in participants]
            participants_for_del.extend([participant for participant in participants])
            offset += offset_my
            participants_for_records_count += len(participants)

            if participants_for_records:
                db.bulk_upsert_data(upsert_query, participants_for_records)

        logging.info(f"Количество логинов: {participants_for_records_count} записано для кампуса: {school_id}")
        if participants_for_del:
            db.delete_missing_records(delete_query, (tuple(participants_for_del), school_id))

    logging.error("Все участники успешно записаны в базу данных.")

school_ids_query = "SELECT id FROM parser.campuses"

create_table_query = '''
CREATE TABLE IF NOT EXISTS parser.participants (
    id TEXT PRIMARY KEY,
    schoolId UUID NOT NULL,
    last_updated TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_school
        FOREIGN KEY (schoolId)
        REFERENCES parser.campuses(id)
        ON DELETE CASCADE
)
'''

upsert_query = '''
INSERT INTO parser.participants (id, schoolId, last_updated)
VALUES (%s, %s, NOW())
ON CONFLICT (id) DO UPDATE SET
    schoolId = EXCLUDED.schoolId,
    last_updated = NOW()
'''

delete_query = sql.SQL('''
DELETE FROM parser.participants
WHERE id NOT IN %s
AND schoolId = %s
''')
