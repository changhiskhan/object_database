#   Coyright 2017-2019 Nativepython Authors
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


class ClickableText(CellsTestPage):
    def cell(self):
        slot = cells.Slot(0)

        return cells.Clickable(
            cells.Subscribed(lambda: f"You've clicked on this text {slot.get()} times"),
            lambda: slot.set(slot.get() + 1),
        )

    def text(self):
        return "You should see some text that you can click on to increment a counter."
