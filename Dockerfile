FROM python:3.13.2

WORKDIR /dt_to_dd
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]

