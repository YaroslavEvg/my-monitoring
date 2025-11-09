from init import init_logging
import logging
import func
import db as database
from init import envs, telega_json
from datetime import datetime
import asyncio
import threading

init_logging()

offset_my = 100
batch_size = 50  # Размер пакета

# Определение блокировки
project_lock = threading.Lock()

def fetch_participant_projects(db, participant_id, offset=0, limit=offset_my):
    endpoint = f'participants/{participant_id}/projects?limit={limit}&offset={offset}'
    config = func.GraphqlConfig(
        base_url=envs['base_url'],
        api_version=envs['api_version'],
        db_manager=db,
        test=envs['test']
    )
    graphql_client = func.Graphql(config)
    status_code, data = graphql_client.graphql_with_retry(endpoint)
    return status_code, data

def prepare_project_data(projects, login):
    current_time = datetime.now()
    project_records = []
    team_member_records = []

    for project in projects:
        if project['status'] == 'ASSIGNED':
            continue
        project_id = project['id']
        title = project['title']
        type = project['type']
        status = project['status']
        final_percentage = project.get('finalPercentage')
        completion_date_time = project.get('completionDateTime')
        course_id = project.get('courseId')
        # logging.info(f"{project}")
        project_records.append((
            login, project_id, title, type, status, final_percentage,
            completion_date_time, course_id, current_time
        ))

        if project.get('teamMembers'):
            for member in project['teamMembers']:
                team_member_records.append((
                    login, project_id, member['login'], member['isTeamlead'], current_time
                ))

    return project_records, team_member_records

def get_participants_projects():
    # Использование блокировки для предотвращения параллельного выполнения
    with project_lock:
        db = database.base.create_new_instance()
        db.create_table(create_table_query)

        participant_ids = db.get_ids(participant_ids_query)

        if not participant_ids:
            logging.error("Не удалось получить идентификаторы участников.")
            return

        for i in range(0, len(participant_ids), batch_size):
            batch_ids = participant_ids[i:i + batch_size]
            project_records = []
            team_member_records = []

            for participant_id in batch_ids:
                offset = 0
                while True:
                    try:
                        # logging.error(f"fetch { participant_id} {offset}")
                        status_code, participant_projects = fetch_participant_projects(db, participant_id, offset)

                        if participant_projects is None:
                            break
                        if participant_projects['projects'] is None:
                            break
                        if status_code == 404 or status_code == 500 or status_code == 403:
                            logging.error(f"{status_code} Проекты не найдены для участника {participant_id}")
                            break

                        if 'projects' in participant_projects and participant_projects['projects']:
                            projects, team_members = prepare_project_data(participant_projects['projects'], participant_id)
                            # logging.info(f"{projects}\n\n\n")
                            project_records.extend(projects)
                            # logging.info(f"{project_records}\n\n\n")
                            team_member_records.extend(team_members)
                            if len(projects) < offset_my:
                                break
                        else:
                            # logging.error(f"{status_code} У участника {participant_id} нет проектов.")
                            # asyncio.run(telega_json(participant_projects))
                            # logging.error(f"empty")
                            break
                    except Exception as e:
                        logging.error(f"Ошибка при обработке участника {participant_id}: {e}")
                        break
                    offset += offset_my

            db.upsert_data(upsert_projects_query, project_records)
            db.upsert_data(upsert_team_members_query, team_member_records)
            logging.info(f"Пакет с {i} по {i + batch_size} проектов участников успешно записан в базу данных.")

        logging.error("Все проекты участников успешно записаны в базу данных.")

participant_ids_query = '''
SELECT
    parser.participants_info.id as login
FROM
    parser.participants_info
    LEFT JOIN parser.participants_projects
        ON parser.participants_info.id = parser.participants_projects.login
WHERE
        parser.participants_info.status = 'ACTIVE'
    AND parser.participants_info.parallelname = 'Core program'
    AND parser.participants_info.id NOT LIKE '%%@%%'
ORDER BY
    CASE
        WHEN parser.participants_projects.last_updated IS NULL THEN 0
        ELSE 1
    END,
    parser.participants_projects.last_updated ASC
'''

create_table_query = """
CREATE TABLE IF NOT EXISTS parser.participants_projects (
    id BIGSERIAL PRIMARY KEY,
    login TEXT NOT NULL,
    project_id BIGINT NOT NULL,
    title VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL CHECK (type IN ('INDIVIDUAL', 'GROUP', 'EXAM', 'EXAM_TEST')),
    status VARCHAR(50) NOT NULL CHECK (status IN ('ASSIGNED', 'REGISTERED', 'IN_PROGRESS', 'IN_REVIEWS', 'ACCEPTED', 'FAILED')),
    final_percentage INT,
    completion_date_time TIMESTAMP,
    course_id BIGINT,
    last_updated TIMESTAMP,
    CONSTRAINT fk_participant
        FOREIGN KEY (login)
        REFERENCES parser.participants_info(id)
        ON DELETE CASCADE,
    CONSTRAINT unique_project UNIQUE (project_id, login)
);
CREATE TABLE IF NOT EXISTS parser.participants_projects_team_members (
    id BIGSERIAL PRIMARY KEY,
    owner_login TEXT NOT NULL,
    project_id BIGINT NOT NULL,
    login TEXT NOT NULL,
    is_teamlead BOOLEAN NOT NULL,
    last_updated TIMESTAMP,
    CONSTRAINT fk_project
        FOREIGN KEY (project_id, owner_login)
        REFERENCES parser.participants_projects(project_id, login)
        ON DELETE CASCADE,
    CONSTRAINT fk_participant_member
        FOREIGN KEY (login)
        REFERENCES parser.participants_info(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_participant_member_owner
        FOREIGN KEY (owner_login)
        REFERENCES parser.participants_info(id)
        ON DELETE CASCADE,
    CONSTRAINT unique_team_member UNIQUE (owner_login, project_id, login)
);
"""

upsert_projects_query = """
INSERT INTO parser.participants_projects (
    login, project_id, title, type, status, final_percentage,
    completion_date_time, course_id, last_updated
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (login, project_id)
DO UPDATE SET
    title = EXCLUDED.title,
    type = EXCLUDED.type,
    status = EXCLUDED.status,
    final_percentage = EXCLUDED.final_percentage,
    completion_date_time = EXCLUDED.completion_date_time,
    course_id = EXCLUDED.course_id,
    last_updated = EXCLUDED.last_updated;
"""

upsert_team_members_query = """
INSERT INTO parser.participants_projects_team_members (
    owner_login, project_id, login, is_teamlead, last_updated
) VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (owner_login, project_id, login)
DO UPDATE SET
    is_teamlead = EXCLUDED.is_teamlead,
    last_updated = EXCLUDED.last_updated;
"""

delete_query = """
DELETE FROM parser.participants
WHERE id = %s
"""
