import psycopg2
from psycopg2 import sql
import logging
import time
from init import init_logging, envs

init_logging()

auth_query = "SELECT token FROM public.token ORDER BY updated_at DESC LIMIT 1"

class DatabaseManager:
    def __init__(self, dbname, user, password, host, port):
        self.dbname = dbname
        self.user = user
        self.password = password
        self.host = host
        self.port = port

    def __enter__(self):
        self.connection = psycopg2.connect(
            dbname=self.dbname,
            user=self.user,
            password=self.password,
            host=self.host,
            port=self.port
        )
        self.cursor = self.connection.cursor()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_tb:
            self.connection.rollback()
        else:
            self.connection.commit()
        self.cursor.close()
        self.connection.close()

    def execute_query(self, query, params=None):
        with self as db:
            try:
                db.cursor.execute(query, params)
                if db.cursor.description:
                    return db.cursor.fetchall()
            except Exception as e:
                logging.error(f"Ошибка выполнения запроса: {e}")
                raise e

    def execute_query_with_retry(self, query, params=None):
        while True:
            try:
                with self as db:
                    db.cursor.execute(query, params)
                    if db.cursor.description:
                        result = db.cursor.fetchall()
                        return result
                    db.connection.commit()
                    return None
            except psycopg2.DatabaseError as e:
                logging.error(f"Ошибка выполнения запроса: {e}. Повторная попытка через {envs['RETRY_DELAY']} секунд.")
                time.sleep(envs['RETRY_DELAY'])

    def create_table(self, create_table_query):
        self.execute_query_with_retry(create_table_query)

    def upsert_data(self, upsert_query, data):
        for record in data:
            self.execute_query_with_retry(upsert_query, record)

    def bulk_upsert_data(self, upsert_query, data):
        with self as db:
            try:
                db.cursor.executemany(upsert_query, data)
                db.connection.commit()
            except Exception as e:
                logging.error(f"Ошибка выполнения запроса: {e}")
                raise e

    def delete_missing_records(self, delete_query, params):
        self.execute_query_with_retry(delete_query, params)

    def fetch_auth_data(self):
        result = self.execute_query_with_retry(auth_query)
        if result:
            return result[0][0]
        else:
            logging.error("Данные аутентификации отсутствуют в базе данных.")
            return None

    def get_ids(self, query):
        ids = self.execute_query_with_retry(query)
        if ids is None:
            return []
        return [row[0] for row in ids]

    def create_new_instance(self):
        return DatabaseManager(
            dbname=self.dbname,
            user=self.user,
            password=self.password,
            host=self.host,
            port=self.port
        )


# Инициализация базового экземпляра #
base = DatabaseManager(
    dbname=envs['DATABASE_NAME'],
    user=envs['DATABASE_USERNAME'],
    password=envs['DATABASE_PASSWORD'],
    host=envs['DATABASE_HOST'],
    port=envs['DATABASE_PORT']
)
