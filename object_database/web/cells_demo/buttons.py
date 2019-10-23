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

from object_database.web import cells as cells
from object_database.web.CellsTestPage import CellsTestPage


class SomeButtons(CellsTestPage):
    def cell(self):
        return (
            cells.Button(
                "Small Active", lambda: None, small=True, active=True, style="primary"
            )
            + cells.Button(
                "Small Inactive", lambda: None, small=True, active=False, style="primary"
            )
            + cells.Button(
                "Large Active", lambda: None, small=False, active=True, style="primary"
            )
            + cells.Button(
                "Large Inactive", lambda: None, small=False, active=False, style="primary"
            )
        )

    def text(self):
        return "You should see some buttons in various styles."
