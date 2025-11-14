#!/bin/bash

export APP_ENV=$1

APP_HOME=~/Program/restful_server

export PROMETHEUS_MULTIPROC_DIR=$APP_HOME/metrics_dir

mkdir -p $PROMETHEUS_MULTIPROC_DIR
rm -rf $PROMETHEUS_MULTIPROC_DIR/*.db

exec gunicorn -c $(python -c "import restful_server; print(restful_server.GUNICORN_CONF_PATH)") restful_server.backend.main:app
