import logging
from multiprocessing import Pool
from init import init_logging
import func
import db as database
from init import envs
from datetime import datetime

init_logging()

batch_size = 100  # Размер пакета
num_processes = 10  # Количество процессов

def fetch_participant_skills(db, participant_id):
    endpoint = f'participants/{participant_id}/skills'
    config = func.GraphqlConfig(
        base_url=envs['base_url'],
        api_version=envs['api_version'],
        db_manager=db,
        test=envs['test']
    )
    graphql_client = func.Graphql(config)
    status_code, data = graphql_client.graphql_with_retry(endpoint)
    return status_code, data

def prepare_data(skills, nickname):
    current_time = datetime.now()
    records = []

    for skill in skills:
        skill_name = skill['name']
        points = min(skill['points'], 2000)
        records.append((nickname, skill_name, points, current_time))

    if not skills:
        records.append((nickname, 'no skills in school21', 0, current_time))

    return records

def process_batch(batch_ids):
    db = database.base.create_new_instance()
    records = []
    for participant_id in batch_ids:
        try:
            logging.info(f"Запрос id {participant_id}")
            status_code, participant = fetch_participant_skills(db, participant_id)
            if status_code == 404:
                logging.error(f"Hе найдено в школе {participant_id}")
                continue
            if participant is None:
                continue
            if 'skills' in participant and participant['skills']:
                records.extend(prepare_data(participant['skills'], participant_id))
            else:
                records.extend(prepare_data([], participant_id))
        except Exception as e:
            logging.error(f"Error processing participant {participant_id}: {e}")
    db.upsert_data(upsert_query, records)
    logging.info(f"Пакет обработан и записан в базу данных: {batch_ids[0]}-{batch_ids[-1]}")

def get_participants_skills():
    db = database.base.create_new_instance()
    db.create_table(create_table_query)

    participatns_ids = db.get_ids(participatns_ids_query)

    if not participatns_ids:
        logging.error("Не удалось получить идентификаторы учеников.")
        return

    # Удаление дубликатов
    participatns_ids = list(set(participatns_ids))

    # Разделение списка идентификаторов на пакеты
    batches = [participatns_ids[i:i + batch_size] for i in range(0, len(participatns_ids), batch_size)]

    # Создание пула процессов и распределение пакетов по процессам
    with Pool(num_processes) as pool:
        pool.map(process_batch, batches)

    logging.info("Все skills участников успешно записаны в базу данных.")

participatns_ids_query = '''
SELECT
    parser.participants_info.id as login
FROM
    parser.participants_info
    LEFT JOIN parser.participants_skills
        ON parser.participants_info.id = parser.participants_skills.nickname
WHERE
    parser.participants_info.id != 'agroup'
    AND parser.participants_info.status != 'EXPELLED'
    AND parser.participants_info.status != 'BLOCKED'
    AND parser.participants_info.status != 'FROZEN'
ORDER BY
    CASE
        WHEN parser.participants_skills.last_updated IS NULL THEN 0
        ELSE 1
    END,
    parser.participants_skills.last_updated ASC
'''

create_table_query = """
CREATE TABLE IF NOT EXISTS parser.participants_skills (
    nickname VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    points INT NOT NULL,
    last_updated TIMESTAMP NOT NULL,
    PRIMARY KEY (nickname, name)
);
"""

upsert_query = """
INSERT INTO parser.participants_skills (nickname, name, points, last_updated)
VALUES (%s, %s, %s, %s)
ON CONFLICT (nickname, name)
DO UPDATE SET points = EXCLUDED.points, last_updated = EXCLUDED.last_updated;
"""

delete_query = """
DELETE FROM parser.participants
WHERE id = %s
"""
