FROM python:3.14-slim

WORKDIR /dt_to_dd
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]

