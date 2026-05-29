# TradingView Webhook Signal Bot

Основной режим: TradingView Webhook (`/webhook`).
Резервный режим: WebSocket (только рыночные данные для фильтра качества).

## Важное

- Бот не открывает сделки и не управляет аккаунтом.
- Бот только отправляет информационные сигналы в Telegram.

## Команды

- `/stats` - статистика.
- `/pairs` - лидеры пар.
- `/active` - активный сигнал.
- `/last` - последние сигналы.
- `/debug` - диагностика состояния.

## Inline меню

- 📊 Статистика
- 📈 Активный сигнал
- 📜 Последние сигналы
- ⚙ Настройки

## TradingView webhook

Endpoint:

- `POST /webhook`

Payload:

```json
{
  "pair": "BTCUSD",
  "direction": "UP",
  "price": "73145",
  "strength": "8",
  "time": "{{time}}"
}
```

Health endpoint:

- `GET /health`

## HTTPS на VPS

Webhook должен быть доступен по HTTPS через reverse proxy (например, Nginx + Let's Encrypt):

- Nginx принимает `https://MY_DOMAIN/webhook`
- проксирует на `http://127.0.0.1:8088/webhook`

## systemd

Файл сервиса:

- `deploy/systemd/tradingview-signal-bot.service`

Команды:

```bash
sudo cp deploy/systemd/tradingview-signal-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tradingview-signal-bot
sudo systemctl start tradingview-signal-bot
sudo systemctl status tradingview-signal-bot
```

## Production deploy

Ниже приведен полный runbook для Ubuntu VPS (стабильный запуск без открытого терминала).

1. Обновить систему и поставить зависимости (Ubuntu 22.04 и 24.04):

```bash
sudo apt update
sudo apt -y upgrade
sudo apt -y install software-properties-common curl ca-certificates gnupg lsb-release git nginx ufw

# Python 3.12: на 24.04 обычно уже доступен в стандартных репозиториях,
# на 22.04 чаще нужен deadsnakes.
if ! apt-cache policy python3.12 | grep -q Candidate:; then
  sudo add-apt-repository ppa:deadsnakes/ppa -y
  sudo apt update
fi

sudo apt -y install python3.12 python3.12-venv python3.12-dev certbot python3-certbot-nginx
```

2. Создать системного пользователя и каталог проекта:

```bash
sudo useradd --system --create-home --home /opt/tradingview-signal-bot --shell /usr/sbin/nologin tvbot || true
sudo mkdir -p /opt/tradingview-signal-bot
sudo chown -R tvbot:tvbot /opt/tradingview-signal-bot
```

3. Залить код проекта:

```bash
sudo -u tvbot git clone https://github.com/FanTom6699/Naslediye.git /opt/tradingview-signal-bot
cd /opt/tradingview-signal-bot
```

Если репозиторий уже есть:

```bash
cd /opt/tradingview-signal-bot
sudo -u tvbot git pull
```

4. Создать virtualenv и установить зависимости:

```bash
cd /opt/tradingview-signal-bot
sudo -u tvbot python3.12 -m venv .venv
sudo -u tvbot /opt/tradingview-signal-bot/.venv/bin/python -m pip install --upgrade pip
sudo -u tvbot /opt/tradingview-signal-bot/.venv/bin/pip install -r requirements.txt
```

5. Настроить .env:

```bash
cd /opt/tradingview-signal-bot
sudo -u tvbot cp .env .env.backup.$(date +%F-%H%M%S) 2>/dev/null || true
sudo -u tvbot nano /opt/tradingview-signal-bot/.env
sudo chown tvbot:tvbot /opt/tradingview-signal-bot/.env
sudo chmod 600 /opt/tradingview-signal-bot/.env

# Права на рабочие данные
sudo mkdir -p /opt/tradingview-signal-bot/database
sudo chown -R tvbot:tvbot /opt/tradingview-signal-bot/database
sudo chmod 700 /opt/tradingview-signal-bot/database
```

Минимально проверьте:

- BOT_TOKEN
- WEBHOOK_HOST=127.0.0.1
- WEBHOOK_PORT=8088
- WEBHOOK_SECRET=<случайная строка>
- TV_ALLOWED_PAIRS=EURUSD,GBPUSD,USDJPY,AUDUSD,EURJPY,BTCUSD
- ACTIVE_HOURS_START / ACTIVE_HOURS_END
- SIGNAL_COOLDOWN_SECONDS

6. Быстрый локальный smoke-test на VPS:

```bash
cd /opt/tradingview-signal-bot
sudo -u tvbot /opt/tradingview-signal-bot/.venv/bin/python bot.py
```

Остановить Ctrl+C после проверки старта.

7. Подключить systemd:

```bash
sudo cp /opt/tradingview-signal-bot/deploy/systemd/tradingview-signal-bot.service /etc/systemd/system/tradingview-signal-bot.service
sudo systemctl daemon-reload
sudo systemctl enable tradingview-signal-bot
sudo systemctl start tradingview-signal-bot
```

8. Команды управления сервисом:

```bash
sudo systemctl status tradingview-signal-bot
sudo systemctl restart tradingview-signal-bot
sudo journalctl -u tradingview-signal-bot -f
```

Дополнительно после редактирования unit-файла:

```bash
sudo systemctl daemon-reload
sudo systemctl restart tradingview-signal-bot
```

9. Nginx reverse proxy для публичного webhook:

Создайте файл /etc/nginx/sites-available/tradingview-signal-bot:

```nginx
server {
    listen 80;
    listen [::]:80;
  server_name MY_DOMAIN;

  location ~ /\. {
    deny all;
    access_log off;
    log_not_found off;
  }

    location /webhook {
        proxy_pass http://127.0.0.1:8088/webhook;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 10s;
        proxy_read_timeout 30s;
    }

    location /health {
        proxy_pass http://127.0.0.1:8088/health;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Активируйте конфиг:

```bash
sudo ln -sf /etc/nginx/sites-available/tradingview-signal-bot /etc/nginx/sites-enabled/tradingview-signal-bot
sudo nginx -t
sudo systemctl reload nginx
```

10. Firewall (UFW):

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

11. Certbot HTTPS:

```bash
sudo certbot --nginx -d MY_DOMAIN
```

Проверка автообновления сертификатов:

```bash
sudo systemctl status certbot.timer
sudo certbot renew --dry-run
```

12. Проверка webhook вручную через curl:

Проверка health-заголовков:

```bash
curl -I https://MY_DOMAIN/health
```

Проверка webhook POST:

```bash
curl -X POST https://MY_DOMAIN/webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: YOUR_WEBHOOK_SECRET" \
  -d '{"pair":"EURUSD","direction":"UP","price":"1.08500","strength":"9","time":"test"}'
```

Ожидается:

- API отвечает JSON с accepted=true или queued=true
- сигнал приходит в Telegram
- команда /active показывает активный сигнал
- после экспирации приходит WIN или LOSS или DRAW

13. TradingView alert payload:

LONG:

```json
{
  "pair": "{{ticker}}",
  "direction": "UP",
  "price": "{{close}}",
  "strength": "8",
  "time": "{{time}}"
}
```

SHORT:

```json
{
  "pair": "{{ticker}}",
  "direction": "DOWN",
  "price": "{{close}}",
  "strength": "8",
  "time": "{{time}}"
}
```

Webhook URL для TradingView:

- `https://MY_DOMAIN/webhook`

14. Проверки после деплоя:

```bash
curl -s https://MY_DOMAIN/health
sudo systemctl status tradingview-signal-bot
sudo journalctl -u tradingview-signal-bot -n 100 --no-pager
```

15. Обновление кода в проде:

```bash
cd /opt/tradingview-signal-bot
sudo -u tvbot git pull
sudo -u tvbot bash -lc 'cd /opt/tradingview-signal-bot && source .venv/bin/activate && pip install -r requirements.txt'
sudo systemctl restart tradingview-signal-bot
sudo systemctl status tradingview-signal-bot
```

16. Безопасность и быстрый self-check:

```bash
# .env должен быть доступен только владельцу
sudo ls -l /opt/tradingview-signal-bot/.env

# Проверка активного nginx-конфига и запрета доступа к dotfiles
sudo nginx -t
curl -I https://MY_DOMAIN/.env

# Проверка локального приложения (без nginx)
curl -s http://127.0.0.1:8088/health
```

## How to test

1. Запустить бота в чистом терминале:

```powershell
python bot.py
```

Для детерминированного локального e2e-теста можно запустить так:

```powershell
$env:MOCK_DATA='true'
$env:MOCK_SYMBOLS='EURUSD_OTC'
$env:EXPIRATION_SECONDS='8'
$env:SIGNAL_COOLDOWN_SECONDS='20'
$env:SIGNAL_BATCH_WINDOW_SECONDS='2'
python bot.py
```

Если терминал случайно находится в Python REPL (видите `>>>`), выйдите:

```python
exit()
```

И откройте новый терминал PowerShell для чистого запуска.

2. Проверить health:

```powershell
curl http://127.0.0.1:8088/health
```

Ожидаются поля:

- webhook_status
- database_status
- websocket_status
- bot_status

3. Отправить тестовый webhook вручную:

```powershell
curl -Method Post http://127.0.0.1:8088/webhook `
  -ContentType "application/json" `
  -Body '{"pair":"EURUSD","direction":"UP","price":"1.2000","strength":"9","time":"manual"}'
```

4. Запустить e2e сценарии:

```powershell
python test_webhook.py --base-url http://127.0.0.1:8088 --db-path database/market.db --batch-window 2 --expiration 12
```

Скрипт проверяет:

- single LONG / SHORT
- batch 3 signals -> один победитель
- low-strength reject
- active signal lock
- cooldown duplicate
- outside active hours (soft-check)
- WIN / LOSS / DRAW на экспирации
- smoke для текстов статистики

Чтобы проверить outside_active_hours строго, запустите бота вне текущего окна времени, например:

```powershell
$env:ACTIVE_HOURS_START='23'
$env:ACTIVE_HOURS_END='1'
python bot.py
```

5. Проверить Telegram-команды:

- `/stats`
- `/pairs`
- `/active`
- `/last`
- `/debug`

Они должны отвечать без падений даже на пустой статистике.

6. Настроить TradingView webhook URL:

- локально (для теста): `http://127.0.0.1:8088/webhook`
- на VPS через HTTPS: `https://MY_DOMAIN/webhook`

Рекомендуется использовать reverse proxy (Nginx) и TLS сертификат.
