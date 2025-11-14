# Python Restful Framework

---------------------

## Installation

This project was built on Ubuntu 22.04.5 LTS and has been successfully tested under Python 3.10 and Python 3.11.

* Download source code:

```shell
git clone https://github.com/ferry2174/restful_server.git
```

* It is recommended to create a Python virtual environment with version 3.11 and then install it from the source package.

```shell
cd restful_server
pip install -e .
```

After installing with pip, the start stop script of the service will be installed in the environment variables of the current Python environment.

## Manage Services

### Restful Server

```shell
start_restful_server.sh dev   # start server

stop_restful_server.sh     # stop server
```

* Open your browser and enter` http://127.0.0.1:8090/restful_server `If you see the `Welcome to Python Restful Template Project!` This indicates that the service has been successfully started.
* Input` http://127.0.0.1:8091/metrics `If the corresponding monitoring parameter output is seen, it indicates that the monitoring output service has been successfully started.

### Metrics Server

The monitoring service is built using Prometheus and Grafana, and installed using Docker Composer.

The Docker compose file can be found in the `src/restful_derver/assets/metrics` directory of the project directory. First, you need to install the Docker service locally.

```shell
cd src/restful_derver/assets/metrics
docker compose up  # start monitoring service

docker compose down   # stop monitoring service
```

Enter in the browser` http://127.0.0.1:3000/ `If you see the Grafana service page, it means the service has started successfully. The default administrator account password is `admin/admin`

The `src/destful_derver/assets/metrics/data_Service _monitor-1763097717086.json` file is a dashboard example that you can import into Grafana to see the basic API monitoring chart.

## Try The API

This is an example project where all business code has been removed. You can check the availability of the service by accessing the link below:

* <http://127.0.0.1:8090/restful_server/docs>: API document
* <http://127.0.0.1:8090/restful_server/example/mariadb/version>: If you have an available Mariadb or MySQL service locally and have configured it to be available in `src/destful_derver/config/config_dev.yaml`, you can view the service status and version through this URL

## Service Log

After the service is started, a cache directory will be created in your local `${HOME}/Program/destful_derver/`, and log files will be created in the ` logs ` directory.
After you have completed the test, you can delete it at any time.
