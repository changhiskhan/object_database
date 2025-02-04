#   Copyright 2017-2019 object_database Authors
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import logging
import os
import object_database

from object_database import Indexed, SubscribeLazilyByDefault
from typed_python import ConstDict, sha_hash, NamedTuple
import threading

from object_database.service_manager.ServiceSchema import service_schema
from typed_python.Codebase import Codebase as TypedPythonCodebase


CommitInfo = NamedTuple(reposUrl=str, commitHash=str)


# singleton state objects for the codebase cache
_codebase_lock = threading.Lock()
_codebase_cache = {}
_codebase_instantiation_dir = None


def setCodebaseInstantiationDirectory(directory, forceReset=False):
    """Called at program invocation to specify where we can instantiate codebases."""
    with _codebase_lock:
        global _codebase_instantiation_dir
        global _codebase_cache

        if forceReset:
            _codebase_instantiation_dir = None
            _codebase_cache = {}

        if _codebase_instantiation_dir == directory:
            return

        assert _codebase_instantiation_dir is None, (
            "Can't modify the codebase instantiation location. (%s != %s)"
            % (_codebase_instantiation_dir, directory)
        )

        _codebase_instantiation_dir = os.path.abspath(directory)


@service_schema.define
@SubscribeLazilyByDefault
class File:
    hash = Indexed(str)
    contents = str

    @staticmethod
    def create(contents):
        hash = sha_hash(contents).hexdigest
        f = File.lookupAny(hash=hash)
        if f:
            return f
        else:
            return File(hash=hash, contents=contents)


@service_schema.define
@SubscribeLazilyByDefault
class Codebase:
    hash = Indexed(str)

    # filename (at root of project import) to contents
    files = ConstDict(str, service_schema.File)
    commitInfo = CommitInfo

    @staticmethod
    def createFromRootlevelPath(rootPath, **kwargs):
        return Codebase.createFromCodebase(
            TypedPythonCodebase.FromRootlevelPath(rootPath, **kwargs)
        )

    @staticmethod
    def createFromCodebase(codebase: TypedPythonCodebase):
        return Codebase.createFromFiles(codebase.filesToContents)

    @staticmethod
    def createFromFiles(files):
        assert files

        files = {k: File.create(v) if not isinstance(v, File) else v for k, v in files.items()}

        hashval = sha_hash(files).hexdigest

        c = Codebase.lookupAny(hash=hashval)
        if c:
            return c

        return Codebase(hash=hashval, files=files)

    def instantiate(self, module_name=None, codebase_dir_override=None):
        """Instantiate a codebase on disk and load it."""
        with _codebase_lock:
            if codebase_dir_override is None:
                assert _codebase_instantiation_dir is not None
                codebase_dir_override = _codebase_instantiation_dir

            if self.hash not in _codebase_cache:
                try:
                    if not os.path.exists(codebase_dir_override):
                        os.makedirs(codebase_dir_override)
                except Exception as e:
                    logging.getLogger(__name__).warn(
                        "Exception trying to make directory '%s'", codebase_dir_override
                    )
                    logging.getLogger(__name__).warn("Exception: %s", e)

                disk_path = os.path.join(codebase_dir_override, self.hash)

                # preload the files, since they're lazy.
                object_database.current_transaction().db().requestLazyObjects(
                    set(self.files.values())
                )

                fileContents = {fpath: file.contents for fpath, file in self.files.items()}

                _codebase_cache[self.hash] = TypedPythonCodebase.FromFileMap(fileContents)
                _codebase_cache[self.hash].instantiate(disk_path)

            if module_name is None:
                return _codebase_cache[self.hash]

            return _codebase_cache[self.hash].getModuleByName(module_name)

    def setCommitInfo(self, commitInfo):
        self.commitInfo = commitInfo
