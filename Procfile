web: gunicorn app:app --bind 0.0.0.0:$PORT
worker: celery -A tasks worker --loglevel=info
beat: celery -A tasks beat --loglevel=info --scheduler celery.beat.PersistentScheduler
