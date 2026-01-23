## Логика работы мониторинга

Этот документ объясняет цепочки запросов, подстановки из ответа, фильтры и multipart-особенности.

### Как выполняются цепочки

- Каждый маршрут запускается как корневой запрос.
- Если в нём есть `children`, они выполняются последовательно, в том порядке, как записаны в конфиге.
- Дети выполняются независимо от наличия JSON-ответа, но без подстановок из ответа.

#### Задержки

- `delay_before` — пауза перед конкретным запросом (в секундах).
- `children_delay` — пауза между родителем и его детьми (применяется к детям, если у ребёнка нет `delay_before`).

Пример:
```yaml
children_delay: 2
children:
  - name: step-1
    delay_before: 5  # перекрывает children_delay
```

### Ожидание поля в ответе (`wait_for`)

Если нужно опрашивать сервис, пока не появится поле в JSON-ответе:

```yaml
wait_for:
  path: $.result_id
  attempts: 5
  delay: 2
```

- Запрос повторяется до `attempts` раз.
- Между попытками пауза `delay`.
- Если поле не найдено — результат помечается `ok=false`, а в `error` пишется сообщение.

### Какой результат сохраняется

В JSON результата записывается только один запрос из цепочки:

- первый с `ok=false`, если он есть;
- иначе последний дочерний.

`response_time_ms` — сумма времени всех запросов и ожиданий в цепочке.

### Подстановки из ответа

Подстановки работают в `url`, `headers`, `params`, `data`, `json`.

Варианты:
- **Целое значение**: строка является путём.
  ```yaml
  json:
    uuid: $.job.id
  ```
- **Шаблон внутри строки**:
  ```yaml
  url: "https://api.example/job/{{$.job.id}}"
  ```

Если путь не найден, значение не меняется.

### env и переменные окружения

Поддерживается подстановка `${VAR}` из:
- переменных окружения процесса;
- блока `env` в конфиге (глобальный);
- блока `env` внутри маршрута (перекрывает глобальный).

Подстановка применяется ко всем строкам в маршруте, включая `basic_auth` и содержимое JSON-файлов.

### JSON-пути и фильтры

Базовый синтаксис:
- `$.field.subfield`
- `$.items[0].id`
- `$.[0].id` (если корневой ответ — массив)

Фильтры по значению:
- `$.items[key=value].id`
- `$.items[key="value"].id`
- `$.items[key==value].id` (эквивалентно `=`)

Несколько условий через `&`:
- `$.items[key1=val1&key2=val2].id`

Вложенные пути в условиях:
- `$.items[meta.code=200&meta.type="ok"].id`
- `$.items[fields[name="python"].value="need_value"].uuid`

Фильтр в корневом массиве:
- `$.[tech.techName="OpenShift"&fields[name="cluster"].value="test"].uuid`

Поведение:
- выбирается **первый** элемент списка, где все условия совпали;
- если совпадений нет — значение не подставляется.

#### Про кавычки в YAML

Если в выражении есть `&`, лучше оборачивать строку в кавычки.

Рекомендуемые варианты:
```yaml
url: 'https://example/api/{{ $.[tech.techName="OpenShift"&fields[name="cluster"].value="test"].uuid }}'
```

или
```yaml
url: "https://example/api/{{ $.[tech.techName='OpenShift'&fields[name='cluster'].value='test'].uuid }}"
```

### Multipart с несколькими JSON-частями

Можно отправлять несколько JSON-частей в multipart:

```yaml
multipart_json_fields:
  - field_name: meta
    json:
      source: monitoring
  - field_name: payload
    json: payloads/request.json
    encoding: utf-8
```

- каждая часть получает `Content-Type: application/json; charset=<encoding>`;
- если `encoding` не задана, берётся `encoding_json`.

### Текстовые файлы в multipart без zip

Если `content_type` начинается с `text/`, агент добавит `charset=<encoding_file>`, если он не задан.

Пример ручного charset:
```yaml
file:
  content_type: text/plain; charset=windows-1251
```

### Где смотреть итоговый URL

В `monitoring_results.json` поле `url` содержит уже подставленное значение (если подстановка сработала).
