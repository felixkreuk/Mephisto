#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


import unittest
import shutil
import os
import tempfile
import time
import threading

from mephisto.server.blueprints.mock.mock_blueprint import MockBlueprint
from mephisto.server.architects.mock_architect import MockArchitect
from mephisto.providers.mock.mock_provider import MockProvider
from mephisto.core.local_database import LocalMephistoDB
from mephisto.core.task_launcher import TaskLauncher
from mephisto.core.argparse_parser import get_default_arg_dict
from mephisto.data_model.test.utils import get_test_task_run
from mephisto.data_model.assignment import InitializationData
from mephisto.data_model.task import TaskRun
from mephisto.core.supervisor import Supervisor, Job


class TestSupervisor(unittest.TestCase):
    """
    Unit testing for the Mephisto Supervisor
    """

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        database_path = os.path.join(self.data_dir, "mephisto.db")
        self.db = LocalMephistoDB(database_path)
        self.task_id = self.db.new_task("test_mock", MockBlueprint.BLUEPRINT_TYPE)
        self.task_run_id = get_test_task_run(self.db)
        self.task_run = TaskRun(self.db, self.task_run_id)
        architect_args = get_default_arg_dict(MockArchitect)
        architect_args['should_run_server'] = True
        self.architect = MockArchitect(self.db, architect_args, self.task_run, self.data_dir)
        self.architect.prepare()
        self.architect.deploy()
        self.urls = self.architect.get_socket_urls()
        self.url = self.urls[0]
        self.provider = MockProvider(self.db)
        self.provider.setup_resources_for_task_run(self.task_run, self.url)
        self.launcher = TaskLauncher(self.db, self.task_run, self.get_mock_assignment_data_array())
        self.launcher.create_assignments()
        self.launcher.launch_units(self.url)
        self.sup = None

    def tearDown(self):
        if self.sup is not None:
            self.sup.shutdown()
        self.launcher.expire_units()
        self.architect.cleanup()
        self.architect.shutdown()
        self.db.shutdown()
        shutil.rmtree(self.data_dir)

    def get_mock_assignment_data_array(self) -> InitializationData:
        mock_data = MockBlueprint.TaskRunnerClass.get_mock_assignment_data()
        return [mock_data, mock_data]

    def test_initialize_supervisor(self):
        """Ensure that the supervisor object can even be created"""
        sup = Supervisor(self.db)
        self.assertIsNotNone(sup)
        self.assertDictEqual(sup.agents, {})
        self.assertDictEqual(sup.sockets, {})
        sup.shutdown()

    def test_socket_operations(self):
        """
        Initialize a socket, and ensure the basic 
        startup and shutdown functions are working
        """
        sup = Supervisor(self.db)
        self.sup = sup
        TaskRunnerClass = MockBlueprint.TaskRunnerClass
        task_runner = TaskRunnerClass(self.task_run, get_default_arg_dict(TaskRunnerClass))
        test_job = Job(
            architect=self.architect, 
            task_runner=task_runner,
            provider=self.provider,
            registered_socket_ids=[],
        )
        socket_id = sup.setup_socket(self.url, test_job)
        self.assertIsNotNone(socket_id)
        self.assertEqual(sup.socket_count, 1)
        self.assertIn(socket_id, sup.sockets)
        socket_info = sup.sockets[socket_id]
        self.assertTrue(socket_info.is_alive)
        self.assertEqual(len(self.architect.server.subs), 1, "MockServer doesn't see registered socket")
        self.assertIsNotNone(self.architect.server.last_alive_packet, "No alive packet recieved by server")
        sup.launch_sending_thread()
        self.assertIsNotNone(sup.sending_thread)
        sup.shutdown()
        self.assertTrue(socket_info.is_closed)
        self.assertEqual(len(self.architect.server.subs), 0)

    def test_register_job(self):
        """Test registering and running a job"""
        # Handle baseline setup
        sup = Supervisor(self.db)
        self.sup = sup
        TaskRunnerClass = MockBlueprint.TaskRunnerClass
        task_runner_args = get_default_arg_dict(TaskRunnerClass)
        task_runner_args['timeout_time'] = 5
        task_runner = TaskRunnerClass(self.task_run, get_default_arg_dict(TaskRunnerClass))
        sup.register_job(self.architect, task_runner, self.provider)
        self.assertEqual(len(sup.sockets), sup.socket_count)
        self.assertEqual(sup.socket_count, 1)
        socket_info = list(sup.sockets.values())[0]
        self.assertIsNotNone(socket_info)
        self.assertTrue(socket_info.is_alive)
        socket_id = socket_info.socket_id
        task_runner = socket_info.job.task_runner
        self.assertIsNotNone(socket_id)
        self.assertEqual(len(self.architect.server.subs), 1, "MockServer doesn't see registered socket")
        self.assertIsNotNone(self.architect.server.last_alive_packet, "No alive packet recieved by server")
        sup.launch_sending_thread()
        self.assertIsNotNone(sup.sending_thread)

        # Register a worker
        mock_worker_name = 'MOCK_WORKER'
        self.architect.server.register_mock_worker(mock_worker_name)
        workers = self.db.find_workers(worker_name=mock_worker_name)
        self.assertEqual(len(workers), 1, 'Worker not successfully registered')
        worker = workers[0]
        
        self.architect.server.register_mock_worker(mock_worker_name)
        workers = self.db.find_workers(worker_name=mock_worker_name)
        self.assertEqual(len(workers), 1, 'Worker potentially re-registered')
        worker_id = workers[0].db_id

        self.assertEqual(len(task_runner.running_assignments), 0)

        # Register an agent
        mock_agent_details = "FAKE_ASSIGNMENT"
        self.architect.server.register_mock_agent(worker_id, mock_agent_details)
        agents = self.db.find_agents()
        self.assertEqual(len(agents), 1, "Agent was not created properly")

        self.architect.server.register_mock_agent(worker_id, mock_agent_details)
        agents = self.db.find_agents()
        self.assertEqual(len(agents), 1, "Agent may have been duplicated")
        agent = agents[0]
        self.assertIsNotNone(agent)
        self.assertEqual(len(sup.agents), 1, 'Agent not registered with supervisor')

        self.assertEqual(len(task_runner.running_assignments), 0, 'Task was not yet ready')

        # Register another worker
        mock_worker_name = 'MOCK_WORKER_2'
        self.architect.server.register_mock_worker(mock_worker_name)
        workers = self.db.find_workers(worker_name=mock_worker_name)
        worker_id = workers[0].db_id

        # Register an agent
        mock_agent_details = "FAKE_ASSIGNMENT_2"
        self.architect.server.register_mock_agent(worker_id, mock_agent_details)

        self.assertEqual(len(task_runner.running_assignments), 1, 'Task was not launched')
        agents = [a.agent for a in sup.agents.values()]

        # Make both agents act
        agent_id_1, agent_id_2 = agents[0].db_id, agents[1].db_id
        agent_1_data = agents[0].datastore['agents'][agent_id_1]
        agent_2_data = agents[1].datastore['agents'][agent_id_2]
        self.architect.server.send_agent_act(agent_id_1, {'text': 'message1'})
        self.architect.server.send_agent_act(agent_id_2, {'text': 'message2'})
        
        # Give up to 1 seconds for the actual operation to occur
        start_time = time.time()
        TIMEOUT_TIME = 1
        while time.time() - start_time < TIMEOUT_TIME:
            if len(agent_1_data['acts']) > 0:
                break
            time.sleep(0.1)

        self.assertLess(time.time() - start_time, TIMEOUT_TIME, 'Did not process messages in time')

        # Give up to 1 seconds for the task to complete afterwards
        start_time = time.time()
        TIMEOUT_TIME = 1
        while time.time() - start_time < TIMEOUT_TIME:
            if len(task_runner.running_assignments) == 0:
                break
            time.sleep(0.1)
        self.assertLess(time.time() - start_time, TIMEOUT_TIME, 'Did not complete task in time')

        # Give up to 1 seconds for all messages to propogate
        start_time = time.time()
        TIMEOUT_TIME = 1
        while time.time() - start_time < TIMEOUT_TIME:
            if self.architect.server.actions_observed == 2:
                break
            time.sleep(0.1)
        self.assertLess(time.time() - start_time, TIMEOUT_TIME, "Not all actions observed in time")

        sup.shutdown()
        self.assertTrue(socket_info.is_closed)

    # TODO handle testing for disconnecting in and out of tasks
