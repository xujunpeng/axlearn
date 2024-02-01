# syntax=docker/dockerfile:1

ARG TARGET=base
ARG BASE_IMAGE=python:3.9-slim

FROM ${BASE_IMAGE} AS base

RUN apt-get update
RUN apt-get install -y apt-transport-https ca-certificates gnupg curl gcc g++

# Install git.
RUN apt-get install -y git

# Install gcloud. https://cloud.google.com/sdk/docs/install
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key --keyring /usr/share/keyrings/cloud.google.gpg add - && \
    apt-get update -y && apt-get install google-cloud-cli -y

# Install screen and other utils for launch script.
RUN apt-get install -y jq screen ca-certificates

# Setup.
RUN mkdir -p /root
WORKDIR /root
# Introduce the minimum set of files for install.
COPY README.md README.md
COPY pyproject.toml pyproject.toml
RUN mkdir axlearn && touch axlearn/__init__.py
# Setup venv to suppress pip warnings.
ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
# Install dependencies.
RUN pip install flit
RUN pip install --upgrade pip


################################################################################
# Final target spec.                                                           #
################################################################################

FROM ${TARGET} AS final
