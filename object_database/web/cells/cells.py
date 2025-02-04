#   Copyright 2017-2021 object_database Authors
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

import queue
import time
import traceback
import logging
import types
import threading

from object_database.view import RevisionConflictException
from object_database.web.cells.session_state import SessionState
from object_database.web.cells.cell import Cell
from object_database.web.cells.slot import Slot
from object_database.web.cells.root_cell import RootCell
from object_database.web.cells.util import SubscribeAndRetry
from object_database.web.cells.computing_cell_context import ComputingCellContext
from object_database.web.cells.leaves import Text
from object_database.web.cells.leaves import Traceback


class Cells:
    def __init__(self, db):
        self.db = db

        self._eventHasTransactions = queue.Queue()

        self.db.registerOnTransactionHandler(self._onTransaction)

        # map: Cell.identity ->  Cell
        self._cells = {}

        # set: type(Cell) that have been sent over the wire
        self._nonbuiltinCellTypes = set()

        # map: Cell.identity -> set(Cell)
        self._cellsKnownChildren = {}

        # set(Cell)
        self._dirtyNodes = set()

        # set(Cell)
        self._nodesToBroadcast = set()

        # set(Cell.identity)
        self._nodeIdsToDiscard = set()

        # set(Cell)
        self._focusableCells = set()

        self._sessionId = None

        # set(Cell.identity) - the set of identities we've sent in prior
        # updates
        self._nodesKnownToChannel = set()

        self._transactionQueue = queue.Queue()

        # set(Slot) containing slots that have been dirtied but whose
        # values have not been updated yet.
        self._dirtySlots = set()

        # map: db.key -> set(Cell)
        self._subscribedCells = {}

        # used by _newID to generate unique identifiers
        self._id = 1

        # a list of pending callbacks that want to run on the main thread
        self._callbacks = queue.Queue()

        # Testing. Remove.
        self.updatedCellTypes = set()

        self._root = RootCell()

        self._shouldStopProcessingTasks = threading.Event()

        self._addCell(self._root, parent=None)

        self._dirtyComputedSlots = set()

        # cell identity to list of json messages to process in each cell object
        self._pendingOutgoingMessages = {}

        # the next packetId we'll return
        self._packetId = 1

        # map from packetId to the callback that produces the packet data
        self._packetCallbacks = {}

        # the cell that currently has the focus
        self.focusedCell = Slot(None)

        # an ever-increasing 'eventId' that we can use to handle the race between
        # the user changing focus and the server sending an old focus
        self.focusEventId = 1

    def onMessage(self, message):
        """Called when the CellHandler sends a message _directly_ to 'cells'."""
        if message.get("event") == "focusChanged":
            eventId = message.get("eventId")
            if eventId > self.focusEventId:
                cellId = message.get("cellId")

                cell = self._cells.get(cellId)

                self.focusedCell.set(cell)
                self.focusEventId = eventId

                if cell is not None:
                    cell.mostRecentFocusId = self.focusEventId

    def changeFocus(self, newCell):
        """Trigger a server-side focus change."""
        self._eventHasTransactions.put(1)

        self.focusedCell.set(newCell)
        self.focusEventId += 1000

        if newCell is not None:
            newCell.mostRecentFocusId = self.focusEventId

    def cleanupCells(self):
        """Walk down the tree calling 'onRemovedFromTree' so that our cells can GC any
        outstanding threads or downloaders they have sitting around."""

        def walk(cell):
            cell.onRemovedFromTree()
            for child in cell.children.allChildren:
                walk(child)

        walk(self._root)

    def _processCallbacks(self):
        """Execute any callbacks that have been scheduled to run on the main UI thread."""
        processed = 0
        t0 = time.time()

        try:
            while True:
                callback = self._callbacks.get(block=False)
                processed += 1

                def callCallback(callback):
                    revisionConflicts = 0

                    while True:
                        with self.db.transaction():
                            try:
                                callback()
                                return
                            except RevisionConflictException:
                                revisionConflicts += 1
                                logging.warn(
                                    "Callback threw revision conflict #%s", revisionConflicts
                                )
                                if revisionConflicts > 100:
                                    logging.error(
                                        "ComputedSlot threw so many conflicts we're bailing"
                                    )
                                return
                            except SubscribeAndRetry as e:
                                e.callback(self.db)
                            except Exception:
                                logging.exception(
                                    "Callback %s threw an unexpected exception:", callback
                                )
                                return

                callCallback(callback)
        except queue.Empty:
            return
        finally:
            if processed:
                logging.info(
                    "Processed %s callbacks in %s seconds", processed, time.time() - t0
                )

    def scheduleCallback(self, callback):
        """Schedule a callback to execute on the main cells thread as soon as possible.

        Code in other threads shouldn't modify cells or slots.
        Cells that want to trigger asynchronous work can do so and then push
        content back into Slot objects using these callbacks.
        """
        self._callbacks.put(callback)
        self._eventHasTransactions.put(1)

    def markPendingMessage(self, cell, message):
        self.markPendingMessages(cell, [message])

    def markPendingMessages(self, cell, message):
        wasEmpty = len(self._pendingOutgoingMessages) == 0

        messagesToSend = self._pendingOutgoingMessages.setdefault(cell.identity, [])

        messagesToSend.extend(message)

        if wasEmpty:
            self._eventHasTransactions.put(1)

    def withRoot(self, root_cell, session_state=None):
        self._root.setChild(root_cell)
        self._root.setContext(
            SessionState, session_state or self._root.context.get(SessionState)
        )
        return self

    def __contains__(self, cell_or_id):
        if isinstance(cell_or_id, Cell):
            return cell_or_id.identity in self._cells
        else:
            return cell_or_id in self._cells

    def __len__(self):
        return len(self._cells)

    def __getitem__(self, ix):
        return self._cells.get(ix)

    def _newID(self):
        self._id += 1
        return str(self._id)

    def triggerIfHasDirty(self):
        if self._dirtyNodes:
            self._eventHasTransactions.put(1)

    def wait(self):
        self._eventHasTransactions.get()

        # drain the queue
        try:
            while True:
                self._eventHasTransactions.get_nowait()
        except queue.Empty:
            pass

    def _onTransaction(self, *trans):
        self._transactionQueue.put(trans)
        self._eventHasTransactions.put(1)

    def _handleTransaction(self, key_value, set_adds, set_removes, transactionId):
        """ Given the updates coming from a transaction, update self._subscribedCells. """
        for k in list(key_value) + list(set_adds) + list(set_removes):
            if k in self._subscribedCells:
                self._subscribedCells[k] = set(
                    cell for cell in self._subscribedCells[k] if not cell.garbageCollected
                )

                toTrigger = list(self._subscribedCells[k])

                for cell in toTrigger:
                    cell.subscribedOdbValueChanged(k)

                if not self._subscribedCells[k]:
                    del self._subscribedCells[k]

    def _addCell(self, cell, parent):
        if not isinstance(cell, Cell):
            raise Exception(
                f"Can't add a cell of type {type(cell)} which isn't a subclass of Cell."
            )

        if cell.cells is not None:
            raise Exception(
                f"Cell {cell} is already installed as a child of {cell.parent}."
                f" We can't add it to {parent}"
            )

        cell.install(self, parent, self._newID())

        assert cell.identity not in self._cellsKnownChildren
        self._cellsKnownChildren[cell.identity] = set()

        assert cell.identity not in self._cells
        self._cells[cell.identity] = cell

        if cell.FOCUSABLE:
            self._focusableCells.add(cell)

    def _cellOutOfScope(self, cell):
        for c in cell.children.allChildren:
            self._cellOutOfScope(c)

        self.markToDiscard(cell)

        if cell.cells is not None:
            assert cell.cells == self
            del self._cells[cell.identity]
            del self._cellsKnownChildren[cell.identity]
            for sub in cell.subscriptions:
                self.unsubscribeCell(cell, sub)

        cell.garbageCollected = True

    def subscribeCell(self, cell, subscription):
        self._subscribedCells.setdefault(subscription, set()).add(cell)

    def unsubscribeCell(self, cell, subscription):
        if subscription in self._subscribedCells:
            self._subscribedCells[subscription].discard(cell)
            if not self._subscribedCells[subscription]:
                del self._subscribedCells[subscription]

    def markDirty(self, cell):
        assert not cell.garbageCollected, (cell, cell.text if isinstance(cell, Text) else "")
        self._dirtyNodes.add(cell)

    def computedSlotDirty(self, slot):
        self._dirtyComputedSlots.add(slot)
        self._eventHasTransactions.put(1)

    def markToDiscard(self, cell):
        assert not cell.garbageCollected, (cell, cell.text if isinstance(cell, Text) else "")

        if cell.identity in self._nodesKnownToChannel:
            self._nodeIdsToDiscard.add(cell.identity)

        self._nodesToBroadcast.discard(cell)
        self._focusableCells.discard(cell)

        cell.onRemovedFromTree()

    def markToBroadcast(self, node):
        assert node.cells is self

        self._nodesToBroadcast.add(node)

    def dumpTree(self, cell=None, indent=0):
        print(" " * indent + str(cell))
        for child in cell.children.allChildren:
            self.dumpTree(child, indent + 2)

    def pickFocusedCell(self):
        """Pick the most recently focused focusable cell."""
        if not self._focusableCells:
            return

        return sorted(
            self._focusableCells,
            key=lambda cell: (cell.mostRecentFocusId or -1, str(cell.identity)),
        )[-1]

    def renderMessages(self):
        self._processCallbacks()
        self._recalculateCells()

        if (
            self.focusedCell.get()
            and self.focusedCell.get().identity in self._nodeIdsToDiscard
        ):
            self.focusedCell.set(self.pickFocusedCell())
            self.focusEventId += 1

        packet = dict(
            # indicate that this is one complete cell frame
            type="#frame",
            # list of cell identities that were discarded
            nodesToDiscard=[],
            # map from cellId -> cell update
            # each update contains the properties, children, and named
            # children that have changed
            nodesUpdated={},
            # for any new nodes, the complete body of the node
            nodesCreated={},
            # messages: dict from cell-id to []
            messages={},
            # new cell types: list of [(javascript, css)]
            dynamicCellTypeDefinitions=[],
            focusedCellId=self.focusedCell.get().identity if self.focusedCell.get() else None,
            focusedCellEventId=self.focusEventId,
        )

        for node in self._nodesToBroadcast:
            # assert that the parent of each child is either in this set, or is known
            # to the other side of the connection
            if node.parent is None:
                assert isinstance(node, RootCell)
            else:
                assert (
                    node.parent in self._nodesToBroadcast
                    or node.parent.identity in self._nodesKnownToChannel
                )

        for node in self._nodesToBroadcast:
            if not node.isBuiltinCell():
                if type(node) not in self._nonbuiltinCellTypes:
                    self._nonbuiltinCellTypes.add(type(node))
                    packet["dynamicCellTypeDefinitions"].append(
                        (type(node).getDefinitionalJavascript(), type(node).getCssRules())
                    )

            if node.identity not in self._nodesKnownToChannel:
                self._nodesKnownToChannel.add(node.identity)

                packet["nodesCreated"][node.identity] = dict(
                    cellType=node.cellJavascriptClassName(),
                    extraData=node.getDisplayExportData(),
                    children=node.children.namedChildIdentities(),
                    parent=node.parent.identity if node.parent is not None else None,
                )
            else:
                packet["nodesUpdated"][node.identity] = dict(
                    extraData=node.getDisplayExportData(),
                    children=node.children.namedChildIdentities(),
                )

            # check that every node we're sending is either known
            # already, or in the broadcast set
            for child in node.children.allChildren:
                assert (
                    child.identity in self._nodesKnownToChannel
                    or child in self._nodesToBroadcast
                )

        # Make the compound message
        # listing all the nodes that
        # will be discarded
        finalNodesToDiscard = packet["nodesToDiscard"]

        for nodeId in self._nodeIdsToDiscard:
            assert nodeId in self._nodesKnownToChannel
            assert nodeId not in packet["nodesUpdated"], nodeId
            assert nodeId not in packet["nodesCreated"], nodeId

            finalNodesToDiscard.append(nodeId)
            self._nodesKnownToChannel.discard(nodeId)

        for nodeId, messages in self._pendingOutgoingMessages.items():
            # only send messages for cells that still exist.
            # we process messages at the end of the cell update cycle,
            # after the tree is fully rebuilt.
            if nodeId in self._nodesKnownToChannel:
                toSend = []

                def unpackMessage(m):
                    if isinstance(m, types.FunctionType):
                        try:
                            toSend.append(m())
                        except Exception:
                            logging.exception("Callback %s threw an unexpected exception:", m)
                    else:
                        toSend.append(m)

                for m in messages:
                    unpackMessage(m)

                packet["messages"][nodeId] = toSend

        self._pendingOutgoingMessages.clear()
        self._nodesToBroadcast = set()
        self._nodeIdsToDiscard = set()

        # if packet['nodesUpdated']:
        #     print("SENDING PACKET WITH ")
        #     print("   UPDATED: ")
        #     for node in sorted(packet['nodesUpdated']):
        #         print("        ", node, "->", packet['nodesUpdated'][node]['children'])

        #     print("   NEW    : ", sorted(packet['nodesCreated']))
        #     print("   DROP   : ", sorted(packet['nodesToDiscard']))

        # print(
        #     len(str(packet)),
        #     "bytes and",
        #     len(packet['nodesCreated']) + len(packet['nodesUpdated']),
        #     "nodes"
        # )

        return [packet]

    def _recalculateComputedSlots(self):
        t0 = time.time()

        slotsComputed = set()
        while self._dirtyComputedSlots:
            slot = self._dirtyComputedSlots.pop()
            slotsComputed.add(slot)
            slot.cells = self
            slot.ensureCalculated()

        if slotsComputed and time.time() - t0 > 0.01:
            logging.info(
                "Recomputed %s ComputedSlots in %s", len(slotsComputed), time.time() - t0
            )

        return slotsComputed

    def _recalculateCells(self):
        # handle all the transactions so far
        old_queue = self._transactionQueue
        self._transactionQueue = queue.Queue()

        try:
            while True:
                self._handleTransaction(*old_queue.get_nowait())
        except queue.Empty:
            pass

        slotsRecomputed = self._recalculateComputedSlots()

        while self._dirtyNodes:
            cellsByLevel = {}
            for node in self._dirtyNodes:
                if not node.garbageCollected:
                    cellsByLevel.setdefault(node.level, []).append(node)
            self._dirtyNodes.clear()

            for level, nodesAtThisLevel in sorted(cellsByLevel.items()):
                for node in nodesAtThisLevel:
                    if not node.garbageCollected:
                        self._recalculateSingleCell(node)

        # walk all the computed slots and drop any that
        # no longer have anybody looking at them so that we don't keep
        # recomputing them.
        orphanedAny = True
        orphanedCount = 0
        while orphanedAny:
            orphanedAny = False

            for s in list(slotsRecomputed):
                if s.orphanSelfIfUnused():
                    slotsRecomputed.discard(s)
                    orphanedCount += 1
                    orphanedAny = True

        if orphanedCount:
            logging.info("GC'd %s ComputedSlot objects", orphanedCount)

    def getPacketId(self, packetCallback):
        """Return an integer 'packet' id for a callback.

        This lets us register a callback that can produce a larger bundle of
        data that we can send to the browser over http (instead of the websocket)
        which is faster and which can happen out-of-band.

        Args:
            packetCallback - a function that accepts a packetId and
                returns a 'bytes' object  that will be the response

        Returns:
            a 'packet id' we can use to identify the packet.
        """
        packetId = self._packetId

        self._packetId += 1
        self._packetCallbacks[packetId] = packetCallback

        return packetId

    def getPackets(self):
        """Get a dict from packetId to packet contents"""
        res = {}
        for packetId, packetFun in self._packetCallbacks.items():
            res[packetId] = packetFun(packetId)

        self._packetCallbacks.clear()
        return res

    def _recalculateSingleCell(self, node):
        origChildren = self._cellsKnownChildren.get(node.identity, set())

        with ComputingCellContext(node):
            try:
                while True:
                    try:
                        node.prepare()
                        node.recalculate()
                        break
                    except SubscribeAndRetry as e:
                        e.callback(self.db)

                for child_cell in node.children.allChildren:
                    if not isinstance(child_cell, Cell):
                        childname = node.children.findNameFor(child_cell)
                        raise Exception(
                            "Cell of type %s had a non-cell child %s of type %s != Cell."
                            % (type(node), childname, type(child_cell))
                        )

            except Exception:
                logging.exception("Node %s had exception during recalculation:", node)
                logging.exception("Subscribed cell threw an exception:")
                tracebackCell = Traceback(traceback.format_exc())
                node.children["content"] = tracebackCell

        self.markToBroadcast(node)

        newChildren = set(node.children.allChildren)

        # remove any nodes from the tree we're no longer using
        for child in origChildren.difference(newChildren):
            self._cellOutOfScope(child)

        for child in newChildren.difference(origChildren):
            if child.garbageCollected:
                child.prepareForReuse()
                self._addCell(child, node)
            else:
                self._addCell(child, node)
            self._recalculateSingleCell(child)

        self._cellsKnownChildren[node.identity] = newChildren

    def childrenWithExceptions(self):
        return self._root.findChildrenMatching(lambda cell: isinstance(cell, Traceback))

    def findChildrenByTag(self, tag, stopSearchingAtFoundTag=True):
        return self._root.findChildrenByTag(
            tag, stopSearchingAtFoundTag=stopSearchingAtFoundTag
        )

    def findChildrenMatching(self, filtr):
        return self._root.findChildrenMatching(filtr)
