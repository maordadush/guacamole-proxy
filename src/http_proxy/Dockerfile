FROM tiangolo/uvicorn-gunicorn-fastapi:python3.7

COPY config.py /app/
COPY http_proxy/* /app/

RUN pip install pipenv
RUN pipenv install --system  --deploy --ignore-pipfile
