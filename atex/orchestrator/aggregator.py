import csv
import gzip
import json
import shutil
import threading
from pathlib import Path


class CSVAggregator:
    """
    Collects reported results as a GZIP-ed CSV and files (logs) from multiple
    test runs under a shared directory.
    """

    class _ExcelWithUnixNewline(csv.excel):
        lineterminator = "\n"

    def __init__(self, csv_file, storage_dir):
        """
        'csv_file' is a string/Path to a .csv.gz file with aggregated results.

        'storage_dir' is a string/Path of the top-level parent for all
        per-platform / per-test files uploaded by tests.
        """
        self.lock = threading.RLock()
        self.storage_dir = Path(storage_dir)
        self.csv_file = Path(csv_file)
        self.csv_writer = None
        self.results_gzip_handle = None

    def open(self):
        if self.csv_file.exists():
            raise FileExistsError(f"{self.csv_file} already exists")
        f = gzip.open(self.csv_file, "wt", newline="")
        try:
            self.csv_writer = csv.writer(f, dialect=self._ExcelWithUnixNewline)
        except:
            f.close()
            raise
        self.results_gzip_handle = f

        if self.storage_dir.exists():
            raise FileExistsError(f"{self.storage_dir} already exists")
        self.storage_dir.mkdir()

    def close(self):
        self.results_gzip_handle.close()
        self.results_gzip_handle = None
        self.csv_writer = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def ingest(self, platform, test_name, json_file, files_dir):
        """
        Process 'json_file' (string/Path) for reported results and append them
        to the overall aggregated CSV file, recursively copying over the dir
        structure under 'files_dir' (string/Path) under the respective platform
        and test name in the aggregated files storage dir.
        """
        # parse the JSON separately, before writing any CSV lines, to ensure
        # that either all results from the test are ingested, or none at all
        # (if one of the lines contains JSON errors)
        csv_lines = []
        with open(json_file) as json_fobj:
            for raw_line in json_fobj:
                result_line = json.loads(raw_line)

                result_name = result_line.get("name", "")

                file_names = []
                if "testout" in result_line:
                    file_names.append(result_line["testout"])
                if "files" in result_line:
                    file_names += (f["name"] for f in result_line["files"])

                csv_lines.append((
                    platform,
                    result_line["status"],
                    test_name,
                    result_name,
                    result_line.get("note", ""),
                    *file_names,
                ))

        with self.lock:
            self.csv_writer.writerows(csv_lines)
            self.results_gzip_handle.flush()

        Path(json_file).unlink()

        platform_dir = self.storage_dir / platform
        platform_dir.mkdir(exist_ok=True)
        test_dir = platform_dir / test_name.lstrip("/")
        if test_dir.exists():
            raise FileExistsError(f"{test_dir} already exists for {test_name}")
        shutil.move(files_dir, test_dir, copy_function=shutil.copy)
