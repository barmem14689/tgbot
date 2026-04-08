# Telegram VPN payment bot

Бот принимает скриншоты оплат, отправляет их двум администраторам на подтверждение и после подтверждения создает или продлевает клиента в X-UI.

## Что реализовано

- Выбор периода подписки через inline-кнопки.
- Отправка скриншота оплаты.
- Модерация заявки двумя администраторами (approve/reject) через inline-кнопки.
- Интеграция с X-UI API:
  - создание клиента;
  - попытка продления существующего клиента;
  - fallback на удаление+пересоздание с тем же UUID, чтобы ключ не менялся.
- Логика продления:
  - если пользователь продляет в пределах `GRACE_PERIOD_DAYS` после окончания подписки - используется старый ключ;
  - если прошло больше - старый клиент удаляется, при оплате создается новый ключ.
- Фоновая очистка: после истечения grace-периода ключ автоматически удаляется в X-UI.
- Хранение данных в SQLite (`users`, `payments`, `admin_messages`).

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Настройка

1. Скопируйте `.env.example` в `.env`.
2. Заполните все переменные:
   - `BOT_TOKEN`
   - `ADMIN_IDS` (через запятую)
   - данные X-UI (`XUI_*`)
   - `KEY_TEMPLATE`, `VPN_HOST`, `VPN_PORT`

> Важно: у разных сборок X-UI могут отличаться API endpoints и payload. В `.env` для этого вынесены `XUI_*_ENDPOINT`.

## Где брать значения для `.env` (x-ui-pro)

- `BOT_TOKEN`: у `@BotFather` -> `/newbot` -> токен вида `123456:ABC...`.
- `ADMIN_IDS`: напишите любому боту `@userinfobot` или `@RawDataBot`, получите ваш Telegram ID; внесите два ID через запятую.
- `XUI_BASE_URL`: домен панели, по которому открываете web-панель x-ui-pro, например `https://panel.example.com`.
- `XUI_USERNAME` / `XUI_PASSWORD`: логин/пароль администратора панели (те же, что для входа в web-интерфейс).
- `XUI_INBOUND_ID`: в панели `Inbounds` откройте нужный inbound и возьмите его `ID` (число, например `1`).
- `VPN_HOST`: хост, который будет внутри ключа (обычно тот же домен, что у inbound/реверс-прокси).
- `VPN_PORT`: порт подключения клиента (чаще всего `443`).
- `KEY_TEMPLATE`: формат ссылки, которую получает пользователь. Если не уверены, оставьте дефолт и потом подгоните под ваш transport/security.
- `SUBSCRIPTION_PERIODS`: список кнопок в днях, например `30,90,180,365`.
- `GRACE_PERIOD_DAYS`: у вас по ТЗ `3`.

### По API endpoint'ам для x-ui-pro

- Обычно работает:
  - `XUI_LOGIN_ENDPOINT=/login`
  - `XUI_ADD_CLIENT_ENDPOINT=/panel/api/inbounds/addClient`
  - `XUI_UPDATE_CLIENT_ENDPOINT=/panel/api/inbounds/updateClient/{client_id}`
  - `XUI_DELETE_CLIENT_ENDPOINT=/panel/api/inbounds/delClient/{client_id}`
- В некоторых сборках `delete` может быть в формате `/panel/api/inbounds/{inbound_id}/delClient/{client_id}`.
- Бот уже умеет fallback между распространенными вариантами `update/delete`, поэтому чаще всего ручная правка не нужна.

## Запуск

```bash
python main.py
```
