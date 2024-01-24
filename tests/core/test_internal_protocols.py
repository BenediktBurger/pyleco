#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2024 PyLECO Developers
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

import pytest

from pyleco.core.message import Message, MessageTypes
from pyleco.core.internal_protocols import CommunicatorProtocol
from pyleco.test import FakeCommunicator

cid = b"conversation_id;"

# Test the utility methods of the CommunicatorProtocol


@pytest.fixture
def communicator() -> CommunicatorProtocol:
    return FakeCommunicator(name="communicator")


def test_full_name_without_namespace(communicator: FakeCommunicator):
    communicator.namespace = None
    assert communicator.full_name == "communicator"


def test_full_name_with_namespace(communicator: FakeCommunicator):
    communicator.namespace = "N1"
    assert communicator.full_name == "N1.communicator"


def test_send(communicator: FakeCommunicator):
    kwargs = dict(receiver="rec", message_type=MessageTypes.JSON, data=[4, 5], conversation_id=cid)
    communicator.send(**kwargs)  # type: ignore
    assert communicator._s[0] == Message(sender="communicator", **kwargs)  # type: ignore


class Test_ask:
    response = Message(receiver="communicator", sender="rec", conversation_id=cid)

    @pytest.fixture
    def communicator_asked(self, communicator: FakeCommunicator):
        communicator._r = [self.response]
        return communicator

    def test_sent(self, communicator_asked: FakeCommunicator):
        communicator_asked.ask(receiver="rec", conversation_id=cid)
        assert communicator_asked._s == [Message(receiver="rec", sender="communicator",
                                                 conversation_id=cid)]

    def test_read(self, communicator_asked: FakeCommunicator):
        response = communicator_asked.ask(receiver="rec", conversation_id=cid)
        assert response == self.response


class Test_ask_rpc:
    response = Message(receiver="communicator", sender="rec", conversation_id=cid,
                       message_type=MessageTypes.JSON,
                       data={
                           "jsonrpc": "2.0",
                           "result": 5,
                           "id": 1,
                           })

    @pytest.fixture
    def communicator_asked(self, communicator: FakeCommunicator):
        communicator._r = [self.response]
        return communicator

    def test_sent(self, communicator_asked: FakeCommunicator):
        communicator_asked.ask_rpc(receiver="rec", method="test_method", par1=5)
        sent = communicator_asked._s[0]
        assert communicator_asked._s == [Message(receiver="rec", sender="communicator",
                                                 conversation_id=sent.conversation_id,
                                                 message_type=MessageTypes.JSON,
                                                 data={
                                                     "jsonrpc": "2.0",
                                                     "method": "test_method",
                                                     "id": 1,
                                                     "params": {'par1': 5},
                                                 })]

    def test_read(self, communicator_asked: FakeCommunicator):
        result = communicator_asked.ask_rpc(receiver="rec", method="test_method", par1=5)
        assert result == 5
