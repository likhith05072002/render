FROM node:20-bullseye AS frontend-builder

WORKDIR /app/ui
COPY ui/package*.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend-builder /app/ui/dist /app/ui/dist

EXPOSE 5000

CMD ["gunicorn", "ui.app:app", "--bind", "0.0.0.0:5000", "--timeout", "180"]
