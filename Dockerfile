FROM opendevorg/python-builder as builder

COPY . /tmp/src
RUN assemble

FROM python:slim

COPY --from=builder /output/ /output
RUN /output/install-from-bindep
