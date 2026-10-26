FROM python:3.12-slim-bookworm AS python_base

FROM rust:1.90-bookworm AS build
COPY --from=python_base /usr/local /usr/local
ENV PYO3_PYTHON=/usr/local/bin/python3
ARG MORTAL_REF=0cff2b52982be5b1163aa9a62fb01f03ce91e0d2
RUN git clone https://github.com/Equim-chan/Mortal.git /src/Mortal && cd /src/Mortal && git checkout "$MORTAL_REF"
WORKDIR /src/Mortal
RUN --mount=type=cache,id=xmahjong-mortal-cargo,target=/usr/local/cargo/registry cargo build --locked -p libriichi --lib --release

FROM python_base
ARG TORCH_VERSION=2.9.1
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch==${TORCH_VERSION}" && pip install --no-cache-dir numpy==2.5.4 toml==0.10.2 tqdm==4.70.1 tensorboard==2.21.0
WORKDIR /opt/mortal
COPY --from=build /src/Mortal/mortal/ ./
COPY --from=build /src/Mortal/target/release/libriichi.so ./libriichi.so
COPY --from=build /src/Mortal/LICENSE ./UPSTREAM_LICENSE
ENV MORTAL_CFG=/mnt/config.toml MORTAL_REVIEW_MODE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4
ENTRYPOINT ["python", "mortal.py"]
