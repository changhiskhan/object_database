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

import os
import unittest

import object_database.service_manager.Task as Task
from object_database.service_manager.ServiceManagerTestCommon import ServiceManagerTestCommon
from object_database.service_manager.ServiceManager import ServiceManager

from object_database import service_schema


VERBOSE = True

ownDir = os.path.dirname(os.path.abspath(__file__))


class TaskTest(ServiceManagerTestCommon, unittest.TestCase):
    def dialWorkers(self, workerCount):
        with self.database.transaction():
            ServiceManager.createOrUpdateService(
                Task.TaskService,
                "TaskService",
                target_count=workerCount,
                gbRamUsed=0,
                coresUsed=0,
            )

    def installServices(self):
        with self.database.transaction():
            ServiceManager.createOrUpdateService(
                Task.TaskService, "TaskService", target_count=1, gbRamUsed=0, coresUsed=0
            )
            ServiceManager.createOrUpdateService(
                Task.TaskDispatchService,
                "TaskDispatchService",
                target_count=1,
                gbRamUsed=0,
                coresUsed=0,
            )

        self.waitRunning("TaskService")
        self.waitRunning("TaskDispatchService")

        with open(os.path.join(ownDir, "test_files", "TestModule1.py"), "r") as f:
            files = {"TestModule1.py": f.read()}

        with self.database.transaction():
            self.testService1Object = ServiceManager.createOrUpdateService(
                "TestModule1.TestService1",
                "TestService1",
                0,
                codebase=service_schema.Codebase.createFromFiles(files),
            )
            self.testService1Codebase = self.testService1Object.codebase.instantiate()

        self.service1Conn = self.newDbConnection()
        self.service1Conn.subscribeToType(Task.Task)
        self.service1Conn.subscribeToType(Task.TaskStatus)
        self.service1Conn.subscribeToType(
            self.testService1Codebase.getClassByName("TestModule1.Record")
        )

    def test_task_running(self):
        self.installServices()

        with self.service1Conn.transaction():
            task = Task.Task.Create(
                service=self.testService1Object,
                executor=Task.FunctionTask(
                    self.testService1Codebase.getClassByName("TestModule1.createNewRecord")
                ),
            )

        self.assertTrue(
            self.service1Conn.waitForCondition(
                lambda: task.finished, timeout=5.0 * self.ENVIRONMENT_WAIT_MULTIPLIER
            )
        )

        Record = self.testService1Codebase.getClassByName("TestModule1.Record")

        with self.service1Conn.transaction():
            self.assertEqual(len(Record.lookupAll()), 1)

        with self.service1Conn.view():
            self.assertEqual(Record.lookupOne().x, 10)

    def test_task_with_dependencies(self):
        self.installServices()

        with self.service1Conn.transaction():
            task = Task.Task.Create(
                service=self.testService1Object,
                executor=self.testService1Codebase.getClassByName(
                    "TestModule1.TaskWithSubtasks"
                )(5),
            )

        self.assertTrue(
            self.service1Conn.waitForCondition(
                lambda: task.finished, timeout=10.0 * self.ENVIRONMENT_WAIT_MULTIPLIER
            )
        )

        def localVersion(x):
            if x <= 0:
                return 1
            return localVersion(x - 1) + localVersion(x - 2)

        with self.service1Conn.transaction():
            self.assertEqual(task.result.result, localVersion(5))

    def test_error_recovery(self):
        if os.getenv("TRAVIS_CI") is not None:
            # skip the test on travis.
            return

        self.installServices()
        self.dialWorkers(4)

        with self.service1Conn.transaction():
            task = Task.Task.Create(
                service=self.testService1Object,
                executor=self.testService1Codebase.getClassByName(
                    "TestModule1.TaskWithSubtasks"
                )(7),
            )

        self.assertTrue(
            self.service1Conn.waitForCondition(
                lambda: len([t for t in Task.TaskStatus.lookupAll() if t.worker is not None])
                == 4,
                timeout=20.0 * self.ENVIRONMENT_WAIT_MULTIPLIER,
            )
        )

        with self.service1Conn.view():
            print("Have", len(Task.TaskStatus.lookupAll()), "tasks")

        self.dialWorkers(0)

        self.assertTrue(
            self.service1Conn.waitForCondition(
                lambda: sum([t.times_failed for t in Task.TaskStatus.lookupAll()]) > 0,
                timeout=20.0 * self.ENVIRONMENT_WAIT_MULTIPLIER,
            )
        )

        self.dialWorkers(4)

        self.assertTrue(
            self.service1Conn.waitForCondition(
                lambda: task.finished, timeout=20.0 * self.ENVIRONMENT_WAIT_MULTIPLIER
            )
        )

        def localVersion(x):
            if x <= 0:
                return 1
            return localVersion(x - 1) + localVersion(x - 2)

        with self.service1Conn.transaction():
            self.assertEqual(task.result.result, localVersion(7))
