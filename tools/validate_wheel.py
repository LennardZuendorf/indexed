#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# Vendored from PyPI's warehouse repository at:
#   https://github.com/pypi/warehouse/blob/main/warehouse/utils/zipfiles.py
#
# This is the EXACT validator PyPI runs against every uploaded wheel/sdist.
# Running this locally before `uv publish` / twine upload catches malformed
# archives with the same error message PyPI would emit, eliminating the
# round-trip-and-fail loop.
#
# Detected malformations include (non-exhaustive):
#   - "Trailing data"                          (bytes after EOCD)
#   - "Mis-matched data size"                  (local-header vs central-directory mismatch)
#   - "Mis-matched file size"
#   - "Duplicate filename in central directory"
#   - "Duplicate filename in local headers"
#   - "Missing filename in local headers"
#   - "Mismatched central directory records / offset / size"
#   - "Comment in central directory"
#   - "ZIP contains a data descriptor"
#   - "Invalid character in filename"
#   - "Filename not unicode" / "Filename not valid UTF-8"
#   - "Invalid duplicate extra in local file"
#   - "Unknown record signature"
#   - "ZIP64 extensible data not allowed"
#   - "Malformed zip file"
#
# Usage:
#   uv run python tools/validate_wheel.py dist/*.whl

import os
import struct
import sys
import typing
import zipfile

RECORD_SIG_CENTRAL_DIRECTORY = b"\x50\x4b\x01\x02"
RECORD_SIG_LOCAL_FILE = b"\x50\x4b\x03\x04"
RECORD_SIG_EOCD = b"\x50\x4b\x05\x06"
RECORD_SIG_EOCD64 = b"\x50\x4b\x06\x06"
RECORD_SIG_EOCD64_LOCATOR = b"\x50\x4b\x06\x07"
RECORD_SIG_DATA_DESCRIPTOR = b"\x50\x4b\x07\x08"

DISALLOW_DUPLICATE_EXTRA_IDS = {
    0x0001,
    0x7075,
}
UNPRINTABLE_CHARS = set(range(0x00, 0x20)) | {0x7F}


class InvalidZipFileError(Exception):
    """Internal exception used by this module"""


def _seek_check(fp: typing.IO[bytes], amt: int, /) -> None:
    if amt < 0:
        raise InvalidZipFileError("Negative offset")
    fp.seek(amt, os.SEEK_CUR)


def _read_check(fp: typing.IO[bytes], amt: int, /) -> bytes:
    if amt < 0:
        raise InvalidZipFileError("Negative offset")
    data = fp.read(amt)
    if len(data) != amt:
        raise InvalidZipFileError("Malformed zip file")
    return data


def _contains_unprintable_chars(value: bytes) -> bool:
    return any(ch in UNPRINTABLE_CHARS for ch in value)


def _handle_local_file_header(
    fp: typing.IO[bytes], zipfile_files_and_sizes: dict[str, tuple[int, int]]
) -> bytes:
    data = _read_check(fp, 26)
    (
        gpbf,
        compress_method,
        compressed_size,
        file_size,
        filename_size,
        extra_size,
    ) = struct.unpack("<xxHHxxxxxxxxLLHH", data)
    filename = _read_check(fp, filename_size)
    extra = _read_check(fp, extra_size)

    if _contains_unprintable_chars(filename):
        raise InvalidZipFileError("Invalid character in filename")

    seen_extra_ids = set()
    while extra:
        if len(extra) < 4:
            raise InvalidZipFileError("Malformed zip file")
        extra_id, extra_data_size = struct.unpack("<HH", extra[:4])
        if extra_data_size + 4 > len(extra):
            raise InvalidZipFileError("Malformed zip file")
        if extra_id in seen_extra_ids and extra_id in DISALLOW_DUPLICATE_EXTRA_IDS:
            raise InvalidZipFileError("Invalid duplicate extra in local file")
        seen_extra_ids.add(extra_id)

        if extra_id == 0x0001:
            if extra_data_size not in (0, 8, 16, 24, 28):
                raise InvalidZipFileError("Malformed zip file")

            if extra_data_size == 0:
                if compressed_size == 0xFFFFFFFF:
                    raise InvalidZipFileError("Malformed zip file")
                if file_size == 0xFFFFFFFF:
                    raise InvalidZipFileError("Malformed zip file")

            elif extra_data_size == 8:
                if compress_method != 0x0000:
                    raise InvalidZipFileError("Malformed zip file")
                (uncompressed_size,) = struct.unpack("<Q", extra[4:12])
                compressed_size = uncompressed_size
                if file_size == 0xFFFFFFFF:
                    file_size = uncompressed_size

            else:
                if file_size == 0xFFFFFFFF:
                    (file_size,) = struct.unpack("<Q", extra[4:12])
                (compressed_size,) = struct.unpack("<Q", extra[12:20])

        elif extra_id == 0x7075:
            unicode_name = extra[9 : 4 + extra_data_size]
            if _contains_unprintable_chars(unicode_name):
                raise InvalidZipFileError("Invalid character in filename")
            try:
                unicode_name.decode("utf-8")
            except UnicodeError:
                raise InvalidZipFileError("Filename not valid UTF-8")

        extra = extra[extra_data_size + 4 :]

    has_data_descriptor = gpbf & 0x08
    if has_data_descriptor:
        raise InvalidZipFileError("ZIP contains a data descriptor")
    try:
        filename_as_str = filename.decode("utf-8")
        expected_compress_size, expected_file_size = zipfile_files_and_sizes[
            filename_as_str
        ]
        if expected_compress_size != compressed_size:
            raise InvalidZipFileError("Mis-matched data size")
        if expected_file_size != file_size:
            raise InvalidZipFileError("Mis-matched file size")
    except UnicodeError:
        raise InvalidZipFileError("Filename not unicode")
    except KeyError:
        raise InvalidZipFileError("Filename not in central directory")

    _seek_check(fp, compressed_size)

    return filename


def _handle_central_directory_header(fp: typing.IO[bytes]) -> tuple[bytes, bytes]:
    data = _read_check(fp, 42)
    _compressed_size, filename_size, extra_size, comment_size, _offset = struct.unpack(
        "<xxxxxxxxxxxxxxxxLxxxxHHHxxxxxxxxL", data
    )
    if comment_size != 0:
        raise InvalidZipFileError("Comment in central directory")
    filename = _read_check(fp, filename_size)
    extra = _read_check(fp, extra_size)

    if _contains_unprintable_chars(filename):
        raise InvalidZipFileError("Invalid character in filename")

    return filename, extra


def _handle_eocd(fp: typing.IO[bytes]) -> tuple[int, int, int]:
    data = _read_check(fp, 18)
    (
        cd_records_on_disk,
        cd_records,
        cd_size,
        cd_offset,
        comment_size,
    ) = struct.unpack("<xxxxHHLLH", data)
    if cd_records_on_disk != cd_records:
        raise InvalidZipFileError("Malformed zip file")
    _seek_check(fp, comment_size)
    return cd_records, cd_size, cd_offset


def _handle_eocd64(fp: typing.IO[bytes]) -> tuple[int, int, int]:
    data = _read_check(fp, 52)
    eocd64_size, cd_records_on_disk, cd_records, cd_size, cd_offset = struct.unpack(
        "<QxxxxxxxxxxxxQQQQ", data
    )
    if cd_records_on_disk != cd_records:
        raise InvalidZipFileError("Malformed zip file")
    if eocd64_size != 44:
        raise InvalidZipFileError("ZIP64 extensible data not allowed")
    _seek_check(fp, eocd64_size - 44)
    return cd_records, cd_size, cd_offset


def _handle_eocd64_locator(fp: typing.IO[bytes]) -> int:
    data = _read_check(fp, 16)
    (eocd64_offset,) = struct.unpack("<xxxxQxxxx", data)
    return eocd64_offset


def validate_zipfile(zip_filepath: str) -> tuple[bool, str | None]:
    """Validates that a ZIP file would parse the same through a CD-checking
    implementation and a streaming local-file-header implementation."""

    try:
        zfp = zipfile.ZipFile(zip_filepath, mode="r")
        zipfile_files = {
            zfi.orig_filename: (zfi.compress_size, zfi.file_size)
            for zfi in zfp.filelist
        }
    except zipfile.BadZipfile as e:
        return False, e.args[0]

    with open(zip_filepath, mode="rb") as fp:
        local_filenames: set[bytes] = set()
        cd_filenames: set[bytes] = set()

        expected_eocd64_offset = None
        actual_eocd64_offset = None

        cd_records = 0
        cd_offset = None
        cd_size = 0

        eocd_cd_records = None
        eocd_cd_offset = None
        eocd_cd_size = None

        while True:
            try:
                signature = _read_check(fp, 4)

                if (
                    signature == RECORD_SIG_EOCD
                    and expected_eocd64_offset is not None
                    and actual_eocd64_offset is None
                ):
                    return False, "Malformed zip file"

                if signature == RECORD_SIG_CENTRAL_DIRECTORY:
                    if cd_offset is None:
                        cd_offset = fp.tell() - 4
                    cd_records += 1

                    filename, extra = _handle_central_directory_header(fp)
                    cd_size += 46 + len(filename) + len(extra)
                    if filename in cd_filenames:
                        raise InvalidZipFileError(
                            "Duplicate filename in central directory"
                        )
                    if filename not in local_filenames:
                        raise InvalidZipFileError("Missing filename in local headers")
                    cd_filenames.add(filename)

                elif signature == RECORD_SIG_LOCAL_FILE:
                    filename = _handle_local_file_header(fp, zipfile_files)
                    if filename in local_filenames:
                        raise InvalidZipFileError("Duplicate filename in local headers")
                    local_filenames.add(filename)

                elif signature == RECORD_SIG_EOCD:
                    if cd_offset is None:
                        cd_offset = fp.tell() - 4

                    if actual_eocd64_offset is not None and eocd_cd_offset is not None:
                        _handle_eocd(fp)
                    else:
                        eocd_cd_records, eocd_cd_size, eocd_cd_offset = _handle_eocd(fp)

                    if eocd_cd_records != cd_records:
                        raise InvalidZipFileError(
                            "Mismatched central directory records"
                        )
                    if cd_offset is None or eocd_cd_offset != cd_offset:
                        raise InvalidZipFileError("Mismatched central directory offset")
                    if cd_size is None or eocd_cd_size != cd_size:
                        raise InvalidZipFileError("Mismatched central directory size")

                    break

                elif signature == RECORD_SIG_EOCD64:
                    expected_eocd64_offset = fp.tell() - 4
                    eocd_cd_records, eocd_cd_size, eocd_cd_offset = _handle_eocd64(fp)

                elif signature == RECORD_SIG_EOCD64_LOCATOR:
                    actual_eocd64_offset = _handle_eocd64_locator(fp)

                else:
                    return False, "Unknown record signature"

            except InvalidZipFileError as e:
                return False, e.args[0]

        if cd_filenames != local_filenames:
            return False, "Mis-matched local headers and central directory"

        cur = fp.tell()
        fp.seek(0, os.SEEK_END)
        if cur != fp.tell():
            return False, "Trailing data"

    return True, None


def main(argv: list[str]) -> int:
    if not argv:
        print("Usage: validate_wheel.py <wheel_or_sdist> [<more> ...]", file=sys.stderr)
        return 2

    failures = 0
    for path in argv:
        name = os.path.basename(path)
        if not os.path.isfile(path):
            print(f"{name}: NOT FOUND", file=sys.stderr)
            failures += 1
            continue
        ok, error = validate_zipfile(path)
        if ok:
            print(f"{name}: OK")
        else:
            print(f"{name}: REJECTED — {error}", file=sys.stderr)
            failures += 1

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
