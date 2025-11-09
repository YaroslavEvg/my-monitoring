from query import query
# import common as c
from init import init_logging
import logging
from apscheduler.schedulers.background import BackgroundScheduler
import func
import db as database
from init import envs
from psycopg2 import sql

init_logging()

def get_campus():
    db = database.base.create_new_instance()
    endpoint = 'campuses'
    config = func.GraphqlConfig(
        base_url=envs['base_url'],
        api_version=envs['api_version'],
        db_manager=db,
        # token=db.fetch_auth_data(),
        test=envs['test']
    )
    graphql_client = func.Graphql(config)

    status_code, data = graphql_client.graphql_with_retry(endpoint)
    campuses = data['campuses']

    db.create_table(create_table_query)
    db.upsert_data(upsert_query, [(campus['id'], campus['shortName'], campus['fullName']) for campus in campuses])
    json_ids = tuple(campus['id'] for campus in campuses)
    db.delete_missing_records(delete_query, (json_ids,))
    logging.error(f"Поисковый запрос кампусов из {len(campuses)} комбинаций были выполнены.")

create_table_query = '''
CREATE TABLE IF NOT EXISTS parser.campuses (
    id UUID PRIMARY KEY,
    shortName TEXT,
    fullName TEXT,
    last_updated TIMESTAMP DEFAULT NOW()
)
'''

upsert_query = '''
INSERT INTO parser.campuses (id, shortName, fullName, last_updated)
VALUES (%s, %s, %s, NOW())
ON CONFLICT (id) DO UPDATE SET
    shortName = EXCLUDED.shortName,
    fullName = EXCLUDED.fullName,
    last_updated = NOW()
'''


delete_query = sql.SQL('''
DELETE FROM parser.campuses
WHERE id NOT IN %s
''')
