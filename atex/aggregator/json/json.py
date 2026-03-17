import abc
import collections
import gzip
import json
import lzma
import shutil
import threading
from pathlib import Path

from ... import util
from .. import Aggregator, AggregatorError


def _verbatim_move(src, dst):
    def copy_without_symlinks(src, dst):
        return shutil.copy2(src, dst, follow_symlinks=False)
    shutil.move(src, dst, copy_function=copy_without_symlinks)


class JSONAggregator(Aggregator):
    def __init__(self, target, files, *, allow_duplicate=False):
        """
        - `target` is a string/Path to a `.json` file for all ingested
          results to be aggregated (written) to.

        - `files` is a string/Path of the top-level parent for all per-platform
          / per-test files uploaded by tests.

        - `allow_duplicate` permits any one test name to be ingested more than
          once, appending ` (1)` to the second test name entry, ` (2)` to the
          third, etc.
        """
        self.lock = threading.RLock()
        self.target = Path(target)
        self.files = Path(files)
        self.allow_duplicate = allow_duplicate
        self.seen_tests = collections.Counter()
        self.target_fobj = None

    def start(self):
        if self.target.exists(follow_symlinks=False):
            raise FileExistsError(f"{self.target} already exists")
        self.target_fobj = open(self.target, "w")

        if self.files.exists(follow_symlinks=False):
            raise FileExistsError(f"{self.files} already exists")
        self.files.mkdir()

    def stop(self):
        if self.target_fobj:
            self.target_fobj.close()
            self.target_fobj = None

    @staticmethod
    def _modify_file_list(test_files):
        return test_files

    @staticmethod
    def _move_test_files(test_files, target_dir):
        """
        Move (or otherwise process) `test_files` as directory of files uploaded
        by the test, into the pre-computed `target_dir` location (inside
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

    def ingest(self, platform, test_name, artifacts):
        unique_id = (platform, test_name)
        if unique_id in self.seen_tests:
            if not self.allow_duplicate:
                raise AggregatorError(f"'{test_name}' was already ingested once for '{platform}'")
            else:
                test_name = f"{test_name} ({self.seen_tests[unique_id]})"
        self.seen_tests[unique_id] += 1

        artifacts = Path(artifacts)
        # TODO: define these as TestArtifacts namedtuple in Executor?
        artifacts_results = artifacts / "results"
        artifacts_files = artifacts / "files"

        if not artifacts_results.exists(follow_symlinks=False):
            raise FileNotFoundError(f"{artifacts_results} does not exist")

        platform_files = self.files / util.normalize_path(platform)
        target_test_files = platform_files / util.normalize_path(test_name)
        if target_test_files.exists(follow_symlinks=False):
            raise FileExistsError(f"{target_test_files} already exists for {test_name}")

        # parse the results separately, before writing any aggregated output,
        # to ensure that either ALL results from the test are ingested, or none
        # at all (ie. if one of the result lines contains JSON errors)
        with open(artifacts_results) as f:
            output_results = self._gen_test_results(f, platform, test_name)
            output_json = "\n".join(output_results) + "\n"

        with self.lock:
            self.target_fobj.write(output_json)
            self.target_fobj.flush()

        # clean up the source test_results (Aggregator should 'mv', not 'cp')
        Path(artifacts_results).unlink()

        # if the test_files dir is not empty
        if any(artifacts_files.iterdir()):
            platform_files.mkdir(exist_ok=True)
            # TODO: why does this work without .mkdir(target_test_files.parent) ?
            self._move_test_files(artifacts_files, target_test_files)


class CompressedJSONAggregator(JSONAggregator, abc.ABC):
    compress_files = False
    suffix = ""
    exclude = ()

    @abc.abstractmethod
    def compressed_open(self, *args, **kwargs):
        pass

    def start(self):
        if self.target.exists(follow_symlinks=False):
            raise FileExistsError(f"{self.target_file} already exists")
        self.target_fobj = self.compressed_open(self.target, "wt", newline="\n")

        if self.files.exists(follow_symlinks=False):
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
        self, *args,
        compress_level=9,
        compress_files=True, compress_files_suffix=".gz", compress_files_exclude=None,
        **kwargs,
    ):
        """
        - `args` and `kwargs` are passed to JSONAggregator().

        - `compress_level` specifies how much effort should be spent compressing,
          (1 = fast, 9 = slow).

        - If `compress_files` is `True`, compress also any files uploaded by
          tests.

        - The `compress_files_suffix` is appended to any processed test-uploaded
          files, and the respective `files` results array is modified with the
          new file names (as if the test uploaded compressed files already).
          Set to `""` (empty string) to use original file names and just
          compress them transparently in-place.

        - `compress_files_exclude` is a tuple/list of strings (input `files`
          names) to skip when compressing. Their names also won't be modified.
        """
        super().__init__(*args, **kwargs)
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
        self, *args,
        compress_preset=9, compress_files=True, compress_files_suffix=".xz",
        compress_files_exclude=None,
        **kwargs,
    ):
        """
        - `args` and `kwargs` are passed to JSONAggregator().

        - `compress_preset` specifies how much effort should be spent
          compressing (1 = fast, 9 = slow). Optionally ORed with
          `lzma.PRESET_EXTREME` to spend even more CPU time compressing.

        - If `compress_files` is `True`, compress also any files uploaded by
          tests.

        - The `compress_files_suffix` is appended to any processed test-uploaded
          files, and the respective `files` results array is modified with the
          new file names (as if the test uploaded compressed files already).
          Set to `""` (empty string) to use original file names and just
          compress them transparently in-place.

        - `compress_files_exclude` is a tuple/list of strings (input `files`
          names) to skip when compressing. Their names also won't be modified.
        """
        super().__init__(*args, **kwargs)
        self.preset = compress_preset
        self.compress_files = compress_files
        self.suffix = compress_files_suffix
        self.exclude = compress_files_exclude or ()
