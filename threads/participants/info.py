
from init import init_logging
import logging
import func
import db as database
from init import envs

init_logging()

offset_my = 1000
batch_size = 100  # Размер пакета

def fetch_participant_info(db, participant_id):
    endpoint = f'participants/{participant_id}'
    config = func.GraphqlConfig(
        base_url=envs['base_url'],
        api_version=envs['api_version'],
        db_manager=db,
        # token=db.fetch_auth_data(),
        test=envs['test']
    )
    graphql_client = func.Graphql(config)
    status_code, data = graphql_client.graphql_with_retry(endpoint)
    # logging.info(data)
    return status_code, data

def get_participants_info():
    db = database.base.create_new_instance()
    db.create_table(create_table_query)

    participants_ids = db.get_ids(participants_ids_query)

    if not  participants_ids:
        logging.error("Не удалось получить идентификаторы школ.")
        return
    logging.info(f"Всего логинов: {len(participants_ids)}")

    for i in range(0, len(participants_ids), batch_size):
        batch_ids =  participants_ids[i:i + batch_size]
        logging.info(f"Всего логинов в пачке: {len(batch_ids)}")
        records = []
        for participant_id in batch_ids:
            # logging.info(f"Получаем инфо для : {participant_id}")
            status_code, participant =  fetch_participant_info(db, participant_id)
            if status_code == 404:
                logging.info(f"404 Hе найдено в школе {participant_id}")
                # db.delete_missing_records(delete_query, (participant_id,))
                continue
            if participant is None:
                continue
            try:
                record = (
                    participant['login'],
                    participant['className'],
                    participant['parallelName'],
                    participant['expValue'],
                    participant['level'],
                    participant['expToNextLevel'],
                    participant['campus']['id'],
                    participant['campus']['shortName'],
                    participant['status']
                )
                # logging.info(record)
                records.append(record)
            except (TypeError, KeyError) as e:
                if 'SSL' not in str(participant):
                    logging.error(f"Error processing participant {participant}: {e}")
        db.upsert_data(upsert_query, records)
        logging.info(f"Пакет с {i} по {i + batch_size} участников успешно записан в базу данных.")

    logging.error("Все участники успешно записаны в базу данных.")


participants_ids_query = '''
SELECT
    parser.participants.id as login
FROM
    parser.participants
    LEFT JOIN parser.participants_info
        ON parser.participants.id = parser.participants_info.id
WHERE parser.participants.id != 'agroup'
ORDER BY
    CASE
        WHEN parser.participants_info.last_updated IS NULL THEN 0
        ELSE 1
    END,
    parser.participants_info.last_updated ASC
'''

create_table_query = '''
CREATE TABLE IF NOT EXISTS parser.participants_info (
    id TEXT PRIMARY KEY,
    className TEXT,
    parallelName TEXT,
    expValue TEXT NOT NULL,
    level INT NOT NULL,
    expToNextLevel INT NOT NULL,
    schoolId UUID NOT NULL,
    shortName TEXT NOT NULL,
    status TEXT NOT NULL,
    last_updated TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_school
        FOREIGN KEY (schoolId)
        REFERENCES parser.campuses(id)
        ON DELETE CASCADE
)
'''

upsert_query = '''
INSERT INTO parser.participants_info (id, className, parallelName, expValue, level, expToNextLevel,
                                 schoolId, shortName, status, last_updated)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
ON CONFLICT (id) DO UPDATE SET
    className = EXCLUDED.className,
    parallelName = EXCLUDED.parallelName,
    expValue = EXCLUDED.expValue,
    level = EXCLUDED.level,
    expToNextLevel = EXCLUDED.expToNextLevel,
    schoolId = EXCLUDED.schoolId,
    shortName = EXCLUDED.shortName,
    status = EXCLUDED.status,
    last_updated = NOW()
'''

delete_query = """
DELETE FROM parser.participants
WHERE id = %s
"""
