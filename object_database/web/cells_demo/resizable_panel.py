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


class BasicHResizePanel(CellsTestPage):
    def cell(self):
        return cells.ResizablePanel(
            cells.Card(cells.Text("First")), cells.Card(cells.Text("Second"))
        )

    def text(self):
        return "You should see a vertically-split resizable panel of two cards"


class BasicVResizePanel(CellsTestPage):
    def cell(self):
        return cells.ResizablePanel(
            cells.Card(cells.Text("First")),
            cells.Card(cells.Text("Second")),
            split="horizontal",
        )

    def text(self):
        return "You should see a horizontally-plit resizable panel of two cards"


class InVertSequence(CellsTestPage):
    def cell(self):
        return cells.ResizablePanel(
            cells.Card(cells.Text("First")), cells.Card(cells.Text("Second"))
        ) + cells.Text("boo")

    def text(self):
        return "Should see ResizablePanel in a Sequence with text at bottom"


class InVertSequenceFlexed(CellsTestPage):
    def cell(self):
        return cells.Flex(
            cells.ResizablePanel(
                cells.Card(cells.Text("First")), cells.Card(cells.Text("Second"))
            )
        ) + cells.Text("boo")

    def text(self):
        return "Should see ResizablePanel flexed in Sequence with text"
