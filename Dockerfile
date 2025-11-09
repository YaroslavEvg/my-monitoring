FROM python:3.12.0-alpine3.18

ENV TZ=Europe/Moscow

RUN apk --no-cache add tzdata \
  && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
  && echo $TZ > /etc/timezone

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python3.12", "main.py"]
