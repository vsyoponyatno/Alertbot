# RSIA Alert Bot

Бот состоит из двух процессов. Аккаунт на основе **pyrogram** следит за каналами и отправляет найденные сообщения через HTTP на локальный бот. Aiogram-бот получает эти POST-запросы и пересылает их в целевой чат, а также предоставляет меню управления.

## Быстрый старт

1. Скопируйте репозиторий на сервер, например `/opt/news_monitor/`.
2. Создайте файл `.env` со следующими переменными:
   ```
   API_ID=26184709
   API_HASH=f6cc16fcdfadbebc6b91cd8cf7f2b375
   SESSION_NAME=RSIbot
   TARGET_CHAT_ID=7570803881
   BOT_TOKEN=7316010696:AAE4BWizJsEUZ3uIcKQbZmx51sdefSYnt7o
   ALERT_URL=http://localhost:8081/alert
   ```
3. Установите зависимости: `pip install -r requirements.txt`.
4. Создайте файл сессии для аккаунта:
   `python auth_session.py` (следует ввести код подтверждения).
5. Запустите `bash run.sh` (скрипт сперва стартует бот, делает короткую паузу и
   затем запускает watcher) или установите юниты systemd из каталога проекта.

### Автозапуск через systemd

Скопируйте файлы `newsbot.service` и `watcher.service` в `/etc/systemd/system/`.
`watcher.service` зависит от `newsbot.service`, поэтому бот будет запущен
раньше watcher:

```bash
sudo cp newsbot.service watcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable newsbot.service watcher.service
sudo systemctl start newsbot.service watcher.service
```
`watcher.service` делает небольшую паузу перед стартом watcher, чтобы HTTP-сервер бота успел запуститься.

Логи можно смотреть через `journalctl -u newsbot -f` и `journalctl -u watcher -f`.

Команда `/reload` перечитывает файлы `channels.json` и `keywords.yaml` без перезапуска процессов.

Файлы `shared/channels.json` и `shared/keywords.yaml` должны существовать. В них хранятся список отслеживаемых каналов и ключевые слова.
