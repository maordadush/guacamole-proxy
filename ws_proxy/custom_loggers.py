import os
from glob import glob
from logging.handlers import RotatingFileHandler
from uuid import uuid4


class ReverseRotatingFileHandler(RotatingFileHandler):
    def __init__(self, filename, mode='a', maxBytes=0, backupCount=0, encoding=None):
        """
        In order to support multiprocessing log writing, upon each rollover this logger changes the
        "current" log file to a new one instead of renaming it (which causes conflicts with other
        processes currently using the file).
        This logger should only write logs in a dedicated directory, as it deletes old files
        """
        RotatingFileHandler.__init__(self, filename, mode, maxBytes, backupCount, encoding, delay=True)
        self.original_filepath = self.baseFilename
        self.baseFilename = self._generate_filename(self.original_filepath)

    @staticmethod
    def _generate_filename(filename):
        random_string = str(uuid4())[:8]
        return f'{filename}.{random_string}'

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None

        # Update the log file to a new, unique name
        self.baseFilename = self._generate_filename(self.original_filepath)
        if not self.delay:
            self.stream = self._open()

        # Attempt deleting old log files
        logs_directory_path = os.path.dirname(self.baseFilename)
        sorted_log_files = sorted(glob(f'{logs_directory_path}/*'), key=lambda t: os.stat(t).st_mtime)
        if len(sorted_log_files) > self.backupCount:
            to_delete_log_files = sorted_log_files[:len(sorted_log_files) - self.backupCount + 1]
            for log_file in to_delete_log_files:
                try:
                    os.remove(log_file)
                except PermissionError:
                    print(f'Failed to delete log file, file in use: {os.path.basename(self.baseFilename)}')
                    # Fail silently when a process is locking the file.
                    # We assume when the last process to lock file rolls over, it will delete it
                    pass
