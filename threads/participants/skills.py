from init import init_logging
import logging
import func
import db as database
from init import envs
from datetime import datetime

init_logging()

offset_my = 1000
batch_size = 100  # Размер пакета

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

def get_participants_skills():
    db = database.base.create_new_instance()
    db.create_table(create_table_query)

    participatns_ids = db.get_ids(participatns_ids_query)

    if not participatns_ids:
        logging.error("Не удалось получить идентификаторы учеников.")
        return

    for i in range(0, len(participatns_ids), batch_size):
        batch_ids = participatns_ids[i:i + batch_size]
        records = []
        for participant_id in batch_ids:
            try:
                status_code, participant = fetch_participant_skills(db, participant_id)
                if participant is None:
                    continue
                if status_code == 404:
                    logging.warning(f"Hе найдены скилы в школе {participant_id}")
                    # db.delete_missing_records(delete_query, (participant_id,))
                    records.extend(prepare_data([], participant_id))
                if 'skills' in participant and participant['skills']:
                    records.extend(prepare_data(participant['skills'], participant_id))
                else:
                    records.extend(prepare_data([], participant_id))
            except Exception as e:
                logging.error(f"Error processing participant {participant_id}: {e}")
        db.upsert_data(upsert_query, records)
        logging.info(f"Пакет с {i} по {i + batch_size} skills участников успешно записан в базу данных.")
    logging.error("Все skills участников успешно записаны в базу данных.")

participatns_ids_query = '''
SELECT
    parser.participants_info.id as login
FROM
    parser.participants_info
    LEFT JOIN parser.participants_skills
        ON parser.participants_info.id = parser.participants_skills.nickname
WHERE
    parser.participants_info.status = 'ACTIVE'
    AND parser.participants_info.id NOT LIKE '%%@%%'
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
