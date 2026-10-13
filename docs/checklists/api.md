# Чек-лист: API

**Модуль:** API

**Приоритет:** Высокий

**Окружение:** Production / Local

**Swagger:** http://localhost:5000/docs (только при DEBUG=True)

**Внешнее ограничение:** OpenDota — 60 RPS

## Общие проверки

- [ ] Swagger доступен локально (`/docs`) при `DEBUG=True`
- [ ] Swagger НЕ доступен при `DEBUG=False`
- [ ] OpenAPI-схема валидна
- [ ] Все эндпоинты отвечают за разумное время (<2 сек)
- [ ] Ответы в формате JSON (кроме `/` и `/login` — HTML/redirect)
- [ ] Content-Type: `application/json`
- [ ] Ошибки возвращают корректный HTTP-статус
- [ ] Ошибки содержат понятное сообщение
- [ ] Пагинации нет ни на одном эндпоинте

## Авторизация

### `GET /login`
- [ ] → 307 редирект на `steamcommunity.com/openid/login`
- [ ] В URL есть `openid.return_to` с корректным `BASE_URL`

### `GET /processlogin`
- [ ] Валидный ответ Steam → 307 редирект на `/`
- [ ] Сессия установлена (`session` cookie)
- [ ] Невалидный ответ Steam → 401 `{"error": "steam_auth_failed"}`
- [ ] Новый пользователь → создаётся в БД, запускается фоновый сбор
- [ ] Существующий пользователь → обновляется ник/аватар
- [ ] Ошибка конвертации Steam ID → 400

### `GET /logout`
- [ ] Сессия очищена
- [ ] → 307 редирект на `/`
- [ ] После выхода `/me` → 401

### `GET /me`
- [ ] Авторизованный → 200 OK
- [ ] Гость → 401 `{"detail": "not_authenticated"}`
- [ ] Пользователь удалён из БД → 401, сессия очищена

### `GET /me/profile`
- [ ] Авторизованный → 200 OK
- [ ] Гость → 401

### `GET /me/stats`
- [ ] Авторизованный → 200 OK
- [ ] Гость → 401

## Пользователи

### `GET /users`
- [ ] → 200 OK
- [ ] Без авторизации → 200 OK
- [ ] Ответ — JSON-массив
- [ ] Поля: `id`, `nickname`, `avatar_url`, `account_id`, `last_updated`
- [ ] Пустой список → `[]`
- [ ] POST/PUT/DELETE → 405

## Профиль

### `GET /profile/{user_id}`
- [ ] Существующий → 200 OK
- [ ] Поля: `user`, `profile` (`rank_tier`, `rank_str`, `mmr_estimate`, `updated_at`)
- [ ] Нет статистики → 200 с `profile: null` и `message`
- [ ] Несуществующий → 404
- [ ] `user_id = 0` → 404
- [ ] `user_id = -1` → 400 (невалидный ID)
- [ ] `user_id = abc` → 400

## Статистика

### `GET /stats/{user_id}`
- [ ] Существующий → 200 OK
- [ ] Поля: `user`, `stats`
- [ ] `games_total`, `wins_total`, `losses_total`, `winrate_total`
- [ ] `games_recent`, `wins_recent`, `winrate_recent`
- [ ] `avg_kills`, `avg_deaths`, `avg_assists`, `avg_kda`
- [ ] Нет статистики → 200 с `stats: null` и `message`
- [ ] Несуществующий → 404

### `GET /stats/{user_id}/heroes`
- [ ] `scope=all` → 200, `meta.scope = "all"`, `meta.patch = null`
- [ ] `scope=patch` → 200, `meta.scope = "patch"`, `meta.patch` с данными
- [ ] `scope` по умолчанию → `"all"`
- [ ] `scope=invalid` → 400 (не 422)
- [ ] `limit` по умолчанию → 10
- [ ] `limit=1` → 1 герой
- [ ] `limit=100` → до 100 героев
- [ ] `limit=0` → 400
- [ ] `limit=101` → 400
- [ ] `limit=-1` → 400
- [ ] `limit=abc` → 400
- [ ] Несуществующий user_id → 404
- [ ] Нет патча в БД → 200 с `heroes: []` и `message`
- [ ] Поля: `hero_id`, `hero_name`, `hero_image`, `games`, `wins`, `winrate`

### `GET /stats/{user_id}/recent`
- [ ] → 200 OK
- [ ] `recent.games` ≤ 20
- [ ] `recent.wins` ≤ games
- [ ] `recent.winrate` = `wins/games * 100`
- [ ] `recent.heroes` — агрегированы по hero_id
- [ ] Сортировка по `games` (убывание)
- [ ] Нет матчей → 200 с `recent: null` и `message`
- [ ] Несуществующий → 404

### `GET /stats/{user_id}/patch`
- [ ] → 200 OK
- [ ] `patch.id`, `patch.name`, `patch.released_at`
- [ ] `summary.games`, `summary.wins`, `summary.winrate`
- [ ] `heroes_by_games` — топ-5 по играм
- [ ] `heroes_by_winrate` — топ-5 по WR, только с `games >= 3`
- [ ] Нет патча → 200 с `patch: null` и `message`
- [ ] Несуществующий → 404
- [ ] Игрок не играл в патче → `summary.games = 0`, WR = 0

### `GET /stats/{user_id}/peers`
- [ ] 200 OK для **авторизованного** (свой профиль)
- [ ] 401 для **гостя**
- [ ] 403 для **авторизованного** (чужой профиль)
- [ ] 404 для несуществующего user_id
- [ ] `limit` по умолчанию → 5
- [ ] `limit=1` → 1 пир
- [ ] `limit=20` → до 20 пиров
- [ ] `limit=0` → 400
- [ ] `limit=21` → 400
- [ ] `limit=-1` → 400
- [ ] Поля: `account_id`, `nickname`, `avatar`, `with_games`, `with_win`, `winrate`, `last_played`

## Валидация и ошибки

- [ ] Невалидный int в path → 400
- [ ] Невалидный query-параметр → 400
- [ ] `scope` не из `^(all|patch)$` → 400
- [ ] `limit` вне диапазона → 400
- [ ] POST на GET-эндпоинт → 405
- [ ] Несуществующий путь → 404
- [ ] Ошибки в едином формате `{"detail": "..."}`

## Интеграция с OpenDota

- [ ] При недоступности OpenDota → 5xx / заглушка, приложение не падает
- [ ] Таймаут OpenDota → корректная ошибка
- [ ] Некорректный ответ OpenDota → graceful degradation
- [ ] Rate limit 60 RPS не превышается
- [ ] При превышении лимита → 429 от OpenDota обрабатывается корректно

## Граничные случаи

- [ ] Очень большой `user_id` (2^63-1) → 404
- [ ] Параллельные запросы → корректные ответы
- [ ] Долгий запрос → не блокирует другие

## Что НЕ проверяем в этом чек-листе

- UI-отображение (покрыто в `profile.md`, `users.md`, `stats.md`)
- Детали Steam-авторизации (покрыто в `auth.md`)
- Нагрузочное тестирование (Out of Scope)
- Пагинация (отсутствует)