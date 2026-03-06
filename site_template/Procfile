web: python manage.py migrate && python manage.py collectstatic --noinput && gunicorn config.wsgi:application -c gunicorn.conf.py --bind 0.0.0.0:$PORT
