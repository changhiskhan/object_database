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

"""message_bus

Classes for maintaining a strongly-typed message bus over sockets,
along with classes to simulate this in tests.
"""

import ssl
import time
import threading
import queue
import struct
import logging
import os
import socket
import sortedcontainers

from typed_python import Alternative, NamedTuple, TypeFunction, serialize, deserialize

from object_database.util import sslContextFromCertPathOrNone
from object_database.bytecount_limited_queue import BytecountLimitedQueue
from object_database.socket_watcher import SocketWatcher

MESSAGE_LEN_BYTES = 4  # sizeof an int32 used to pack messages
EPOLL_TIMEOUT = 5.0
MSG_BUF_SIZE = 128 * 1024


class MessageBusLoopExit(Exception):
    pass


class CorruptMessageStream(Exception):
    pass


class MessageBuffer:
    def __init__(self, extraMessageSizeCheck: bool):
        """ The buffer we're reading

        Args:
            extraMessageSizeCheck (bool): when True, each message is not only
                preceeded by an integer value (4 bytes) that corresponds to the
                number of bytes of the message, but it is also followed by the
                same integer value.
        """
        self.buffer = bytearray()
        self.messagesEver = 0
        self.extraMessageSizeCheck = extraMessageSizeCheck

        # the current message length, if any.
        self.curMessageLen = None

    def pendingBytecount(self):
        return len(self.buffer)

    @staticmethod
    def encode(bytes, extraMessageSizeCheck: bool):
        """Prepend a message-length prefix"""
        res = bytearray(struct.pack("i", len(bytes)))
        res.extend(bytes)

        if extraMessageSizeCheck:
            res.extend(struct.pack("i", len(bytes)))

        return res

    def write(self, bytesToWrite):
        """Push bytes into the buffer and read any completed messages.

        Args:
            bytesToWrite (bytes) - a portion of the message stream

        Returns:
            A list of messages completed by the bytes.
        """
        messages = []

        self.buffer.extend(bytesToWrite)

        while True:
            if self.curMessageLen is None:
                if len(self.buffer) >= MESSAGE_LEN_BYTES:
                    self.curMessageLen = struct.unpack("i", self.buffer[:MESSAGE_LEN_BYTES])[0]
                    self.buffer[:MESSAGE_LEN_BYTES] = b""

            if self.curMessageLen is None:
                return messages

            if self.extraMessageSizeCheck:
                if len(self.buffer) >= self.curMessageLen + MESSAGE_LEN_BYTES:
                    messages.append(bytes(self.buffer[: self.curMessageLen]))
                    self.messagesEver += 1
                    msgLen = self.curMessageLen
                    sizeCheckBytes = self.buffer[msgLen : msgLen + MESSAGE_LEN_BYTES]
                    sizeCheck = struct.unpack("i", sizeCheckBytes)[0]

                    self.buffer[: msgLen + MESSAGE_LEN_BYTES] = b""
                    self.curMessageLen = None

                    if sizeCheck != msgLen:
                        raise CorruptMessageStream(f"{sizeCheck} != {msgLen}")

                else:
                    return messages
            else:
                if len(self.buffer) >= self.curMessageLen:
                    messages.append(bytes(self.buffer[: self.curMessageLen]))
                    self.messagesEver += 1
                    self.buffer[: self.curMessageLen] = b""
                    self.curMessageLen = None
                else:
                    return messages


class Disconnected:
    """A singleton representing our disconnect state."""


class FailedToStart(Exception):
    """We failed to acquire the listening socket."""


class TriggerDisconnect:
    """A singleton for triggering a channel to disconnect."""


class TriggerConnect:
    """A singleton for signaling we should connect to a channel."""


Endpoint = NamedTuple(host=str, port=int)


ConnectionId = NamedTuple(id=int)


@TypeFunction
def MessageBusEvent(MessageType):
    return Alternative(
        "MessageBusEvent",
        # the entire bus was stopped (by us). This is always the last message
        Stopped=dict(),
        # someone connected to us. All messages sent on this particular socket connectionId
        # will be associated with the given connectionId.
        NewIncomingConnection=dict(source=Endpoint, connectionId=ConnectionId),
        # an incoming connection closed
        IncomingConnectionClosed=dict(connectionId=ConnectionId),
        # someone sent us a message one one of our channels
        IncomingMessage=dict(connectionId=ConnectionId, message=MessageType),
        # we made a new outgoing connection. this connection is also
        # valid as an input connection (we may receive messages on it)
        OutgoingConnectionEstablished=dict(connectionId=ConnectionId),
        # an outgoing connection failed
        OutgoingConnectionFailed=dict(connectionId=ConnectionId),
        # an outgoing connection closed
        OutgoingConnectionClosed=dict(connectionId=ConnectionId),
    )


class MessageBus(object):
    def __init__(
        self,
        busIdentity,
        endpoint,
        inMessageType,
        outMessageType,
        onEvent,
        authToken=None,
        serializationContext=None,
        certPath=None,
        wantsSSL=True,
        sslContext=None,
        extraMessageSizeCheck=True,
    ):
        """Initialize a MessageBus

        Args:
            busIdentity: any object that identifies this message bus
            endpoint: a (host, port) tuple that we're supposed to listen on,
                or None if we accept no incoming.
            inMessageType: the wire-type of messages we receive. Can be 'object', in
                which case we'll require a serializationContext to know how
                to serialize the names of types.
            outMessageType: the wire-type of messages we send. Can be 'object', in
                which case we'll require a serializationContext to know how
                to serialize the names of types.
            serializationContext: the serialization context to use for
                serializing things, or None to use naked serialization
                from typed_python without any 'object'.
            authToken: the authentication token that must be sent to us for
                the connection to succeed. If None, then don't require
                authentication. MessageBus objects must have the same
                authToken to work together.
            onEvent: a callback function recieving a stream of 'eventType'
                objects (MessageBusEvents).
            certPath(str or None): if we use SSL, an optional path to a cert file.
            wantsSSL(bool): should we encrypt our channel with SSL
            sslContext - an SSL context if we've already got one

        The MessageBus listens for connection on the endpoint and calls
        onEvent from the read thread whenever a new event occurs.

        Clients may establish connection to other MessageBus objects, and
        will receive a ConnectionId object representing that channel.
        Other clients connecting in will produce their own 'ConnectionId's
        associated with the incoming connection. ConnectionIds are unique
        for a given MessageBus instance.

        Clients may send messages to outgoing connections that have been
        established or to other incoming connections.
        The send function indicates whether the send _might_ succeed,
        meaning it returns False only if it's KNOWN that the message
        channel on the other side is closed.

        All event callbacks are fired from the same internal thread.
        This function should never throw, and if it blocks, it will
        block execution across all threads.

        Clients are expected to call 'start' to start the bus, and 'stop'
        to stop it and tear down threads.

        Clients can call 'connect' to get a connection id back, which they
        can pass to 'closeConnection' or 'sendMessage'.
        """
        if authToken is not None:
            assert isinstance(authToken, str), (authToken, type(authToken))

        self._logger = logging.getLogger(__file__)

        self.busIdentity = busIdentity

        self._certPath = certPath
        self.onEvent = onEvent
        self.serializationContext = serializationContext
        self.inMessageType = inMessageType
        self.outMessageType = outMessageType
        self.eventType = MessageBusEvent(inMessageType)
        self._eventQueue = queue.Queue()
        self._authToken = authToken
        self._listeningEndpoint = Endpoint(endpoint) if endpoint is not None else None
        self._lock = threading.RLock()
        self.started = False
        self._acceptSocket = None
        self.extraMessageSizeCheck = extraMessageSizeCheck

        self._connIdToIncomingSocket = {}  # connectionId -> socket
        self._connIdToOutgoingSocket = {}  # connectionId -> socket

        self._socketToIncomingConnId = {}  # socket -> connectionId
        self._socketToOutgoingConnId = {}  # socket -> connectionId

        self._unauthenticatedConnections = set()
        self._connIdToIncomingEndpoint = {}  # connectionId -> Endpoint
        self._connIdToOutgoingEndpoint = {}  # connectionId -> Endpoint
        self._connIdPendingOutgoingConnection = set()
        self._messagesForUnconnectedOutgoingConnection = {}  # connectionId- > [bytes]

        self._messageToSendWakePipe = None
        self._eventToFireWakePipe = None
        self._generalWakePipe = None

        # how many bytes do we actually have in our deserialized pump loop
        # waiting to be sent down the wire.
        self.totalBytesPendingInOutputLoop = 0

        # how many bytes have we actually written (to anybody)
        self.totalBytesWritten = 0

        # how many bytes are in the deserialization queue that have not
        # created full messages.
        self.totalBytesPendingInInputLoop = 0
        self.totalBytesPendingInInputLoopHighWatermark = 0

        # how many bytes have we actually read (from anybody)
        self.totalBytesRead = 0

        self._connectionIdCounter = 0

        # queue of messages to write to other endpoints
        self._messagesToSendQueue = BytecountLimitedQueue(self._bytesPerMsg)
        self._eventsToFireQueue = queue.Queue()

        self._socketThread = threading.Thread(target=self._socketThreadLoop, daemon=True)
        self._eventThread = threading.Thread(target=self._eventThreadLoop, daemon=True)
        self._wantsSSL = wantsSSL
        self._sslContext = sslContext

        # socket -> bytes that need to be written
        self._socketToBytesNeedingWrite = {}
        self._socketsWithSslWantWrite = set()
        self._allSockets = None  # SocketWatcher

        # dict from 'socket' object to MessageBuffer
        self._incomingSocketBuffers = {}

        if self._wantsSSL:
            if self._sslContext is None:
                self._sslContext = sslContextFromCertPathOrNone(self._certPath)
        else:
            assert (
                self._certPath is None
            ), "Makes no sense to give a cert path and not request ssl"
            assert (
                self._sslContext is None
            ), "Makes no sense to give an ssl context and not request ssl"

        # a set of (timestamp, callback) pairs of callbacks we're supposed
        # to fire on the output thread.
        self._pendingTimedCallbacks = sortedcontainers.SortedSet(
            key=lambda tsAndCallback: tsAndCallback[0]
        )

    @property
    def listeningEndpoint(self):
        return self._listeningEndpoint

    @property
    def authToken(self):
        return self._authToken

    def setMaxWriteQueueSize(self, queueSize):
        """Insist that we block any _sending_ threads if our outgoing queue gets too large."""
        self._messagesToSendQueue.setMaxBytes(queueSize)

    def isWriteQueueBlocked(self):
        return self._messagesToSendQueue.isBlocked()

    def start(self):
        """
        Start the message bus. May create threads and connect sockets.
        """
        with self._lock:
            assert not self.started

            if not self._setupAcceptSocket():
                raise FailedToStart()

            # allocate the pipes that we use to wake our select loop.
            self._messageToSendWakePipe = os.pipe()
            self._eventToFireWakePipe = os.pipe()
            self._generalWakePipe = os.pipe()

            self._allSockets = SocketWatcher()
            self._allSockets.addForRead(self._generalWakePipe[0])
            self._allSockets.addForRead(self._eventToFireWakePipe[0])
            if self._acceptSocket is not None:
                self._allSockets.addForRead(self._acceptSocket)

            self.started = True
            self._socketThread.start()
            self._eventThread.start()

    def stop(self, timeout=None):
        """
        Stop the message bus.

        This bus may not be started again. Client threads blocked reading on the bus
        will return immediately with no message.
        """
        with self._lock:
            if not self.started:
                return
            self.started = False

        self._logger.debug(
            "Stopping MessageBus (%s) on endpoint %s",
            self.busIdentity,
            self._listeningEndpoint,
        )

        self._messagesToSendQueue.put(Disconnected)
        self._scheduleEvent(self.eventType.Stopped())

        self._socketThread.join(timeout=timeout)

        if self._socketThread.is_alive():
            raise Exception("Failed to shutdown our threads!")

        # shutdown the event loop after the threadloops, so that we're guaranteed
        # that we fire the shutdown events.
        self._eventQueue.put(None)
        self._eventThread.join(timeout=timeout)

        if self._eventThread.is_alive():
            raise Exception("Failed to shutdown our threads!")

        if self._acceptSocket is not None:
            self._ensureSocketClosed(self._acceptSocket)
            self._acceptSocket = None

        def closePipe(fdPair):
            os.close(fdPair[0])
            os.close(fdPair[1])

        closePipe(self._messageToSendWakePipe)
        closePipe(self._eventToFireWakePipe)
        closePipe(self._generalWakePipe)

        for sock in self._connIdToIncomingSocket.values():
            self._ensureSocketClosed(sock)

        for sock in self._connIdToOutgoingSocket.values():
            self._ensureSocketClosed(sock)

        self._allSockets.teardown()

    def connect(self, endpoint: Endpoint) -> ConnectionId:
        """Make a connection to another endpoint and return a ConnectionId for it.

        You can send messages on this ConnectionId immediately.

        Args:
            endpoint (Endpoint) - the host/port to connect to

        Returns:
            a ConnectionId representing the connection.
        """
        if not self.started:
            raise Exception(f"Bus {self.busIdentity} is not active")

        endpoint = Endpoint(endpoint)

        with self._lock:
            connId = self._newConnectionId()
            self._connIdToOutgoingEndpoint[connId] = endpoint
            self._connIdPendingOutgoingConnection.add(connId)

        # TriggerConnect must go on the sendQueue and not the EventQueue
        # in order for the auth_token to be sent (if necessary) before
        # any subsequent sendMessage calls schedule messages on the connection.
        # self._scheduleEvent((connId, TriggerConnect))
        self._putOnSendQueue(connId, TriggerConnect)

        return connId

    def closeConnection(self, connectionId):
        """Trigger a connection close."""
        if self._isDefinitelyDead(connectionId):
            return

        self._scheduleEvent((connectionId, TriggerDisconnect))

    def _isDefinitelyDead(self, connectionId):
        with self._lock:
            return (
                connectionId not in self._connIdToOutgoingEndpoint
                and connectionId not in self._connIdToIncomingEndpoint
            )

    def _putOnSendQueue(self, connectionId, msg):
        self._messagesToSendQueue.put((connectionId, msg))
        assert os.write(self._messageToSendWakePipe[1], b" ") == 1

    def scheduleCallback(self, callback, *, atTimestamp=None, delay=None):
        """Schedule a callback to fire on the message read thread.

        Use 'delay' or 'atTimestamp' to decide when the callback runs, or
        use neither to mean 'immediately'. You can't use both.

        Args:
            atTimestamp - the earliest posix timestamp to run the callback on
            delay - the amount of time until we fire the callback.
        """
        if callback is None:
            self._logger.warning("Cannot scheduleCallback(None); discarding.")
            # This would cause the event loop thread to terminate
            return

        if atTimestamp is not None and delay is not None:
            raise ValueError("atTimestamp and delay arguments cannot both have values.")

        if delay is None:
            delay = 0.0

        if atTimestamp is None:
            atTimestamp = time.time() + (delay or 0.0)

        with self._lock:
            self._pendingTimedCallbacks.add((atTimestamp, callback))

            # if we put this on the front of the queue, we need to wake
            # the thread loop
            if self._pendingTimedCallbacks[0][0] == atTimestamp:
                written = os.write(self._generalWakePipe[1], b" ")
                if written != 1:
                    raise Exception("Internal Error: Failed to write to general wake pipe")

    def sendMessage(self, connectionId, message):
        """Send a message to another endpoint endpoint.

        Send a message and return immediately (before guaranteeding we've sent
        the message). This function may block if we have too much outgoing data on the wire,
        but doesn't have to.

        Args:
            targetEndpoint - a host and port tuple.
            message - a message of type (self.MessageType) to send to the other endpoint.

        Returns:
            True if the message was queued, False if we preemptively dropped it because the
            other endpoint is disconnected.
        """
        if not self.started:
            raise Exception(f"Bus {self.busIdentity} is not active")

        if self.serializationContext is None:
            serializedMessage = serialize(self.outMessageType, message)
        else:
            serializedMessage = self.serializationContext.serialize(
                message, serializeType=self.outMessageType
            )

        if self._isDefinitelyDead(connectionId):
            return False

        self._putOnSendQueue(connectionId, serializedMessage)

        return True

    def _newConnectionId(self):
        """ Accessed by: user threads & socketThread """
        with self._lock:
            self._connectionIdCounter += 1
            return ConnectionId(id=self._connectionIdCounter)

    @staticmethod
    def _bytesPerMsg(msg):
        if not isinstance(msg, tuple):
            return 0

        if msg[1] is TriggerConnect or msg[1] is TriggerDisconnect:
            return 0

        return len(msg[1])

    def _scheduleEvent(self, event):
        """Schedule an event to get sent to the onEvent callback on the input loop

        Accessed by: user threads & socketThread
        """
        self._eventsToFireQueue.put(event)
        assert os.write(self._eventToFireWakePipe[1], b" ") == 1

    def _setupAcceptSocket(self):
        """ Accessed by: user threads via bus.start() """
        assert not self.started

        if self._listeningEndpoint is None:
            return True

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            sock.bind((self._listeningEndpoint.host, self._listeningEndpoint.port))
            sock.listen(2048)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, True)

            # if we listen on port zero, we need to get the port assigned
            # by the operating system
            if self._listeningEndpoint.port == 0:
                self._listeningEndpoint = Endpoint(
                    host=self._listeningEndpoint.host, port=sock.getsockname()[1]
                )

            if self._wantsSSL:
                assert self._sslContext is not None
                sock = self._sslContext.wrap_socket(sock, server_side=True)

            with self._lock:
                self._acceptSocket = sock

                self._logger.debug(
                    "%s listening on %s:%s",
                    self.busIdentity,
                    self._listeningEndpoint[0],
                    self._listeningEndpoint[1],
                )

        except OSError:
            sock.close()
            return False

        else:
            return True

    def _scheduleBytesForWrite(self, connId, msg):
        """ Accessed by: socketThread and eventThread

        It is called under self._lock when called by the eventThread (through _connectTo)
        and not under self._lock when called from the socketThread

        """
        if not msg:
            return

        if connId in self._connIdToOutgoingSocket:
            sslSock = self._connIdToOutgoingSocket.get(connId)

        elif connId in self._connIdToIncomingSocket:
            sslSock = self._connIdToIncomingSocket.get(connId)

        else:
            # we're not connected yet, so we can't put this on the buffer
            # so instead, put it on a pending buffer.
            if connId not in self._connIdPendingOutgoingConnection:
                # if we don't have one, it's because we disconnected
                return

            with self._lock:
                self._messagesForUnconnectedOutgoingConnection.setdefault(connId, []).append(
                    msg
                )

            return

        msgBytes = MessageBuffer.encode(msg, self.extraMessageSizeCheck)

        with self._lock:
            self.totalBytesPendingInOutputLoop += len(msgBytes)

            if sslSock not in self._socketToBytesNeedingWrite:
                self._socketToBytesNeedingWrite[sslSock] = bytearray(msgBytes)
            else:
                self._socketToBytesNeedingWrite[sslSock].extend(msgBytes)

    def _handleReadReadySocket(self, socketWithData):
        """ Our select loop indicated 'socketWithData' has data pending.

        Accessed by: socketThread
        """
        if socketWithData is self._acceptSocket:
            try:
                newSocket, newSocketSource = socketWithData.accept()

            except OSError as exc:
                # e.g., OSError: [Errno 24] Too many open files
                self._logger.info(f"Failed to accept incoming socket: {exc}")
                return False

            else:
                newSocket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, True)
                newSocket.setblocking(False)

                with self._lock:
                    connId = self._newConnectionId()
                    if self._authToken is not None:
                        self._unauthenticatedConnections.add(connId)
                    self._connIdToIncomingSocket[connId] = newSocket
                    self._socketToIncomingConnId[newSocket] = connId
                    self._connIdToIncomingEndpoint[connId] = newSocketSource
                    self._incomingSocketBuffers[newSocket] = MessageBuffer(
                        self.extraMessageSizeCheck
                    )
                    self._allSockets.addForRead(newSocket)

                self._fireEvent(
                    self.eventType.NewIncomingConnection(
                        source=Endpoint(newSocketSource), connectionId=connId
                    )
                )

                return True

        elif socketWithData in self._allSockets:
            try:
                bytesReceived = socketWithData.recv(MSG_BUF_SIZE)
            except ssl.SSLWantReadError:
                bytesReceived = None
            except ssl.SSLWantWriteError:
                self._socketsWithSslWantWrite.add(socketWithData)
            except ConnectionResetError:
                bytesReceived = b""
            except Exception:
                self._logger.exception("MessageBus read socket shutting down")
                bytesReceived = b""

            if bytesReceived is None:
                # do nothing
                pass
            elif bytesReceived == b"":
                self._markSocketClosed(socketWithData)
                return True
            else:
                self.totalBytesRead += len(bytesReceived)

                messageBuffer = self._incomingSocketBuffers[socketWithData]
                oldBytecount = messageBuffer.pendingBytecount()

                try:
                    newMessages = messageBuffer.write(bytesReceived)

                except CorruptMessageStream:
                    connId = self._getConnectionIdFromSocket(socketWithData)
                    if connId is not None:
                        self._logger.error(
                            f"Closing connection {connId} due to corrupted message stream."
                        )
                    self._markSocketClosed(socketWithData)
                    return True

                self.totalBytesPendingInInputLoop += (
                    self._incomingSocketBuffers[socketWithData].pendingBytecount()
                    - oldBytecount
                )

                self.totalBytesPendingInInputLoopHighWatermark = max(
                    self.totalBytesPendingInInputLoop,
                    self.totalBytesPendingInInputLoopHighWatermark,
                )

                for m in newMessages:
                    if not self._handleIncomingMessage(m, socketWithData):
                        self._markSocketClosed(socketWithData)
                        break

                return True

        else:
            self._logger.warning(
                "MessageBus got data on a socket it didn't know about: %s", socketWithData
            )

    def _socketThreadLoop(self):
        t0 = time.time()
        selectsWithNoUpdate = 0

        while True:
            try:
                if time.time() - t0 > 0.01:
                    t0 = time.time()
                    selectsWithNoUpdate = 0

                # don't read from the serialization queue unless we can handle the
                # bytes in our 'self.totalBytesPendingInOutputLoop' flow
                canRead = (
                    self._messagesToSendQueue.maxBytes is None
                    or self.totalBytesPendingInOutputLoop < self._messagesToSendQueue.maxBytes
                )

                # before going to sleep, flush any callbacks that need to fire. Note that
                # we do this only if we're allowed to read messages also
                if canRead:
                    maxSleepTime = self._consumeCallbacksOnOutputThread()
                    if maxSleepTime is None:
                        maxSleepTime = EPOLL_TIMEOUT
                    else:
                        maxSleepTime = min(maxSleepTime, EPOLL_TIMEOUT)
                else:
                    maxSleepTime = EPOLL_TIMEOUT

                if canRead:
                    # only listen on this socket if we can actually absorb more
                    # data. if we cant we'll wake up in EPOLL_TIMEOUT seconds, after
                    # which something should have flushed
                    self._allSockets.addForRead(self._messageToSendWakePipe[0])
                else:
                    self._allSockets.discardForRead(self._messageToSendWakePipe[0])

                try:
                    # if we're just spinning making no progress, don't bother
                    if selectsWithNoUpdate < 10:
                        for sock in self._socketToBytesNeedingWrite:
                            self._allSockets.addForWrite(sock)

                    else:
                        for sock in self._socketToBytesNeedingWrite:
                            self._allSockets.discardForWrite(sock)

                    readReady, writeReady = self._allSockets.poll(maxSleepTime)

                except ValueError:
                    # one of the sockets must have failed
                    failedSockets = self._allSockets.gc()

                    if not failedSockets:
                        # if not, then we don't have a good understanding of why this happened
                        raise

                    readReady = []
                    writeReady = []

                    for s in failedSockets:
                        if s in self._socketToBytesNeedingWrite:
                            del self._socketToBytesNeedingWrite[s]

                else:
                    didSomething = False

                    for socketWithData in readReady:
                        if socketWithData == self._messageToSendWakePipe[0]:
                            if canRead:
                                self._handleMessageToSendWakePipe()
                                didSomething = True

                        elif socketWithData == self._eventToFireWakePipe[0]:
                            self._handleEventToFireWakePipe()
                            didSomething = True

                        elif socketWithData == self._generalWakePipe[0]:
                            self._handleGeneralWakePipe()
                            didSomething = True

                        else:
                            if self._handleReadReadySocket(socketWithData):
                                didSomething = True

                    socketsWithSslWantWrite = self._socketsWithSslWantWrite
                    self._socketsWithSslWantWrite.clear()
                    for writeable in socketsWithSslWantWrite:
                        self._allSockets.discardForWrite(writeable)
                        if self._handleWriteReadySocket(writeable):
                            didSomething = True

                    # if we're just spinning making no progress, don't bother
                    if selectsWithNoUpdate < 10:
                        for writeable in writeReady:
                            if self._handleWriteReadySocket(writeable):
                                didSomething = True

                    if didSomething:
                        selectsWithNoUpdate = 0
                    else:
                        selectsWithNoUpdate += 1

            except MessageBusLoopExit:
                self._logger.debug("Socket loop for MessageBus exiting gracefully")
                return

            except Exception as e:
                self._logger.exception(
                    "INFO: MessageBus socket-thread encountered unexpected exception "
                    f"(and ignoring): {str(e)}"
                )
                time.sleep(1.0)

    def _handleMessageToSendWakePipe(self):
        """ Accessed by: socketThread """
        for receivedMsgTrigger in os.read(self._messageToSendWakePipe[0], MSG_BUF_SIZE):
            self._handleMessageToSend()

    def _handleEventToFireWakePipe(self):
        """ Accessed by: socketThread """
        for receivedMsgTrigger in os.read(self._eventToFireWakePipe[0], MSG_BUF_SIZE):
            self._handleEventToFire()

    def _handleGeneralWakePipe(self):
        """ Accessed by: socketThread """
        os.read(self._generalWakePipe[0], MSG_BUF_SIZE)

    def _handleMessageToSend(self):
        """ Accessed by: socketThread """
        connectionAndMsg = self._messagesToSendQueue.get(timeout=0.0)

        if connectionAndMsg is Disconnected or connectionAndMsg is None:
            return

        connId, msg = connectionAndMsg

        if msg is TriggerConnect:
            # preschedule the auth token write. When we connect we'll send it
            # immediately
            if self._authToken is not None:
                self._scheduleBytesForWrite(connId, self._authToken.encode("utf8"))

            # we're supposed to connect to this worker. We have to do
            # this in a background.
            self.scheduleCallback(lambda: self._connectTo(connId))

        else:
            self._scheduleBytesForWrite(connId, msg)

    def _handleEventToFire(self):
        """ Accessed by: the socketThread """
        # one message should be on the queue for each "E" msg trigger on the
        # thread pipe
        readMessage = self._eventsToFireQueue.get_nowait()

        if isinstance(readMessage, tuple) and readMessage[1] is TriggerDisconnect:
            connId = readMessage[0]
            if connId in self._connIdPendingOutgoingConnection:
                self.scheduleCallback(lambda: self._scheduleEvent(readMessage), delay=0.1)
                return

            else:
                if connId in self._connIdToOutgoingSocket:
                    self._markSocketClosed(self._connIdToOutgoingSocket[connId])

                elif connId in self._connIdToIncomingSocket:
                    self._markSocketClosed(self._connIdToIncomingSocket[connId])

                else:
                    self._logger.error(
                        f"Internal Error: can't find socket for connection ID {connId}"
                    )

        else:
            assert isinstance(readMessage, self.eventType)

            if readMessage.matches.OutgoingConnectionEstablished:
                connId = readMessage.connectionId
                sock = self._connIdToOutgoingSocket.get(connId)
                if sock:
                    self._allSockets.addForRead(sock)
                else:
                    self._logger.error(
                        f"Internal Error: no known socket for connection {connId}"
                    )

                self._fireEvent(readMessage)

            elif readMessage.matches.Stopped:
                self._fireEvent(readMessage)
                # this is the only valid way to exit the loop
                raise MessageBusLoopExit()

            else:
                self._fireEvent(readMessage)

    def _handleWriteReadySocket(self, writeable):
        """ Socket 'writeable' can accept more bytes.

        Accessed by: the socketThread

        Returns (bool) didSomething
        """
        if writeable not in self._socketToBytesNeedingWrite:
            return

        try:
            bytesWritten = writeable.send(self._socketToBytesNeedingWrite[writeable])

        except ssl.SSLWantReadError:
            bytesWritten = -1

        except ssl.SSLWantWriteError:
            self._socketsWithSslWantWrite.add(writeable)
            bytesWritten = -1

        except (OSError, BrokenPipeError):
            bytesWritten = 0

        except Exception:
            self._logger.exception(
                "MessageBus write socket shutting down because of exception"
            )
            bytesWritten = 0

        if bytesWritten == 0:
            # the primary socket close pathway is in the socket handler.
            self._allSockets.discardForWrite(writeable)

            with self._lock:
                del self._socketToBytesNeedingWrite[writeable]

            return True

        elif bytesWritten == -1:
            # do nothing
            return False

        elif bytesWritten > 0:
            with self._lock:
                self.totalBytesPendingInOutputLoop -= bytesWritten
                self.totalBytesWritten += bytesWritten

                self._socketToBytesNeedingWrite[writeable][:bytesWritten] = b""

                if not self._socketToBytesNeedingWrite[writeable]:
                    # we have no bytes to flush
                    self._allSockets.discardForWrite(writeable)
                    del self._socketToBytesNeedingWrite[writeable]

            return True

        else:
            self._logger.error(f"Internal Error: bytesWritten = {bytesWritten}")
            return False

    def _ensureSocketClosed(self, sock):
        """ Accessed by: user threads & the socketThread"""
        try:
            sock.close()
        except OSError:
            pass

    def _markSocketClosed(self, socket):
        """ Accessed by: the socketThread """
        toFire = []

        with self._lock:
            if socket in self._socketToIncomingConnId:
                connId = self._socketToIncomingConnId[socket]
                self._unauthenticatedConnections.discard(connId)
                del self._connIdToIncomingSocket[connId]
                del self._socketToIncomingConnId[socket]
                del self._connIdToIncomingEndpoint[connId]
                del self._incomingSocketBuffers[socket]
                if socket in self._socketToBytesNeedingWrite:
                    del self._socketToBytesNeedingWrite[socket]
                toFire.append(self.eventType.IncomingConnectionClosed(connectionId=connId))

            elif socket in self._socketToOutgoingConnId:
                connId = self._socketToOutgoingConnId[socket]
                del self._connIdToOutgoingEndpoint[connId]

                del self._socketToOutgoingConnId[socket]
                del self._connIdToOutgoingSocket[connId]
                del self._incomingSocketBuffers[socket]
                if socket in self._socketToBytesNeedingWrite:
                    del self._socketToBytesNeedingWrite[socket]
                toFire.append(self.eventType.OutgoingConnectionClosed(connectionId=connId))

        self._ensureSocketClosed(socket)
        self._allSockets.discard(socket)

        for event in toFire:
            self._fireEvent(event)

    def isUnauthenticated(self, connId):
        with self._lock:
            return connId in self._unauthenticatedConnections

    def _getConnectionIdFromSocket(self, socket):
        """ Accessed by: socketThread """
        if socket in self._socketToIncomingConnId:
            return self._socketToIncomingConnId[socket]
        elif socket in self._socketToOutgoingConnId:
            return self._socketToOutgoingConnId[socket]
        else:
            return None

    def _handleIncomingMessage(self, serializedMessage, socket):
        """ Accessed by: socketThread """
        connId = self._getConnectionIdFromSocket(socket)
        if connId is None:
            return False

        if connId in self._unauthenticatedConnections:
            try:
                if serializedMessage.decode("utf8") != self._authToken:
                    self._logger.error("Unauthorized socket connected to us.")
                    return False

                self._unauthenticatedConnections.discard(connId)
                self._logger.debug(f"Connection {connId} authenticated successfully.")
                return True

            except Exception:
                self._logger.exception("Failed to read incoming auth message for %s", connId)
                return False
        else:
            try:
                if self.serializationContext is None:
                    message = deserialize(self.inMessageType, serializedMessage)
                else:
                    message = self.serializationContext.deserialize(
                        serializedMessage, self.inMessageType
                    )
            except Exception:
                if serializedMessage != self._authToken:
                    self._logger.exception("Failed to deserialize a message")
                return False

            self._fireEvent(
                self.eventType.IncomingMessage(connectionId=connId, message=message)
            )

            return True

    def _fireEvent(self, event):
        """ Accessed by: the socketThread """
        self._eventQueue.put(event)

    def _connectTo(self, connId: ConnectionId):
        """Actually form an outgoing connection.

        This should never get called from the socket thread-loop because its
        a blocking call (the wrap_socket ssl code can block) and may
        introduce a deadlock.

        Accessed by: eventThread
        """
        try:
            endpoint = self._connIdToOutgoingEndpoint[connId]

            naked_socket = socket.create_connection((endpoint.host, endpoint.port))

            if self._wantsSSL:
                sock = self._sslContext.wrap_socket(naked_socket)
            else:
                sock = naked_socket

            sock.setblocking(False)

            with self._lock:
                self._socketToOutgoingConnId[sock] = connId
                self._connIdToOutgoingSocket[connId] = sock
                self._incomingSocketBuffers[sock] = MessageBuffer(self.extraMessageSizeCheck)

                if connId in self._messagesForUnconnectedOutgoingConnection:
                    messages = self._messagesForUnconnectedOutgoingConnection.pop(connId)

                    for m in messages:
                        self._scheduleBytesForWrite(connId, m)

                self._connIdPendingOutgoingConnection.discard(connId)

            # this message notifies the socket loop that it needs to pay attention to this
            # connection.
            self._scheduleEvent(self.eventType.OutgoingConnectionEstablished(connId))

            return True

        except Exception as e:
            self._logger.debug(f"Failed to Connect to {endpoint}: {str(e)}")
            # we failed to connect. cleanup after ourselves.
            with self._lock:
                if connId in self._connIdToOutgoingEndpoint:
                    del self._connIdToOutgoingEndpoint[connId]

                self._connIdPendingOutgoingConnection.discard(connId)

                if connId in self._messagesForUnconnectedOutgoingConnection:
                    del self._messagesForUnconnectedOutgoingConnection[connId]

                if connId in self._connIdToOutgoingSocket:
                    sock = self._connIdToOutgoingSocket.pop(connId)
                    del self._socketToOutgoingConnId[sock]
                    del self._connIdToOutgoingSocket[connId]
                    del self._incomingSocketBuffers[sock]
                    if sock in self._socketToBytesNeedingWrite:
                        del self._socketToBytesNeedingWrite[sock]

            self._scheduleEvent(self.eventType.OutgoingConnectionFailed(connectionId=connId))

            return False

    def _consumeCallbacksOnOutputThread(self):
        """Move any callbacks that are scheduled for now onto the event thread.

        Returns:
            None if no additional callbacks are pending, or the amount of time
            to the next scheduled callback.

        Accessed by: the socketThread
        """
        with self._lock:
            while True:
                t0 = time.time()

                if self._pendingTimedCallbacks and self._pendingTimedCallbacks[0][0] <= t0:
                    _, callback = self._pendingTimedCallbacks.pop(0)
                    if callback is not None:
                        self._eventQueue.put(callback)

                elif self._pendingTimedCallbacks:
                    return max(self._pendingTimedCallbacks[0][0] - t0, 0.0)

                else:
                    return None

    def _eventThreadLoop(self):
        while True:
            msg = self._eventQueue.get()
            if msg is None:
                return

            if isinstance(msg, self.eventType):
                try:
                    self.onEvent(msg)
                except Exception:
                    self._logger.exception("Message callback threw unexpected exception")
            else:
                try:
                    msg()
                except Exception:
                    self._logger.exception(f"User callback {msg} threw unexpected exception:")
