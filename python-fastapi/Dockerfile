FROM python:3.13-slim
WORKDIR /app/python-fastapi
COPY python-fastapi/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY python-fastapi/app ./app
COPY shared/ /app/shared/
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
