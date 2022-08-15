FROM python:2.7

ENV VIRTUAL_ENV=/opt/venv
RUN virtualenv /opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:$PATH"

RUN pip install ansible dumb-init

COPY zuul_console.py .
COPY args.json .

ENTRYPOINT ["dumb-init", "--"]
CMD ["sh", "-c", "python zuul_console.py args.json && sleep infinity"]
