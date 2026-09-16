# Payments Processing Service

Асинхронный сервис обработки платежей: принимает запросы на оплату, обрабатывает их через
эмулируемый внешний платёжный шлюз и уведомляет вызывающую сторону о результате через webhook.

## Запуск стека

```sh
docker compose up
```

Поднимаются четыре сервиса:

- `postgres` — база данных
- `rabbitmq` — брокер (management UI на http://localhost:15672, guest/guest)
- `api` — FastAPI-приложение на http://localhost:8000, перед стартом выполняет `alembic upgrade head`
- `consumer` — разбирает платежи из очереди и отправляет webhook'и

`api` и `consumer` ждут healthcheck'ов `postgres`/`rabbitmq` перед стартом, а `consumer`
дополнительно ждёт, пока `api` станет healthy (это происходит только после применения миграций) —
поэтому `docker compose up` с чистого чекаута запускается без ручных шагов.

Секреты/конфигурация (`DATABASE_URL`, `RABBITMQ_URL`, `API_KEY`) заданы как переменные окружения
сервисов `api`/`consumer` в [docker-compose.yml](docker-compose.yml); эквивалентные значения для
локального запуска (без Docker) — в [.env.example](.env.example).

Все эндпоинты ниже требуют заголовок `X-API-Key` (по умолчанию `dev-api-key`, см. `docker-compose.yml`).

## Happy path

Создание платежа:

```sh
curl -s -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: dev-api-key" \
  -H "Idempotency-Key: demo-key-1" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "10.50",
    "currency": "USD",
    "description": "Test payment",
    "webhook_url": "https://httpbin.org/post"
  }'
# {"payment_id":"...","status":"pending","created_at":"..."}
```

Consumer выполняет (эмулируемый) вызов шлюза 2-5 секунд, прежде чем отправить webhook. Проверить
результат:

```sh
curl -s http://localhost:8000/api/v1/payments/<payment_id> -H "X-API-Key: dev-api-key"
# {"payment_id":"...","status":"succeeded","processed_at":"...", ...}
```

## Конфликт Idempotency-Key (409)

Повторное использование `Idempotency-Key` с другим телом запроса отклоняется; с тем же телом —
возвращает исходный платёж:

```sh
curl -s -w '\nHTTP %{http_code}\n' -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: dev-api-key" \
  -H "Idempotency-Key: demo-key-1" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "99.00",
    "currency": "USD",
    "description": "Different payment",
    "webhook_url": "https://httpbin.org/post"
  }'
# {"detail":"Idempotency-Key already used with a different request body"}
# HTTP 409
```

## Цепочка retry / DLQ

Укажите в `webhook_url` адрес, который всегда отвечает ошибкой (например,
`https://httpbin.org/status/500`), чтобы увидеть, как доставка webhook'а проходит через очереди
`payments.retry.1/2/3` (backoff 2с/8с/32с), прежде чем попасть в `payments.new.dlq`:

```sh
curl -s -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: dev-api-key" \
  -H "Idempotency-Key: demo-key-dlq" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "5.00",
    "currency": "USD",
    "description": "Always-failing webhook",
    "webhook_url": "https://httpbin.org/status/500"
  }'
```

Проследить эскалацию по retry-очередям можно в логах consumer'а (`docker compose logs -f consumer`),
либо проверить глубину DLQ напрямую (должна стать `1` примерно через 45с: задержка шлюза + backoff
2с + 8с + 32с):

```sh
curl -s -u guest:guest http://localhost:15672/api/queues/%2F/payments.new.dlq | python3 -c \
  "import json,sys; print(json.load(sys.stdin)['messages'])"
```

## Разработка

```sh
uv run pytest       # нужен доступный postgres по TEST_DATABASE_URL (по умолчанию localhost:5433)
uv run mypy app
uv run ruff check .
```
