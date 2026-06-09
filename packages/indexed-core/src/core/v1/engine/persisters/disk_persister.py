import os
import shutil


class DiskPersister:
    def __init__(self, base_path):
        self.base_path = os.path.realpath(base_path)

    def _safe_join(self, *parts: str) -> str:
        """Join path parts and verify the result stays within base_path."""
        path = os.path.realpath(os.path.join(*parts))
        if not path.startswith(self.base_path + os.sep) and path != self.base_path:
            raise ValueError(f"Path escapes storage directory: {parts!r}")
        return path

    def save_text_file(self, data, file_path):
        path = self._safe_join(self.base_path, file_path)

        self.__make_sure_path_exists(path)

        with open(path, "w", encoding="utf-8") as file:
            file.write(data)

    def read_text_file(self, file_path):
        path = self._safe_join(self.base_path, file_path)

        with open(path, "r", encoding="utf-8") as file:
            return file.read()

    def save_faiss_index(self, faiss_index, file_path):
        """Save a FAISS index using native faiss.write_index for optimal I/O."""
        import faiss

        path = self._safe_join(self.base_path, file_path)
        self.__make_sure_path_exists(path)
        faiss.write_index(faiss_index, path)

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

    def remove_folder(self, folder_name):
        directory_path = self._safe_join(self.base_path, folder_name)

        if os.path.exists(directory_path):
            shutil.rmtree(directory_path, ignore_errors=True)

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
