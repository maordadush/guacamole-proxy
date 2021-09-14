FROM tiangolo/uvicorn-gunicorn-fastapi:python3.7

COPY config.py /app/
COPY ws_proxy/* /app/

RUN pip install pipenv
RUN pipenv install --system  --deploy --ignore-pipfile
