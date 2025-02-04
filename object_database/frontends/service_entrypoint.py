#!/usr/bin/env python3

#   Copyright 2017-2019 object_database Authors
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import argparse
import logging
import signal
import sys

from object_database import connect
from object_database.util import validateLogLevel, configureLogging
from object_database.service_manager.Codebase import setCodebaseInstantiationDirectory
from object_database.service_manager.ServiceWorker import ServiceWorker
from object_database.service_manager.logfiles import Logfile


def main(argv):
    parser = argparse.ArgumentParser("Run a specific service.")

    parser.add_argument("servicename")
    parser.add_argument("host")
    parser.add_argument("port", type=int)
    parser.add_argument("instanceid", type=int)
    parser.add_argument("sourceDir")
    parser.add_argument("storageRoot")
    parser.add_argument("authToken")
    parser.add_argument("--log-level", required=False, default="INFO")
    parser.add_argument("--log-path", required=False, default=None)
    parser.add_argument("--log-max-megabytes", required=False, default=0)
    parser.add_argument("--log-backup-count", required=False, default=0)
    parser.add_argument("--ip", required=False)

    parsedArgs = parser.parse_args(argv[1:])

    level = parsedArgs.log_level.upper()
    level = validateLogLevel(level, fallback="INFO")

    if parsedArgs.log_path:
        if Logfile.parseLogfileName(parsedArgs.log_path) is None:
            raise ValueError(f"Log Path not parseable: {parsedArgs.log_path}")

        updates = {
            "handlers": {
                "rotating-file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": parsedArgs.log_path,
                    "level": 0,  # this handler should apply to all levels
                    "formatter": "nyc",
                    "maxBytes": int(float(parsedArgs.log_max_megabytes) * 1024 ** 2),
                    "backupCount": int(parsedArgs.log_backup_count),
                }
            },
            "root": {"handlers": ["default", "rotating-file"]},
        }

    else:
        updates = {}

    configureLogging(preamble=str(parsedArgs.instanceid), level=level, config_updates=updates)

    logger = logging.getLogger(__name__)

    logger.info(
        "service_entrypoint.py connecting to %s:%s for %s",
        parsedArgs.host,
        parsedArgs.port,
        parsedArgs.instanceid,
    )

    setCodebaseInstantiationDirectory(parsedArgs.sourceDir)

    try:

        def dbConnectionFactory():
            return connect(parsedArgs.host, parsedArgs.port, parsedArgs.authToken)

        mainDbConnection = dbConnectionFactory()

        if parsedArgs.ip is not None:
            logger.info("Our ip explicitly specified as %s", parsedArgs.ip)
            ourIP = parsedArgs.ip
        else:
            ourIP = mainDbConnection.getConnectionMetadata()["sockname"][0]
            logger.info("Our ip inferred from our connection back to the server as %s", ourIP)

        manager = ServiceWorker(
            mainDbConnection,
            dbConnectionFactory,
            int(parsedArgs.instanceid),
            parsedArgs.storageRoot,
            parsedArgs.authToken,
            ourIP,
            ownsProcess=True,
        )

        def shutdownCleanly(signalNumber, frame):
            logger.info("Received signal %s. Stopping.", signalNumber)
            manager.stop()

        signal.signal(signal.SIGINT, shutdownCleanly)
        signal.signal(signal.SIGTERM, shutdownCleanly)

        exitedGracefully = manager.runAndWaitForShutdown()
        retval = 0 if exitedGracefully else 1
        return retval

    except Exception:
        logger.exception("service_entrypoint failed with an exception:")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
