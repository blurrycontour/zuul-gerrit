FROM python:2.7 AS base

ENV VIRTUAL_ENV=/opt/venv
RUN virtualenv /opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:$PATH"

RUN pip install ansible dumb-init

# ----- zuul_console -----

FROM base AS zuul_console

COPY zuul_console.py .
COPY zuul_console-args.json .
COPY console-1234abc.log /tmp

ENTRYPOINT ["dumb-init", "--"]
CMD ["sh", "-c", "python zuul_console.py args.json && sleep infinity"]

# ----- 2.8 command -----

FROM base as command_2.8

COPY command_2.8.py .
COPY command-args.json .

ENTRYPOINT ["dumb-init", "--"]
CMD ["sh", "-c", "python command_2.8.py args.json && sleep infinity"]

# ----- 2.9 command -----

FROM base as command_2.9

COPY command_2.9.py .
COPY command-args.json .

ENTRYPOINT ["dumb-init", "--"]
CMD ["sh", "-c", "python command_2.9.py args.json && sleep infinity"]

# ----- 5 command -----

FROM base as command_5

COPY command_5.py .
COPY command-args.json .

ENTRYPOINT ["dumb-init", "--"]
CMD ["sh", "-c", "python command_5.py args.json && sleep infinity"]
