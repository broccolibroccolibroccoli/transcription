FROM python:3.11.18-bookworm

# mcr.microsoft.com/devcontainers/python:1-3.11-bookworm は
# eMudhra 中間CA対策（Python 3.11.18 / CVE-2026-115557）より前の
# Python のままなので、公式の修正版イメージを使う。
# updateContentCommand が sudo と apt を呼ぶ。
RUN apt-get update \
    && apt-get install -y --no-install-recommends sudo ca-certificates \
    && rm -rf /var/lib/apt/lists/*
