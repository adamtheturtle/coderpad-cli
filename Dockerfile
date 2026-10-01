FROM python:3.13-slim AS build
LABEL org.opencontainers.image.source="https://github.com/adamtheturtle/coderpad-cli"
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /bin/uv
WORKDIR /build
COPY . .
ARG CODERPAD_CLI_VERSION=0.0.0
RUN SETUPTOOLS_SCM_PRETEND_VERSION_FOR_CODERPAD_CLI=$CODERPAD_CLI_VERSION uv build --wheel --out-dir /wheels

FROM python:3.13-slim
LABEL org.opencontainers.image.source="https://github.com/adamtheturtle/coderpad-cli"
LABEL org.opencontainers.image.description="Upload CoderPad question starter code"
LABEL org.opencontainers.image.licenses="MIT"
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
ENTRYPOINT ["coderpad"]
