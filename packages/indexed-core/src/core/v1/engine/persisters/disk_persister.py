import os
import shutil

from loguru import logger


class DiskPersister:
    def __init__(self, base_path):
        self.base_path = os.path.realpath(base_path)

    def _safe_join(self, *parts: str) -> str:
        """Join path parts and verify the result stays within base_path."""
        path = os.path.realpath(os.path.join(*parts))
        if os.path.commonpath([self.base_path, path]) != self.base_path:
            raise ValueError(f"Path escapes storage directory: {parts!r}")
        return path

    def save_text_file(self, data, file_path):
        path = self._safe_join(self.base_path, file_path)

        self.__make_sure_path_exists(path)

        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def read_text_file(self, file_path):
        path = self._safe_join(self.base_path, file_path)

        with open(path, "r", encoding="utf-8") as file:
            return file.read()

    def save_faiss_index(self, faiss_index, file_path):
        """Save a FAISS index using native faiss.write_index for optimal I/O."""
        import faiss

        path = self._safe_join(self.base_path, file_path)
        self.__make_sure_path_exists(path)
        tmp = path + ".tmp"
        try:
            faiss.write_index(faiss_index, tmp)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def read_faiss_index(self, file_path, mmap=True):
        """Load a FAISS index using native faiss.read_index.

        Args:
            file_path: Relative path to the FAISS index file.
            mmap: If True, use memory-mapped I/O for near-instant loading.
        """
        import faiss

        path = self._safe_join(self.base_path, file_path)
        io_flags = faiss.IO_FLAG_MMAP if mmap else 0
        return faiss.read_index(path, io_flags)

    def get_full_path(self, file_path):
        """Return the absolute path for a relative file path."""
        return self._safe_join(self.base_path, file_path)

    def create_folder(self, folder_name):
        directory_path = self._safe_join(self.base_path, folder_name)
        os.makedirs(directory_path)

    def replace_folder(self, src_folder_name: str, dest_folder_name: str) -> None:
        """Swap ``src_folder_name`` into ``dest_folder_name``'s place (B4).

        Used by the build-aside/rename-swap create path: the destination is
        only ever removed AFTER the fully-built replacement already exists on
        disk under ``src_folder_name``, so a crash mid-build never leaves
        neither version present. If a destination already exists, it is
        first moved aside (a cheap rename, not a copy) so both the old and
        new data are present on disk simultaneously until the final rename.

        If the final rename (moving the built replacement into place) fails,
        we roll back by renaming the moved-aside original back to
        ``dest_folder_name`` so the ORIGINAL collection is restored under its
        expected name, then re-raise the original error. If the rollback
        itself cannot complete, or a trash/staging directory otherwise
        survives cleanup, a warning names the residual path so a
        partial-failure state is observable rather than silent.
        """
        src_path = self._safe_join(self.base_path, src_folder_name)
        dest_path = self._safe_join(self.base_path, dest_folder_name)

        if os.path.exists(dest_path):
            trash_path = f"{dest_path}.trash-{os.getpid()}"
            os.rename(dest_path, trash_path)
            try:
                os.rename(src_path, dest_path)
            except Exception as swap_error:
                try:
                    os.rename(trash_path, dest_path)
                except OSError as rollback_error:
                    logger.warning(
                        f"replace_folder rollback failed after swap error "
                        f"({swap_error!r}): original collection may be "
                        f"stranded at {trash_path!r} and the built "
                        f"replacement at {src_path!r} ({rollback_error!r})"
                    )
                else:
                    logger.warning(
                        f"replace_folder swap failed ({swap_error!r}); rolled "
                        f"back {dest_folder_name!r} to its original contents, "
                        f"but the built replacement remains stranded at "
                        f"{src_path!r} and was not cleaned up"
                    )
                raise
            shutil.rmtree(trash_path, ignore_errors=True)
            if os.path.exists(trash_path):
                logger.warning(
                    f"replace_folder: residual trash directory left behind "
                    f"at {trash_path!r}"
                )
        else:
            os.rename(src_path, dest_path)

    def remove_folder(self, folder_name):
        directory_path = self._safe_join(self.base_path, folder_name)

        if os.path.exists(directory_path):
            shutil.rmtree(directory_path, ignore_errors=True)
            if os.path.exists(directory_path):
                logger.warning(
                    f"remove_folder: directory not fully removed: {directory_path!r}"
                )

    def remove_file(self, file_path):
        path = self._safe_join(self.base_path, file_path)

        if os.path.exists(path):
            os.remove(path)

    def is_path_exists(self, relative_path):
        try:
            path = self._safe_join(self.base_path, relative_path)
        except ValueError:
            return False
        return os.path.exists(path)

    def read_folder_files(self, relative_path):
        path = self._safe_join(self.base_path, relative_path)
        files = []
        for root, dirs, filenames in os.walk(path):
            for filename in filenames:
                files.append(os.path.relpath(os.path.join(root, filename), path))
        return files

    def __make_sure_path_exists(self, path):
        directory_path = os.path.dirname(path)

        if directory_path and not os.path.exists(directory_path):
            os.makedirs(directory_path)
