FROM python:3.6-slim

RUN python -m venv /opt/swift-proxy

RUN mkdir -p /opt/swift-proxy-src

COPY . /opt/swift-proxy-src/

RUN PBR_VERSION=1.0.0 /opt/swift-proxy/bin/pip install /opt/swift-proxy-src

EXPOSE 8000

CMD /opt/swift-proxy/bin/gunicorn -k eventlet -t 3600 --workers 10 swift_proxy:proxy
