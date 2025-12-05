import abc
import gzip
import lzma
import json
import shutil
import threading
from pathlib import Path

from . import Aggregator


def _verbatim_move(src, dst):
    def copy_without_symlinks(src, dst):
        return shutil.copy2(src, dst, follow_symlinks=False)
    shutil.move(src, dst, copy_function=copy_without_symlinks)


class JSONAggregator(Aggregator):
    """
    Collects reported results in a line-JSON output file and uploaded files
    (logs) from multiple test runs under a shared directory.

    Note that the aggregated JSON file *does not* use the test-based JSON format
    described by executor/RESULTS.md - both use JSON, but are very different.

    This aggergated format uses a top-level array (on each line) with a fixed
    field order:

        platform, status, test name, subtest name, files, note

    All these are strings except 'files', which is another (nested) array
    of strings.

    If 'testout' is present in an input test result, it is prepended to
    the list of 'files'.
    If a field is missing in the source result, it is translated to a null
    value.
    """

    def __init__(self, target, files):
        """
        'target' is a string/Path to a .json file for all ingested
        results to be aggregated (written) to.

        'files' is a string/Path of the top-level parent for all
        per-platform / per-test files uploaded by tests.
        """
        self.lock = threading.RLock()
        self.target = Path(target)
        self.files = Path(files)
        self.target_fobj = None

    def start(self):
        if self.target.exists():
            raise FileExistsError(f"{self.target} already exists")
        self.target_fobj = open(self.target, "w")

        if self.files.exists():
            raise FileExistsError(f"{self.files} already exists")
        self.files.mkdir()

    def stop(self):
        if self.target_fobj:
            self.target_fobj.close()
            self.target_fobj = None

    def _get_test_files_path(self, platform, test_name):
        """
        Return a directory path to where uploaded files should be stored
        for a particular 'platform' and 'test_name'.
        """
        platform_files = self.files / platform
        platform_files.mkdir(exist_ok=True)
        test_files = platform_files / test_name.lstrip("/")
        return test_files

    @staticmethod
    def _modify_file_list(test_files):
        return test_files

    @staticmethod
    def _move_test_files(test_files, target_dir):
        """
        Move (or otherwise process) 'test_files' as directory of files uploaded
        by the test, into the pre-computed 'target_dir' location (inside
        a hierarchy of all files from all tests).
        """
        _verbatim_move(test_files, target_dir)

    def _gen_test_results(self, input_fobj, platform, test_name):
        """
        Yield complete output JSON objects, one for each input result.
        """
        # 'testout' , 'files' and others are standard fields in the
        # test control interface, see RESULTS.md for the Executor
        for raw_line in input_fobj:
            result_line = json.loads(raw_line)

            file_names = []
            # process the file specified by the 'testout' key
            if "testout" in result_line:
                file_names.append(result_line["testout"])
            # process any additional files in the 'files' key
            if "files" in result_line:
                file_names += (f["name"] for f in result_line["files"])

            file_names = self._modify_file_list(file_names)

            output_line = (
                platform,
                result_line["status"],
                test_name,
                result_line.get("name"),  # subtest
                file_names,
                result_line.get("note"),
            )
            yield json.dumps(output_line, indent=None)

    def ingest(self, platform, test_name, test_results, test_files):
        target_test_files = self._get_test_files_path(platform, test_name)
        if target_test_files.exists():
            raise FileExistsError(f"{target_test_files} already exists for {test_name}")

        # parse the results separately, before writing any aggregated output,
        # to ensure that either ALL results from the test are ingested, or none
        # at all (ie. if one of the result lines contains JSON errors)
        with open(test_results) as test_results_fobj:
            output_results = self._gen_test_results(test_results_fobj, platform, test_name)
            output_json = "\n".join(output_results) + "\n"

        with self.lock:
            self.target_fobj.write(output_json)
            self.target_fobj.flush()

        # clean up the source test_results (Aggregator should 'mv', not 'cp')
        Path(test_results).unlink()

        # if the test_files dir is not empty
        if any(test_files.iterdir()):
            self._move_test_files(test_files, target_test_files)


class CompressedJSONAggregator(JSONAggregator, abc.ABC):
    compress_files = False
    suffix = ""
    exclude = ()

    @abc.abstractmethod
    def compressed_open(self, *args, **kwargs):
        pass

    def start(self):
        if self.target.exists():
            raise FileExistsError(f"{self.target_file} already exists")
        self.target_fobj = self.compressed_open(self.target, "wt", newline="\n")

        if self.files.exists():
            raise FileExistsError(f"{self.storage_dir} already exists")
        self.files.mkdir()

    def _modify_file_list(self, test_files):
        if self.compress_files and self.suffix:
            return [
                (name if name in self.exclude else f"{name}{self.suffix}")
                for name in test_files
            ]
        else:
            return super()._modify_file_list(test_files)

    def _move_test_files(self, test_files, target_dir):
        if not self.compress_files:
            super()._move_test_files(test_files, target_dir)
            return

        for root, _, files in test_files.walk(top_down=False):
            for file_name in files:
                src_path = root / file_name
                dst_path = target_dir / src_path.relative_to(test_files)

                dst_path.parent.mkdir(parents=True, exist_ok=True)

                # skip dirs, symlinks, device files, etc.
                if not src_path.is_file(follow_symlinks=False) or file_name in self.exclude:
                    _verbatim_move(src_path, dst_path)
                    continue

                if self.suffix:
                    dst_path = dst_path.with_name(f"{dst_path.name}{self.suffix}")

                with open(src_path, "rb") as plain_fobj:
                    with self.compressed_open(dst_path, "wb") as compress_fobj:
                        shutil.copyfileobj(plain_fobj, compress_fobj, 1048576)

                src_path.unlink()

            # we're walking bottom-up, so the local root should be empty now
            root.rmdir()


class GzipJSONAggregator(CompressedJSONAggregator):
    """
    Identical to JSONAggregator, but transparently Gzips either or both of
    the output line-JSON file with results and the uploaded files.
    """
    def compressed_open(self, *args, **kwargs):
        return gzip.open(*args, compresslevel=self.level, **kwargs)

    def __init__(
        self, target, files, *, compress_level=9,
        compress_files=True, compress_files_suffix=".gz", compress_files_exclude=None,
    ):
        """
        'target' is a string/Path to a .json.gz file for all ingested
        results to be aggregated (written) to.

        'files' is a string/Path of the top-level parent for all
        per-platform / per-test files uploaded by tests.

        'compress_level' specifies how much effort should be spent compressing,
        (1 = fast, 9 = slow).

        If 'compress_files' is True, compress also any files uploaded by tests.

        The 'compress_files_suffix' is appended to any processed test-uploaded
        files, and the respective 'files' results array is modified with the
        new file names (as if the test uploaded compressed files already).
        Set to "" (empty string) to use original file names and just compress
        them transparently in-place.

        'compress_files_exclude' is a tuple/list of strings (input 'files'
        names) to skip when compressing. Their names also won't be modified.
        """
        super().__init__(target, files)
        self.level = compress_level
        self.compress_files = compress_files
        self.suffix = compress_files_suffix
        self.exclude = compress_files_exclude or ()


class LZMAJSONAggregator(CompressedJSONAggregator):
    """
    Identical to JSONAggregator, but transparently compresses (via LZMA/XZ)
    either or both of the output line-JSON file with results and the uploaded
    files.
    """
    def compressed_open(self, *args, **kwargs):
        return lzma.open(*args, preset=self.preset, **kwargs)

    def __init__(
        self, target, files, *, compress_preset=9,
        compress_files=True, compress_files_suffix=".xz", compress_files_exclude=None,
    ):
        """
        'target' is a string/Path to a .json.xz file for all ingested
        results to be aggregated (written) to.

        'files' is a string/Path of the top-level parent for all
        per-platform / per-test files uploaded by tests.

        'compress_preset' specifies how much effort should be spent compressing,
        (1 = fast, 9 = slow). Optionally ORed with lzma.PRESET_EXTREME to spend
        even more CPU time compressing.

        If 'compress_files' is True, compress also any files uploaded by tests.

        The 'compress_files_suffix' is appended to any processed test-uploaded
        files, and the respective 'files' results array is modified with the
        new file names (as if the test uploaded compressed files already).
        Set to "" (empty string) to use original file names and just compress
        them transparently in-place.

        'compress_files_exclude' is a tuple/list of strings (input 'files'
        names) to skip when compressing. Their names also won't be modified.
        """
        super().__init__(target, files)
        self.preset = compress_preset
        self.compress_files = compress_files
        self.suffix = compress_files_suffix
        self.exclude = compress_files_exclude or ()
