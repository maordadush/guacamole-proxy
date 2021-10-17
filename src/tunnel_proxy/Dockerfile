FROM tiangolo/uvicorn-gunicorn-fastapi:python3.7

COPY ./ /app/

RUN pip install pipenv
RUN pipenv install --system  --deploy --ignore-pipfile
