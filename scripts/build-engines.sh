#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
docker build -f tools/convlog/Dockerfile -t xmahjong/convlog:local .
docker build -f tools/akochan.Dockerfile --build-arg AKOCHAN_REF=53188a0b926fbab38177f88c3cd87d554cf412af -t xmahjong/akochan:local .
if [ ! -f config.local.json ]; then cp config.example.json config.local.json; fi
