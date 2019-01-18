FROM opendevorg/python-builder as builder

COPY . /tmp/src
ENV ASSEMBLE_HOOK /tmp/src/tools/docker-install-js-tools.sh
RUN assemble

FROM python:slim

COPY --from=builder /output/ /output
RUN /output/install-from-bindep
