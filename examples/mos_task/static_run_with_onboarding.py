#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import os
from mephisto.core.operator import Operator
from mephisto.core.utils import get_root_dir
from mephisto.utils.scripts import load_db_and_process_config
from mephisto.server.blueprints.static_task.static_html_blueprint import BLUEPRINT_TYPE
from mephisto.server.blueprints.abstract.static_task.static_blueprint import (
    SharedStaticTaskState,
)

import hydra
from omegaconf import DictConfig
from dataclasses import dataclass, field
from typing import List, Any

TASK_DIRECTORY = os.path.join(get_root_dir(), "examples/mos_task")
CORRECT_ANSWER = "headphones"

defaults = [
    {"mephisto/blueprint": BLUEPRINT_TYPE},
    {"mephisto/architect": "local"},
    {"mephisto/provider": "mock"},
    {"conf": "onboarding_example"},
]

from mephisto.core.hydra_config import RunScriptConfig, register_script_config


@dataclass
class TestScriptConfig(RunScriptConfig):
    defaults: List[Any] = field(default_factory=lambda: defaults)
    task_dir: str = TASK_DIRECTORY
    correct_answer: str = CORRECT_ANSWER


register_script_config(name="scriptconfig", module=TestScriptConfig)


@hydra.main(config_name="scriptconfig")
def main(cfg: DictConfig) -> None:
    correct_config_answer = cfg.correct_answer

    def onboarding_is_valid(onboarding_data):
        inputs = onboarding_data["inputs"]
        outputs = onboarding_data["outputs"]
        return outputs.get("audio_device") == "headphones" and \
                outputs.get("age") == "21_41" and \
                outputs.get("education") == "college"

    qualifications = [
        {    # number of approved HITs 
             "QualificationTypeId": "00000000000000000040",
             "Comparator": "GreaterThanOrEqualTo",
             "IntegerValues": [1000],
             "ActionsGuarded": "DiscoverPreviewAndAccept",
        },
        {    # from US or Canada
             "QualificationTypeId": "00000000000000000071",
             "Comparator": "In",
             "LocaleValues":[{"Country":"US"}, {"Country": "CA"}],
             "ActionsGuarded": "DiscoverPreviewAndAccept",
        },
    ]

    shared_state = SharedStaticTaskState(
        onboarding_data={"correct_answer": correct_config_answer},
        validate_onboarding=onboarding_is_valid,
    )
    shared_state.mturk_specific_qualifications = qualifications

    db, cfg = load_db_and_process_config(cfg)
    operator = Operator(db)

    operator.validate_and_run_config(cfg.mephisto, shared_state)
    operator.wait_for_runs_then_shutdown(skip_input=True, log_rate=30)


if __name__ == "__main__":
    main()
