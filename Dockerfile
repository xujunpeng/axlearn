# syntax=docker/dockerfile:1

ARG TARGET=base
ARG BASE_IMAGE=python:3.9-slim

FROM ${BASE_IMAGE} AS base

RUN apt-get update
RUN apt-get install -y apt-transport-https ca-certificates gnupg curl gcc g++

