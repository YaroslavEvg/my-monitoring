## Sber Monitoring

Python-конструктор для описания HTTP-маршрутов мониторинга на разных доменах, методах и типах нагрузок (включая загрузку файлов). Каждый маршрут выполняется в отдельном потоке, а результат последнего запроса сохраняется в `monitoring_results.json`, откуда его может прочитать агент Zabbix и передать в Grafana.

### Быстрый старт

1. (Опционально) создайте виртуальное окружение и установите зависимости:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Опишите нужные проверки в `config/routes.yaml`. В примере уже есть:
   - GET-запрос к `https://httpbin.org/status/200`;
   - POST c multipart-файлом в `https://httpbin.org/post`.
3. Разовая проверка с подробным логом:
   ```bash
   python3 main.py --one-shot --log-level DEBUG
   ```
4. Постоянный мониторинг (например, под systemd или cron):
   ```bash
   python3 main.py --config config/routes.yaml --results-file monitoring_results.json
   ```

### Формат конфигурации

Каждый элемент в `routes` задаёт один HTTP-монитор. Ниже перечислены основные поля:

| Поле | Обязательное | Описание |
| --- | --- | --- |
| `name` | ✔ | Уникальное имя маршрута (ключ в `monitoring_results.json`). |
| `type` | ✖ | Тип монитора, сейчас поддерживается `http`. |
| `url` | ✔ | Полный URL. |
| `method` | ✖ | HTTP-метод, по умолчанию `GET`. |
| `interval` | ✖ | Пауза между запросами в секундах (не меньше 1). |
| `timeout` | ✖ | Таймаут HTTP-запроса. |
| `headers`, `params` | ✖ | Дополнительные заголовки и query-параметры. |
| `data` | ✖ | Тело запроса в обычном (form/urlencoded) виде. |
| `json` | ✖ | JSON-тело запроса. Если поле задано, библиотека `requests` отправит payload с `Content-Type: application/json`. |
| `file.path`, `file.field_name`, `file.content_type` | ✖ | Настройки отправки локального файла в multipart/form-data. |
| `max_response_chars` | ✖ | Сколько символов ответа сохранять для анализа. |
| `basic_auth.username`, `basic_auth.password` | ✖ | Пара логин/пароль для HTTP Basic Auth (заголовок `Authorization`). |
| `ca_bundle` | ✖ | Путь к кастомному PEM-файлу цепочки сертификатов для проверки TLS. |
| `enabled` | ✖ | Быстрое отключение маршрута без удаления. |
| `tags` | ✖ | Любые теги (строки) для последующей обработки в Zabbix. |

Чтобы отправить JSON в теле запроса, достаточно добавить блок:

```yaml
json:
  key: value
  items:
    - one
    - two
```

или указать путь к файлу/шаблону, а Python корректно сериализует структуру в JSON.  
Для защиты по Basic Auth добавьте:

```yaml
basic_auth:
  username: test-user
  password: test-pass
```

Для сервисов с самоподписанными сертификатами можно указать свой PEM-файл:

```yaml
ca_bundle: certs/internal-root.pem
```

Файл должен существовать на узле, где запускается мониторинг; Requests передаст его в параметр `verify`.

### Структура файла результатов

`monitoring_results.json` всегда содержит последние показания каждой проверки:

```json
{
  "schema_version": 1,
  "last_updated": "2024-05-28T12:00:00+00:00",
  "routes": {
    "httpbin-status": {
      "name": "httpbin-status",
      "url": "https://httpbin.org/status/200",
      "method": "GET",
      "timestamp": "2024-05-28T12:00:00+00:00",
      "response_time_ms": 123.4,
      "status_code": 200,
      "reason": "OK",
      "ok": true,
      "body_excerpt": "",
      "body_truncated": false,
      "error": null,
      "tags": ["demo", "status"]
    }
  }
}
```

Zabbix-агент может читать этот JSON локальным элементом (`vfs.file.contents`, `vfs.file.regexp` или пользовательским скриптом) и строить метрики/триггеры: например, проверять `status_code`, `response_time_ms` или флаг `ok`.
