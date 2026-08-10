FROM python:3.12-slim

RUN pip install --no-cache-dir mcp-server-datahub==0.6.0

ENV FASTMCP_HOST=0.0.0.0 \
    FASTMCP_PORT=8000 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=6 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["mcp-server-datahub", "--transport", "http"]
