import logging
import logging.handlers

logger = logging.getLogger("mfrc522Logger")
logFormatter = logging.Formatter(
    "%(asctime)s [%(threadName)-12.12s] [%(levelname)-8.8s]  %(message)s")

fileHandler = logging.FileHandler("./key_guard.log")
fileHandler.setFormatter(logFormatter)
logger.addHandler(fileHandler)

consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)
level = logging.getLevelName(logging.INFO)
logger.setLevel(level)
