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

import collections
import collections.abc
import copy
import hashlib
import logging
import logging.config
import os
import random
import ssl
import subprocess
import tempfile
import time
import types


def formatTable(rows):
    rows = [[str(r) for r in row] for row in rows]

    cols = [[r[i] for r in rows] for i in range(len(rows[0]))]
    colWidth = [max([len(c) for c in col]) for col in cols]

    formattedRows = [
        "  ".join(row[col] + " " * (colWidth[col] - len(row[col])) for col in range(len(cols)))
        for row in rows
    ]
    formattedRows = (
        formattedRows[:1]
        + ["  ".join("-" * colWidth[col] for col in range(len(cols)))]
        + formattedRows[1:]
    )

    return "\n".join(formattedRows)


def recursiveUpdate(dictionary, updates):
    for k, v in updates.items():
        if isinstance(v, collections.abc.Mapping):
            dictionary[k] = recursiveUpdate(dictionary.get(k, {}), v)
        else:
            dictionary[k] = v
    return dictionary


def getFormatter(logger):
    """ Given a logger, get its default formatter or None. """
    if logger is None:
        return None

    if not logger.hasHandlers():
        return None

    if len(logger.handlers) == 0:
        return getFormatter(logger.parent)

    return logger.handlers[0].formatter


def logFormat(preamble=""):
    midpart = f"{preamble} | " if preamble else ""
    return (
        "[%(asctime)s] %(levelname)8s %(filename)30s:%(lineno)4s | "
        + midpart
        + "%(threadName)10s | %(message)s"
    )


DEFAULT_LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "[%(asctime)s] %(levelname)8s %(filename)30s:%(lineno)4s | %(message)s"
        },
        "nyc": {
            "()": "object_database.logging.TimezonedFormatter",
            "timezone": "America/New_York",
            "fmt": "[%(asctime)s] %(levelname)8s %(filename)30s:%(lineno)4s | %(message)s",
        },
    },
    "handlers": {
        "default": {
            "class": "logging.StreamHandler",
            "level": 0,  # Default Handler should apply to all levels
            "formatter": "nyc",
            "stream": "ext://sys.stdout",
        }
    },
    "root": {"level": logging.INFO, "handlers": ["default"]},
}


def setupLogging(config=None, default_level=None, default_format=None, updates=None):
    """Setup logging configuration """
    if config is None:
        config = copy.deepcopy(DEFAULT_LOGGING_CONFIG)

    if updates is None:
        updates = {}

    if default_level:
        if not isinstance(default_level, int):
            raise TypeError(f"Expected int for default_level but got {default_level}.")

        updates.setdefault("root", {})["level"] = default_level

    if updates:
        recursiveUpdate(config, updates)

    # propagate default_format to all configured formatters
    if default_format:
        for name, formatConfig in config.setdefault("formatters", {}).items():
            if "()" in formatConfig:
                formatConfig["fmt"] = default_format

            else:
                formatConfig["format"] = default_format

        if len(config["formatters"]) == 0:
            config["formatters"] = dict(default=dict(format=default_format))

    logging.config.dictConfig(config)


def configureLogging(preamble="", level=logging.INFO, config_updates=None):
    if not isinstance(level, int):
        # getLevelName returns a name when given an int and an int when given a name,
        # and there doesn't seem to be an other way to get the int from the string.
        level = logging.getLevelName(level)

        if not isinstance(level, int):
            raise ValueError(f"Invalid logging level: {level}")

    frmt = logFormat(preamble)

    setupLogging(default_level=level, default_format=frmt, updates=config_updates)

    logging.getLogger("botocore.vendored.requests.packages.urllib3.connectionpool").setLevel(
        logging.CRITICAL
    )
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)


def secondsToHumanReadable(seconds):
    if seconds < 120:
        return "%.2f seconds" % (seconds)
    if seconds < 120 * 60:
        return "%.2f minutes" % (seconds / 60)
    if seconds < 120 * 60 * 24:
        return "%.2f hours" % (seconds / 60 / 60)
    return "%.2f days" % (seconds / 60 / 60 / 24)


class Timer:
    granularity = 0.1

    def __init__(self, message=None, *args):
        self.message = message
        self.args = args
        self.t0 = None

    def __enter__(self):
        self.t0 = time.time()
        return self

    def __exit__(self, a, b, c):
        t1 = time.time()
        if t1 - self.t0 > Timer.granularity:
            m = self.message
            a = []
            logger = logging.getLogger(__name__)
            for arg in self.args:
                if isinstance(arg, types.FunctionType):
                    try:
                        a.append(arg())
                    except Exception:
                        a.append("<error>")
                else:
                    a.append(arg)

            if a:
                try:
                    m = m % tuple(a)
                except Exception:
                    logger.error("Couldn't format %s with %s", m, a)

            logger.info("%s took %.2f seconds.", m, t1 - self.t0)

    def __call__(self, f):
        def inner(*args, **kwargs):
            with Timer(self.message or f.__name__, *self.args):
                return f(*args, **kwargs)

        inner.__name__ = f.__name__
        return inner


def indent(text, amount=4, ch=" "):
    padding = amount * ch
    return "".join(padding + line for line in text.splitlines(True))


def distance(s1, s2):
    """Compute the edit distance between s1 and s2"""
    if len(s1) < len(s2):
        return distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    prev = range(len(s2) + 1)

    for i, c1 in enumerate(s1):
        cur = [i + 1]
        for j, c2 in enumerate(s2):
            cur.append(min(prev[j + 1] + 1, cur[j] + 1, prev[j] + (1 if c1 != c2 else 0)))
        prev = cur

    return prev[-1]


def closest_in(name, names):
    return sorted((distance(name, x), x) for x in names)[0][1]


def closest_N_in(name, names, count):
    return [x[1] for x in sorted((distance(name, x), x) for x in names)[:count]]


def sslContextFromCertPath(cert_path, key_path=None):
    assert os.path.isfile(cert_path), "Expected path to existing SSL certificate ({})".format(
        cert_path
    )
    key_path = key_path or os.path.splitext(cert_path)[0] + ".key"
    assert os.path.isfile(
        key_path
    ), "Expected to find .key file along SSL certificate ({})".format(cert_path)

    ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_ctx.load_cert_chain(cert_path, key_path)

    return ssl_ctx


def generateSslContext():
    with tempfile.TemporaryDirectory() as tempDir:
        # openssl
        cert_path = os.path.join(tempDir, "selfsigned.cert")
        key_path = os.path.join(tempDir, "selfsigned.key")
        try:
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-keyout",
                    key_path,
                    "-nodes",
                    "-out",
                    cert_path,
                    "-sha256",
                    "-days",
                    "1000",
                    "-subj",
                    "/C=US/ST=New York/L=New York/CN=localhost",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as e:
            logging.getLogger(__name__).error(
                "Failed while executing 'openssl':\n" + e.stderr.decode("utf-8")
            )
            raise

        # ssl_ctx
        ssl_ctx = sslContextFromCertPath(cert_path)

    return ssl_ctx


def sslContextFromCertPathOrNone(cert_path=None):
    return sslContextFromCertPath(cert_path) if cert_path else generateSslContext()


def genToken(randomness=10000000000000000000):
    val = random.randint(1, int(randomness))
    sha = hashlib.sha256()
    sha.update(str(val).encode())
    return sha.hexdigest()


def tokenFromString(text):
    sha = hashlib.sha256()
    sha.update(text.encode())
    return sha.hexdigest()


VALID_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def validateLogLevel(level: str, fallback=None):
    if level in VALID_LOG_LEVELS:
        return level
    elif fallback in VALID_LOG_LEVELS:
        logging.warning(f"Invalid log-level '{level}', falling back to {fallback}")
        return fallback
    else:
        raise Exception(
            "invalid log-level value: {level}. Must be one of {options}".format(
                level=level, options=VALID_LOG_LEVELS
            )
        )


def removeFileIfExists(path) -> bool:
    """Try to remove a file at path. Silently fail if it's not found.

    This is safer than checking if the file exists and then removing because
    the file could be removed by an external process in the moments between
    checking and trying to remove it.

    Returns:
        True if the removal succeeded and False if it failed because the file was not there.
    """
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False


def getDirectorySize(startPath):
    totalSize = 0
    for dirpath, dirnames, filenames in os.walk(startPath):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            # skip if it is symbolic link
            if not os.path.islink(fp):
                totalSize += os.path.getsize(fp)

    return totalSize
