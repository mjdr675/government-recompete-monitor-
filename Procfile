release: python -c "from db import init_db; init_db()"
web: gunicorn app:app --bind 0.0.0.0:$PORT
