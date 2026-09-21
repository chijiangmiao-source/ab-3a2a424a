FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# 不额外安装 curl：用标准库做健康检查
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=12 \
  CMD python -c "import json,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3); d=json.load(r); assert d.get('status')=='ok'" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
