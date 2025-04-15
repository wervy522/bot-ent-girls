# Entourage Girls Bot 💖

Telegram-бот для воронки клуба Entourage Girls.

## 📋 Возможности

- Отправляет анкету
- Напоминает, если не заполнена
- Проверяет Google Таблицу
- Отправляет приглашение и ссылку на оплату
- Работает с Railway

## 🚀 Запуск

1. Склонируй репозиторий
2. Добавь `.env` на основе `.env.example`
3. Загрузи `credentials.json` (ключ от Google API)
4. Установи зависимости:
```
pip install -r requirements.txt
```
5. Запусти:
```
python bot.py
```

## 🌍 Деплой на Railway

1. Залей проект на GitHub
2. Подключи на https://railway.app
3. Укажи переменные из `.env`
4. Загрузи `credentials.json` в "Files"