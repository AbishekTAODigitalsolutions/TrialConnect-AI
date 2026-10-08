FROM python:3.12-slim

WORKDIR /code

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . ./

CMD ["celery", "-A", "app.worker", "worker", "--loglevel=info"]
