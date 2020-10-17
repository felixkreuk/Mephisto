#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import sys
import pandas as pd

from mephisto.core.local_database import LocalMephistoDB
from mephisto.core.data_browser import DataBrowser as MephistoDataBrowser
from mephisto.data_model.worker import Worker
from mephisto.data_model.assignment import Unit

db = LocalMephistoDB()
mephisto_data_browser = MephistoDataBrowser(db=db)

units = mephisto_data_browser.get_units_for_task_name(sys.argv[1])
#  units = mephisto_data_browser.get_units_for_task_name(input("Input task name: "))

def format_for_printing_data(data):
    # Custom tasks can define methods for how to display their data in a relevant way
    worker_name = Worker(db, data["worker_id"]).worker_name
    contents = data["data"]
    duration = contents["times"]["task_end"] - contents["times"]["task_start"]
    metadata_string = (
        f"Worker: {worker_name}\nUnit: {data['unit_id']}\n"
        f"Duration: {int(duration)}\nStatus: {data['status']}\n"
    )

    inputs = contents["inputs"]
    outputs = contents["outputs"]

    try:
        result = {
                "audio_url": inputs["audio_url"],
                "model": inputs["model"],
                "score": outputs["score"]
        }
        return result
    except:
        return None

results = pd.DataFrame()

for unit in units:
    unit_result = format_for_printing_data(mephisto_data_browser.get_data_from_unit(unit))
    results = results.append(unit_result, ignore_index=True)

print(results)
