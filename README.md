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
```
5. Нажмите **Deploy**.

## Примечания
- Приложение сначала ищет ключ в `st.secrets`, затем в локальном `.env`. Если не находит — показывает поле ввода.
- Ключ хранится локально в `.env`, чтобы не вводить его каждый раз.
