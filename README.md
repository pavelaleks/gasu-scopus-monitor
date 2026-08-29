# Scopus Monitor (ГАГУ)

Streamlit-приложение для мониторинга публикаций в Scopus для проректора по науке ГАГУ.

## Быстрый старт (Windows через .bat)
1. Установите Python 3.10+.
2. Дважды кликните `run_app.bat`.
3. Откройте ссылку, которую покажет терминал (обычно `http://localhost:8501`).
4. Введите API-ключ Scopus в боковой панели и нажмите «Сохранить ключ».

## Ручной запуск (любая ОС)
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Где взять API-ключ Scopus
1. Зарегистрируйтесь на [Elsevier Developer Portal](https://dev.elsevier.com/).
2. Создайте ключ для **Scopus Search API**.

## Деплой в Streamlit Cloud за 5 минут
1. Создайте репозиторий на GitHub и загрузите файлы `app.py`, `requirements.txt`, `README.md`.
2. Перейдите на [Streamlit Cloud](https://streamlit.io/cloud) и нажмите **New app**.
3. Выберите репозиторий, ветку и файл `app.py`.
4. В разделе **Advanced settings → Secrets** добавьте:
```
SCOPUS_API_KEY = "ваш_ключ"
APP_PASSWORD = "12345"
```
5. Нажмите **Deploy**.

Без `SCOPUS_API_KEY` в Secrets ключ придётся вводить снова после каждого перезапуска Cloud. Пароль `12345` задан и в коде (на случай, если `APP_PASSWORD` ещё не добавлен); в Secrets его можно сменить без правки программы.

После входа можно включить «Запомнить в этом браузере» — повторно пароль не спросят около 30 дней.

## Чтобы приложение в Cloud не засыпало

Streamlit Community Cloud усыпляет приложение примерно через **12 часов без визитов**. Пустые коммиты в git для этого не подходят: они засоряют историю, каждый раз пересобирают приложение и больше не считаются активностью.

В репозитории стоит GitHub Action: раз в 6 часов headless-браузер открывает [gasu-scopus-monitor.streamlit.app](https://gasu-scopus-monitor.streamlit.app) и при необходимости нажимает «Yes, get this app back up!». Запуск вручную: вкладка Actions → **Keep Streamlit Alive** → **Run workflow**.

Другой URL можно задать переменной репозитория `STREAMLIT_APP_URL` (Settings → Secrets and variables → Actions → Variables).

## Примечания
- Приложение сначала ищет ключ в `st.secrets`, затем в локальном `.env`. Если не находит — показывает поле ввода.
- Ключ хранится локально в `.env`, чтобы не вводить его каждый раз.
