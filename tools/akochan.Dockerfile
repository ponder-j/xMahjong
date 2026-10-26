FROM ubuntu:22.04
RUN sed -i 's|http://archive.ubuntu.com|http://mirrors.aliyun.com|g; s|http://security.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list && apt-get update && apt-get install -y --no-install-recommends g++ make libboost-system-dev git ca-certificates && rm -rf /var/lib/apt/lists/*
ARG AKOCHAN_REF
RUN git clone https://github.com/critter-mj/akochan.git /opt/akochan && cd /opt/akochan && git checkout "$AKOCHAN_REF"
WORKDIR /opt/akochan
RUN make -C ai_src -f Makefile_Linux -j4 && make -f Makefile_Linux -j4
ENV LD_LIBRARY_PATH=/opt/akochan OMP_NUM_THREADS=4
ENTRYPOINT ["./system.exe"]
