FROM opendevorg/python-builder as builder

COPY . /tmp/src
ENV ASSEMBLE_HOOK /tmp/src/tools/install-js-tools.sh
ENV INSTALL_JS_TOOLS_SUDO_CMD ""
RUN assemble

FROM python:slim

COPY --from=builder /output/ /output
RUN /output/install-from-bindep
