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
        if self.results_gzip_handle:
            self.results_gzip_handle.close()
            self.results_gzip_handle = None
        self.csv_writer = None

    def __enter__(self):
        try:
            self.open()
            return self
        except Exception:
            self.close()
            raise

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
        shutil.move(files_dir, test_dir)


class JSONAggregator:
    """
    Collects reported results as a GZIP-ed line-JSON and files (logs) from
    multiple test runs under a shared directory.

    Note that the aggregated JSON file *does not* use the test-based JSON format
    described by executor/RESULTS.md - both use JSON, but are very different.

    This aggergated format uses a top-level array (on each line) with a fixed
    field order:

        platform, status, test name, subresult name, note, files

    All these are strings except 'files', which is another (nested) array
    of strings.

    If a field is missing in the source result, it is translated to a null
    value.
    """

    def __init__(self, json_file, storage_dir):
        """
        'json_file' is a string/Path to a .json.gz file with aggregated results.

        'storage_dir' is a string/Path of the top-level parent for all
        per-platform / per-test files uploaded by tests.
        """
        self.lock = threading.RLock()
        self.storage_dir = Path(storage_dir)
        self.json_file = Path(json_file)
        self.json_gzip_fobj = None

    def open(self):
        if self.json_file.exists():
            raise FileExistsError(f"{self.json_file} already exists")
        self.json_gzip_fobj = gzip.open(self.json_file, "wt", newline="\n")

        if self.storage_dir.exists():
            raise FileExistsError(f"{self.storage_dir} already exists")
        self.storage_dir.mkdir()

    def close(self):
        if self.json_gzip_fobj:
            self.json_gzip_fobj.close()
            self.json_gzip_fobj = None

    def __enter__(self):
        try:
            self.open()
            return self
        except Exception:
            self.close()
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def ingest(self, platform, test_name, results_file, files_dir):
        """
        Process 'results_file' (string/Path) for reported results and append
        them to the overall aggregated line-JSON file, recursively copying over
        the dir structure under 'files_dir' (string/Path) under the respective
        platform and test name in the aggregated storage dir.
        """
        platform_dir = self.storage_dir / platform
        test_dir = platform_dir / test_name.lstrip("/")
        if test_dir.exists():
            raise FileExistsError(f"{test_dir} already exists for {test_name}")

        # parse the results separately, before writing any aggregated output,
        # to ensure that either all results from the test are ingested, or none
        # at all (ie. if one of the result lines contains JSON errors)
        output_lines = []
        with open(results_file) as results_fobj:
            for raw_line in results_fobj:
                result_line = json.loads(raw_line)

                file_names = []
                if "testout" in result_line:
                    file_names.append(result_line["testout"])
                if "files" in result_line:
                    file_names += (f["name"] for f in result_line["files"])

                output_line = (
                    platform,
                    result_line["status"],
                    test_name,
                    result_line.get("name"),
                    result_line.get("note"),
                    file_names,
                )
                encoded = json.dumps(output_line, indent=None)
                output_lines.append(encoded)

        output_str = "\n".join(output_lines) + "\n"

        with self.lock:
            self.json_gzip_fobj.write(output_str)
            self.json_gzip_fobj.flush()

        Path(results_file).unlink()

        platform_dir.mkdir(exist_ok=True)
        shutil.move(files_dir, test_dir)
