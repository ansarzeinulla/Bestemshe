# Build stage: compile the mmap query CLI
FROM debian:bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends g++ make libzstd-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY query.cpp Oracle.h StateIndex.h BestemsheCore.h ./
RUN g++ -std=c++17 -O3 -DNDEBUG query.cpp -o query -lzstd

# Runtime stage: Gradio app + tablebase
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends libzstd1 && rm -rf /var/lib/apt/lists/*

# HF Spaces requires a non-root user
RUN useradd -m -u 1000 user
USER user
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
ENV PATH="/home/user/.local/bin:$PATH"

COPY --chown=user --from=build /src/query ./query
COPY --chown=user app.py .
COPY --chown=user layers/compressed ./layers/compressed

ENV BESTEMSHE_DATA_DIR=layers/compressed
EXPOSE 7860
CMD ["python", "app.py"]
