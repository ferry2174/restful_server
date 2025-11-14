APP_HOME=~/Program/restful_server

export PROMETHEUS_MULTIPROC_DIR=$APP_HOME/metrics_dir

mkdir -p $PROMETHEUS_MULTIPROC_DIR
rm -rf $PROMETHEUS_MULTIPROC_DIR/*.db

kill -HUP $(cat ~/Program/restful_server/.app_pid)
