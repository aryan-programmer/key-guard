import logging
import logging.handlers


class BraceString(str):
    def __mod__(self, other):
        return self.format(*other)

    def __str__(self):
        return self


class StyleAdapter(logging.LoggerAdapter):

    def __init__(self, logger, extra=None):
        super(StyleAdapter, self).__init__(logger, extra)

    def process(self, msg, kwargs):
        if kwargs.pop("style", "{") == "{":  # optional
            msg = BraceString(msg)
        return msg, kwargs


logger = logging.getLogger("mfrc522Logger")
logFormatter = logging.Formatter(
    "{asctime} [{threadName:12.12s}] [{levelname:8.8s}] {message}", style="{"
)

fileHandler = logging.FileHandler("./key_guard.log")
fileHandler.setFormatter(logFormatter)
logger.addHandler(fileHandler)

consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)
level = logging.getLevelName(logging.INFO)
logger.setLevel(level)

logger = StyleAdapter(logger)
