import requests
import logging
import time
from init import init_logging, envs, telega_json
import asyncio
from datetime import datetime, timedelta
import pytz
import inspect
from requests.exceptions import SSLError

init_logging()

class GraphqlConfig:
    def __init__(self, base_url, api_version, db_manager, test=False):
        self.base_url = base_url
        self.api_version = api_version
        self.db_manager = db_manager
        self.test = test

class Graphql:
    def __init__(self, config):
        self.config = config

    def log_request_info(self, endpoint):
        if self.config.test:
            logging.info(f"Base URL: {self.config.base_url}")
            logging.info(f"API Version: {self.config.api_version}")
            logging.info(f"Endpoint: {endpoint}")

    def prepare_headers(self, token):
        return {
            'content-type': 'application/json',
            'Authorization': f'Bearer {token}'
        }

    def make_request(self, url, headers):
        if self.config.test:
            logging.info(f"Making GET request to {url}")
        return requests.get(url, headers=headers)

    def handle_response(self, answer):
        answer.raise_for_status()
        answer_code = int(answer.status_code)
        answer_text = answer.json()
        if self.config.test:
            logging.info(f"Status code: {answer_code}, Response text: {answer_text}")
        return answer_code, answer_text

    def handle_http_error(self, http_err, url, headers):
        caller_frame = inspect.stack()[3]
        caller_function = caller_frame.function
        answer_code = http_err.response.status_code
        try:
            answer_text = http_err.response.json() if http_err.response.content else str(http_err)
        except ValueError:
            answer_text = {"message": "Invalid JSON response"}

        if answer_code != 429:
            logging.error(f'HTTP error occurred: {answer_code}, {url}')
            asyncio.run(telega_json(answer_text))

        return answer_code, answer_text

    def handle_exception(self, err):
        if isinstance(err, SSLError):
            #logging.error(f'SSL error occurred: {err}')
            return 500, {"message": "SSL error occurred, but ignored"}

        logging.error(f'Other error occurred: {err}')
        asyncio.run(telega_json({"message": str(err)}))
        return 500, {"message": str(err)}

    def process_response(self, answer_code, answer_text):
        if answer_code == 200:
            return 200, answer_text
        elif answer_code == 400:
            logging.error("400 BAD_REQUEST:")
            asyncio.run(telega_json(answer_text))
            return 400, {"code": "BAD_REQUEST", "message": answer_text.get('message', 'Bad request')}
        elif answer_code == 401:
            return 401, {"code": "UNAUTHORIZED", "message": "Unauthorized"}
        elif answer_code == 429:
            return 429, {"code": "TOO_MANY_REQUESTS", "message": "Too many requests"}
        elif answer_code == 500:
            logging.error("500 INTERNAL_SERVER_ERROR:")
            asyncio.run(telega_json(answer_text))
            return 500, {"code": "INTERNAL_SERVER_ERROR", "message": answer_text.get('message', 'Internal Server Error')}
        return answer_code, answer_text

    def graphql(self, endpoint):
        self.log_request_info(endpoint)

        # Получение нового токена перед каждым запросом
        token = self.config.db_manager.fetch_auth_data()
        if not token:
            logging.error("Невозможно получить токен для аутентификации")
            return 401, {"code": "UNAUTHORIZED", "message": "Unauthorized"}

        headers = self.prepare_headers(token)
        url = f"{self.config.base_url}/{self.config.api_version}/{endpoint}"

        try:
            answer = self.make_request(url, headers)
            answer_code, answer_text = self.handle_response(answer)
        except requests.HTTPError as http_err:
            answer_code, answer_text = self.handle_http_error(http_err, url, headers)
        except Exception as err:
            return self.handle_exception(err)

        if self.config.test:
            logging.info("graphql end")

        return self.process_response(answer_code, answer_text)

    def graphql_with_retry(self, endpoint):
        while True:
            status_code, response = self.graphql(endpoint)
            if status_code == 200:
                return status_code, response
            elif status_code == 429:
                time.sleep(1)
            else:
                return status_code, response
                logging.info(f"Request failed with status code {status_code}. Retrying in 20 minutes...")
                time.sleep(20 * 60)  # Ждем 20 минут перед повторным запросом

def generates_dates(weeks=2):
    # Определяем текущую дату и время в UTC
    utc_now = datetime.now(pytz.utc)
    # Начало периода - начало текущего дня в UTC
    start_date = utc_now.replace(hour=0, minute=0, second=0, microsecond=0)
    # Конец периода - плюс две недели от текущего дня в UTC
    end_date = start_date + timedelta(weeks=weeks)

    # Форматируем даты в строку для URL
    start_date_str = start_date.isoformat().replace("+00:00", "Z")
    end_date_str = end_date.isoformat().replace("+00:00", "Z")
    return start_date_str, end_date_str

# def get_auth_data_from_db():
#     while True:
#         try:
#             with connect_db() as conn:
#                 with conn.cursor() as cursor:
#                     cursor.execute("SELECT school_id, token FROM token ORDER BY updated_at DESC LIMIT 1;")
#                     result = cursor.fetchone()
#                     if result:
#                         logging.info("Данные аутентификации успешно получены из базы данных.")
#                         return result
#                     else:
#                         logging.error("Данные аутентификации отсутствуют в базе данных.")
#                         time.sleep(envs.retry_delay)
#         except psycopg2.DatabaseError as e:
#             logging.error(f"Ошибка при получении данных аутентификации из базы данных: {e}. "
#                           f"Повторная попытка через {envs.retry_delay} секунд.")
#             time.sleep(envs.retry_delay)
# curl -X 'GET' \
#   'https://platform-api.21-school.ru/services/21-school/api/v1/participants/desperos%40student.21-school.ru' \
#   -H 'accept: */*' \
#   -H 'Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJ5V29landCTmxROWtQVEpFZnFpVzRrc181Mk1KTWkwUHl2RHNKNlgzdlFZIn0.eyJleHAiOjE3MjEwOTg2NDgsImlhdCI6MTcyMTA2MjY1MCwiYXV0aF90aW1lIjoxNzIxMDYyNjQ4LCJqdGkiOiI2NGVhM2E3Ni1lZmVjLTQwYWQtOWVlMS00YWMyYjUxN2ExNWQiLCJpc3MiOiJodHRwczovL2F1dGguc2JlcmNsYXNzLnJ1L2F1dGgvcmVhbG1zL0VkdVBvd2VyS2V5Y2xvYWsiLCJhdWQiOiJhY2NvdW50Iiwic3ViIjoiMWQ5ZmU4MzEtMTExZC00YzQ2LTgwMmUtMDMzNWQ5NzM4YTg2IiwidHlwIjoiQmVhcmVyIiwiYXpwIjoic2Nob29sMjEiLCJub25jZSI6IjY5MTg2MGQ1LWE3OGMtNDk0Ni04OTk0LTQxZGZmYzEwY2FiMSIsInNlc3Npb25fc3RhdGUiOiIyMzQxMzljMS0wMTkxLTRiNzktODBkMC0zOGJmMTFmMzgwYWMiLCJhY3IiOiIxIiwiYWxsb3dlZC1vcmlnaW5zIjpbImh0dHBzOi8vZWR1LjIxLXNjaG9vbC5ydSIsImh0dHBzOi8vZWR1LWFkbWluLjIxLXNjaG9vbC5ydSJdLCJyZWFsbV9hY2Nlc3MiOnsicm9sZXMiOlsiZGVmYXVsdC1yb2xlcy1lZHVwb3dlcmtleWNsb2FrIiwib2ZmbGluZV9hY2Nlc3MiLCJ1bWFfYXV0aG9yaXphdGlvbiJdfSwicmVzb3VyY2VfYWNjZXNzIjp7ImFjY291bnQiOnsicm9sZXMiOlsibWFuYWdlLWFjY291bnQiLCJtYW5hZ2UtYWNjb3VudC1saW5rcyIsInZpZXctcHJvZmlsZSJdfX0sInNjb3BlIjoib3BlbmlkIHByb2ZpbGUgZW1haWwiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwidXNlcl9pZCI6IjBmMDFlN2YzLTlhYjAtNGVhZC05OWEzLTc4MmM3NDc5ZjlhZSIsIm5hbWUiOiJEZXNwZXJvIFNjaGF1ZXIiLCJhdXRoX3R5cGVfY29kZSI6ImRlZmF1bHQiLCJwcmVmZXJyZWRfdXNlcm5hbWUiOiJkZXNwZXJvc0BzdHVkZW50LjIxLXNjaG9vbC5ydSIsImdpdmVuX25hbWUiOiJEZXNwZXJvIiwiZmFtaWx5X25hbWUiOiJTY2hhdWVyIiwiZW1haWwiOiJkZXNwZXJvc0BzdHVkZW50LjIxLXNjaG9vbC5ydSJ9.Fq-NUsVdNouz23S1EnY11pIuRk5XNg7EM-mAxJTd_FFDGuX3e7NydiYpO7Gtj0GlzUwPetdwIh77JYMpbaYRiXmWPNTINaKahqD9zXxrEWMFSbcAOE9WDM0zdqqxB4mgDi44YlKr9nzU2k5MVdXv3XcCaH6OpQuBXPxrO0fV2N_ryz-JDO1B9E9wWMW4AaTmDzg0MmrmGaMu19PfJ_0a0pTXIyaFO5cinxl_Xc9D7CTXsSIhI_5ay4ZB9bDRRTIKEpKzaLcKjz9CI3cJzosr4WJU00DoxaURFEtlO1Sm9jIJ3csEnm-EhNg_f8u56UebMmaHQLQELQ8L53btx0KF5g'
# agroup%40student.21-school.ru
# curl -X 'GET' \
#    'https://platform-api.21-school.ru/services/21-school/api/v1/participants/agroup%40student.21-school.ru' \
#    -H 'accept: */*' \
#    -H 'Authorization: Bearer '
# <!DOCTYPE HTML><html lang="en-US"><head> <meta charset="UTF-8"/> <title>Access denied</title> <style type="text/css"> html, body{width: 100%; height: 100%; margin: 0; padding: 0;}body{background-color: #f7f7f7; font-family: Helvetica, Arial, sans-serif; font-size: 100%;}h1{font-size: 1.5em; color: #454545; text-align: center;}p{font-size: 1em; color: #454545; text-align: center; margin: 10px 0 0 0;}.attribution{margin-top: 20px;}</style></head><body> <table width="100%" height="100%" cellpadding="20"> <tr> <td align="center" valign="middle"> <div> <h1> <span data-translate="checking_browser">Ваш запрос был заблокирован системой защиты.</span> </h1> <p data-translate="process_is_automatic"> Просим Вас обратиться в службу технической <a href="mailto:support@sberclass.ru?subject=Blocked e2e9c2b1-7593-4735-9157-d49bb7c00754&body=Hello, my request got blocked :(">поддержки</a><br>Контакты для связи: Email: support@sberclass.ru ; Телефон: 8 (800) 775-89-51 </p></div><div class="attribution"> <p style="font-size: 12px;">Request ID: e2e9c2b1-7593-4735-9157-d49bb7c00754</p></div></td></tr></table></body></html>
