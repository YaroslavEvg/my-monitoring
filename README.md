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
| `file.zip_enabled` | `false` | Включает автоматическую сборку zip из файла/папки перед отправкой (по умолчанию файл уходит как есть). |
| `encoding_file` | `utf-8` | Целевая кодировка текстовых файлов перед упаковкой в zip; используется как `charset` для `text/*` без zip. |
| `encoding_json` | `utf-8` | Кодировка JSON-части (multipart и query-параметр). |
| `basic_auth` | не задано | Добавьте блок `basic_auth`, если нужно. |
| `ca_bundle` | не задано | Используйте для кастомных корневых сертификатов. |
| `TZ` | `Europe/Moscow` | Можно переопределить переменной окружения `TZ`. |
| `multipart_json_field` | `json` | Имя части multipart-формы для JSON при наличии файлов (часть без filename). |
| `json_query_param` | не задано | Если указать, JSON будет сериализован и добавлен в query-параметр. |

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
| `file.path`, `file.field_name`, `file.content_type` | ✖ | Настройки отправки локального файла в multipart/form-data. Для упаковки файла/папки в zip укажите `file.zip_enabled: true` (обязательно для каталогов). |
| `file.zip_enabled` | ✖ | Упаковать файл/каталог в zip перед отправкой. Для каталогов требуется `true`; для файлов по умолчанию отправка как есть (без zip). |
| `encoding_file` | ✖ | Целевая кодировка текстовых файлов перед упаковкой в zip (по умолчанию `utf-8`); используется как `charset` для `text/*` без zip. |
| `encoding_json` | ✖ | Кодировка сериализованного JSON (multipart и query-параметр), по умолчанию `utf-8`. |
| `multipart_json_field` | ✖ | Имя поля для JSON-пейлоада внутри multipart (часть без filename, `Content-Type: application/json`). |
| `json_query_param` | ✖ | Имя query-параметра, в который нужно сериализовать JSON вместо тела. |
| `max_response_chars` | ✖ | Сколько символов ответа сохранять для анализа. |
| `basic_auth.username`, `basic_auth.password` | ✖ | Пара логин/пароль для HTTP Basic Auth (заголовок `Authorization`). |
| `ca_bundle` | ✖ | Путь к кастомному PEM-файлу цепочки сертификатов для проверки TLS. |
| `enabled` | ✖ | Быстрое отключение маршрута без удаления. |
| `tags` | ✖ | Любые теги (строки) для последующей обработки в Zabbix. |
| `children` | ✖ | Дочерние запросы, выполняемые последовательно после родителя (каждый элемент — такой же маршрут; допускается вложенность). |

Параметры `encoding_file` и `encoding_json` можно также указать как `encondig_file` и `encondig_json` для совместимости.

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

#### Дочерние запросы и подстановки из ответа

Можно описывать дополнительные запросы внутри родительского маршрута через `children`. Они выполняются
последовательно в рамках одного цикла мониторинга; `interval` учитывается только у корневого маршрута.

Для подстановок используйте JSON-пути вида `$.field.subfield` или `$.items[0].id`. Путь применяется к
JSON-ответу родителя. Если значение нужно встроить в строку, используйте `{{$.path}}`. Подстановки
работают в `url`, `headers`, `params`, `data`, `json`. Если JSON-ответа нет или путь не найден, значение
останется без изменений.

В результатах сохраняется только один запрос из цепочки: первый с невалидным кодом ответа (`ok=false`),
а если все успешны — последний дочерний запрос. Время (`response_time_ms`) — сумма всех запросов в цепочке.

```yaml
routes:
  - name: job-start
    url: https://example/api/start
    method: POST
    json:
      payload: demo
    children:
      - name: job-status
        url: https://example/api/status/{{$.job_id}}
        method: GET
        children:
          - name: job-result
            url: https://example/api/result/{{$.result_id}}
            method: GET
```

Если одновременно требуется отправить файл и JSON (multipart/form-data), укажите файл в секции `file`, а JSON — как обычно. Монитор соберёт multipart в формате, который работает с требуемым бэкендом: JSON передаётся отдельной частью `application/json` **без** `filename`, файл — обычной частью с именем файла. Это единственный поддерживаемый вариант загрузки файлов. Опция `multipart_json_filename` больше не используется: JSON отправляется без имени файла. При необходимости можно переименовать поле JSON через `multipart_json_field` (по умолчанию `json`) и задать кодировку JSON-части через `encoding_json` (по умолчанию `utf-8`). Если `zip_enabled: false` (значение по умолчанию), файл отправится как есть с исходным именем и указанным `content_type`. Для текстовых `content_type` (начинающихся с `text/`) агент добавит `charset=<encoding_file>`, если он не указан. Если нужно задать другой `charset` вручную, укажи его прямо в `file.content_type` (например, `text/plain; charset=windows-1251`) — тогда он не будет переопределён. Если нужно отправлять файл/каталог как zip, укажите `zip_enabled: true` внутри блока `file` — при этом для не-zip файла будет создан архив `<имя_файла_без_расширения>.zip`, для каталога — `<имя_папки>.zip`, содержимое перекодируется в `encoding_file` (по умолчанию `utf-8`) при возможности. Для каталога `zip_enabled` обязателен. Архив создаётся в отдельной временной папке перед каждым запросом и удаляется после него.

```yaml
file:
  path: files/data.csv
  field_name: upload
  content_type: application/zip
  zip_enabled: true
json: payloads/meta.json
multipart_json_field: meta  # опционально: имя JSON-поля внутри multipart
encoding_file: windows-1251 # опционально: целевая кодировка текстовых файлов перед упаковкой в zip (alias: encondig_file)
encoding_json: windows-1251 # опционально: кодировка JSON-части (alias: encondig_json)
```

Эквивалентный вызов `requests`, который сформирует агент (при не-zip файле будет создан временный `data.zip` в отдельной временной директории):

```python
json_payload = ...  # содержимое, указанное в блоке json
with open("/tmp/<tmpdir>/data.zip", "rb") as f:  # временный zip, который агент создаёт из исходного файла перед запросом
    files = {
        "upload": ("data.zip", f, "application/zip"),
        "meta": (None, json.dumps(json_payload).encode("windows-1251"), "application/json; charset=windows-1251"),
    }
```

Если в `file.path` указан каталог, агент упакует сам каталог (с корневой папкой) и все вложенные файлы в zip и отправит его как `application/zip`.

Отправка файла в multipart, где JSON передаётся в query-параметре, воспользуйтесь `json_query_param`. Агент сериализует JSON в строку, экранирует и добавит к URL (`?json=%7B...%7D`), а тело запроса останется multipart только с файлом:

```yaml
file:
  path: files/sample_payload.txt
  field_name: file
  content_type: text/plain
json: payloads/project.json
json_query_param: json
headers:
verify_ssl: false  # если нужно игнорировать SSL-ошибки
```
JSON для query-параметра сериализуется с кодировкой `encoding_json` (по умолчанию `utf-8`).

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

> Важно: для groovy-стиля убедитесь, что
> - указаны `json_query_param` и `file`;
> - `json` содержит готовый JSON (можно указать путь к файлу);
> - `headers.Content-Type` установлен в `multipart/form-data`, если бэкенд это требует;
> - при необходимости отключено SSL через `verify_ssl: false`.

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

Если у маршрута есть `children`, в результатах хранится только выбранный запрос из цепочки (см. выше).

Zabbix-агент может читать этот JSON локальным элементом (`vfs.file.contents`, `vfs.file.regexp` или пользовательским скриптом) и строить метрики/триггеры: например, проверять `status_code`, `response_time_ms` или флаг `ok`.
