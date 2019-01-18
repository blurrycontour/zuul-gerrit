FROM opendevorg/bindep as builder

COPY . /tmp/src
RUN assemble

FROM python:slim

COPY --from=builder /output/ /output
COPY --from=builder /usr/local/bin/install-from-bindep /usr/local/bin
RUN install-from-bindep
