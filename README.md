## Sber Monitoring

Требуется Python 3.9 или выше.

Python-конструктор для описания HTTP-маршрутов мониторинга на разных доменах, методах и типах нагрузок (включая загрузку файлов). Каждый маршрут выполняется в отдельном потоке, а результат последнего запроса сохраняется в JSON (по умолчанию `monitoring_results.json`, либо в каталоге, если он указан), откуда его может прочитать агент Zabbix и передать в Grafana.

### Быстрый старт

1. (Опционально) создайте виртуальное окружение и установите зависимости:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Опишите нужные проверки в каталоге `config/routes/`. Можно создавать любое количество вложенных папок и файлов (`*.yml`, `*.yaml`, `*.json`). В репозитории уже есть пример структуры:
   ```
   config/routes/
   ├── httpbin/
   │   ├── auth.yaml
   │   ├── core.yaml
   │   ├── mutations.yaml
   │   └── upload.yaml
   ├── external/
   │   └── demo.yaml
   └── examples/
       └── custom_ca.yaml
   ```
3. Разовая проверка с подробным логом:
   ```bash
   python3 main.py --one-shot --log-level DEBUG
   ```
4. Постоянный мониторинг (например, под systemd или cron):
   ```bash
   python3 main.py --config config/routes --results-path monitoring_results/
   ```

### Формат конфигурации

#### Значения по умолчанию

| Поле/опция | Default | Комментарий |
| --- | --- | --- |
| `--config` | `config/routes` | Можно указать файл или каталог. |
| `--results-path` | `monitoring_results.json` | Файл или каталог (см. ниже). |
| `--log-level` | `INFO` | Измените на `DEBUG` для подробного вывода. |
| `--one-shot` | `false` | По умолчанию выполняет мониторинг постоянно. |
| `method` | `GET` | Определяется для каждого маршрута. |
| `interval` | `60` секунд | Минимум 1 секунда. |
| `timeout` | `10` секунд | Таймаут HTTP-запроса. |
| `allow_redirects` | `true` | Управляет следованием редиректам. |
| `verify_ssl` | `true` | Отключайте только при доверии к целевому хосту. |
| `body_max_chars` | `2048` | Длина сохраняемого body. |
| `file.field_name` | `file` | Имя поля при отправке файла. |
| `basic_auth` | не задано | Добавьте блок `basic_auth`, если нужно. |
| `ca_bundle` | не задано | Используйте для кастомных корневых сертификатов. |
| `TZ` | `Europe/Moscow` | Можно переопределить переменной окружения `TZ`. |

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
| `multipart_json_field` | ✖ | Имя поля для JSON-пейлоада, который будет добавлен в multipart вместе с файлом (по умолчанию `json`). |
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

или указать путь к файлу с JSON-данными, и сервис подставит содержимое:

```yaml
json: /home/user/test-data.json
# или относительный путь относительно config-файла:
json: payloads/create-request.json
```

Файл должен содержать корректный JSON.

Если одновременно указаны `file` и `json`, монитор отправит multipart/form-data, где JSON будет помещён отдельным полем. Имя поля можно
задать параметром `multipart_json_field` (по умолчанию используется `json`). Например:

```yaml
method: POST
url: https://example.org/upload
file:
  path: files/report.csv
  field_name: uploadFile
multipart_json_field: jsonBody
json:
  customer: TUZ
  retryCount: 3
```

В этом случае тело запроса будет содержать и файл, и поле `jsonBody` со строковым JSON-значением.

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

### Каталоги конфигураций и результатов

- Параметр `--config` принимает путь к одному файлу или к каталогу. При указании каталога скрипт рекурсивно собирает все подходящие файлы и формирует общий список маршрутов.
- Параметр `--results-path` принимает путь к JSON-файлу **или** к каталогу.  
  - Если указан файл (например, `monitoring_results.json`), туда складываются все результаты, как раньше.  
  - Если указан каталог (например, `monitoring_results/`), в нём создаются подкаталоги, полностью повторяющие структуру `config/routes`, а в каждом файле лежит JSON с результатами соответствующего набора маршрутов (например, `monitoring_results/httpbin/core.json`). Чтобы выбрать каталог, либо передайте путь, оканчивающийся слешем, либо заранее создайте нужную директорию.

### Структура JSON с результатами

Каждый результирующий JSON содержит последние показания своей группы:

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
