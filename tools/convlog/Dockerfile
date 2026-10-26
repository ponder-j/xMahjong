FROM rust:1.90-bookworm AS build
WORKDIR /build
COPY vendor/convlog vendor/convlog
COPY tools/convlog tools/convlog
RUN cargo build --locked --release --manifest-path tools/convlog/Cargo.toml
FROM debian:bookworm-slim
COPY --from=build /build/tools/convlog/target/release/xmahjong-convlog /usr/local/bin/xmahjong-convlog
ENTRYPOINT ["xmahjong-convlog"]
