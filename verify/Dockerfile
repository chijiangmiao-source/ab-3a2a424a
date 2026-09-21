FROM python:3.11-slim
WORKDIR /verify
COPY verify.py .
# 一次性服务：运行验收并以退出码报告结果
CMD ["python", "-u", "verify.py"]
