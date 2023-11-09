#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2023 PyLECO Developers
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

from unittest.mock import MagicMock

import pytest
import zmq

from pyleco.core.message import Message
from pyleco.test import FakeContext

from pyleco.utils.pipe_handler import MessageBuffer, PipeHandler, CommunicatorPipe

cid = b"conversation_id;"  # conversation_id
header = b"".join((cid, b"mid", b"\x00"))
# the result
msg = Message(b"r", b"s", conversation_id=cid, message_id=b"mid")
msg_list = ("r", "s", cid, b"", None)
# some different message
other = Message(b"r", b"s", conversation_id=b"conversation_id9", message_id=b"mid")


@pytest.fixture
def message_buffer() -> MessageBuffer:
    message_buffer = MessageBuffer()
    message_buffer._buffer = [msg]
    return message_buffer


# Test MessageBuffer
def test_add_conversation_id(message_buffer: MessageBuffer):
    message_buffer.add_conversation_id(conversation_id=cid)
    assert cid in message_buffer._cids


class Test_add_response_message_successful:
    @pytest.fixture
    def message_buffer_added(self) -> MessageBuffer:
        # Arrange
        mb = MessageBuffer()
        assert mb._buffer == []
        mb.add_conversation_id(cid)
        # Act
        self.return_value = mb.add_response_message(msg)
        return mb

    def test_return_value(self, message_buffer_added):
        assert self.return_value is True

    def test_msg_in_buffer(self, message_buffer_added):
        assert message_buffer_added._buffer == [msg]

    def test_cid_cleared(self, message_buffer_added: MessageBuffer):
        assert message_buffer_added._cids == []


def test_add_fails_without_previous_cid():
    empty_message_buffer = MessageBuffer()
    assert empty_message_buffer.add_response_message(message=msg) is False
    assert empty_message_buffer._buffer == []


class Test_check_message_in_buffer:
    @pytest.fixture
    def message_buffer_cmib(self, message_buffer: MessageBuffer):
        predicate = message_buffer._predicate_generator(cid)
        message_buffer._predicate = predicate  # type: ignore
        return message_buffer

    def test_message_is_in_first_place(self, message_buffer_cmib: MessageBuffer):
        assert message_buffer_cmib._predicate() is True  # type: ignore
        assert message_buffer_cmib._result == msg
        assert message_buffer_cmib._buffer == []

    def test_no_suitable_message_in_buffer(self, message_buffer: MessageBuffer):
        predicate = message_buffer._predicate_generator(conversation_id=b"other_cid")
        assert predicate() is False
        assert not hasattr(message_buffer, "_result")
        assert message_buffer._buffer != []

    def test_msg_somewhere_in_buffer(self, message_buffer_cmib: MessageBuffer):
        o2 = Message(b"r", b"s", conversation_id=b"conversation_id9", message_id=b"mi7")
        message_buffer_cmib._buffer = [other, msg, o2]
        assert message_buffer_cmib._predicate() is True  # type:ignore
        assert message_buffer_cmib._result == msg
        assert message_buffer_cmib._buffer == [other, o2]


@pytest.mark.parametrize("buffer", (
        [msg],  # msg is only message
        [msg, other],  # msg is in the first place of the buffer
        [other, msg],  # msg is in the second and last place of the buffer
        [other, msg, other]  # msg is in the middle of the buffer
    ))
def test_retrieve_message_success(message_buffer: MessageBuffer, buffer):
    message_buffer._buffer = buffer
    original_length = len(buffer)
    assert message_buffer.retrieve_message(cid) == msg
    assert len(message_buffer._buffer) == original_length - 1


@pytest.mark.parametrize("buffer", (
        [],  # no message in buffer
        [other],  # other message in buffer
    ))
def test_retrieve_message_fail(message_buffer: MessageBuffer, buffer):
    message_buffer._buffer = buffer
    with pytest.raises(TimeoutError):
        message_buffer.retrieve_message(conversation_id=cid, timeout=0.01)


@pytest.mark.parametrize("length", (1, 3, 7))
def test_length_of_buffer(message_buffer: MessageBuffer, length: int):
    message_buffer._buffer = length * [msg]
    assert len(message_buffer) == length


# Test PipeHandler
@pytest.fixture
def pipe_handler():
    """With fake contexts, that is with a broken pipe."""
    pipe_handler = PipeHandler(name="handler", context=FakeContext())  # type: ignore
    return pipe_handler


@pytest.fixture
def pipe_handler_pipe():
    """With a working pipe!"""
    pipe_handler = PipeHandler(name="handler", context=FakeContext())  # type: ignore
    pipe_handler.internal_pipe = zmq.Context.instance().socket(zmq.PULL)
    pipe_handler.pipe_port = pipe_handler.internal_pipe.bind_to_random_port(
        "inproc://listenerPipe", min_port=12345)
    yield pipe_handler
    pipe_handler.close()


@pytest.fixture
def communicator(pipe_handler_pipe: PipeHandler):
    return pipe_handler_pipe.get_communicator()


class Test_handle_commands:
    def test_handle_response(self, pipe_handler: PipeHandler):
        message = Message("rec", "send")
        pipe_handler.buffer.add_conversation_id(message.conversation_id)
        # act
        pipe_handler.handle_commands(message)
        assert pipe_handler.buffer.retrieve_message(message.conversation_id) == message

    def test_handle_request(self, pipe_handler: PipeHandler):
        """Message is not a response, but a request."""
        message = Message("rec", "send")
        pipe_handler.finish_handle_commands = MagicMock()  # type: ignore[method-assign]
        # act
        pipe_handler.handle_commands(message)
        # assert
        pipe_handler.finish_handle_commands.assert_called_once_with(message)


class Test_get_communicator:
    @pytest.fixture
    def pipe_handler_setup(self):
        pipe_handler = PipeHandler(name="handler", context=FakeContext())  # type: ignore
        communicator = pipe_handler.get_communicator(context=FakeContext())  # type: ignore
        pipe_handler.external_pipe = communicator  # type: ignore
        return pipe_handler

    def test_external_pipe_type(self, pipe_handler_setup: PipeHandler):
        assert isinstance(pipe_handler_setup.external_pipe, CommunicatorPipe)  # type: ignore

    def test_pipe_ports_match(self, pipe_handler_setup: PipeHandler):
        port_number = pipe_handler_setup.pipe_port
        assert port_number == 5  # due to FakeSocket
        assert pipe_handler_setup.internal_pipe.addr == "inproc://listenerPipe"
        assert pipe_handler_setup.external_pipe.socket.addr == "inproc://listenerPipe:5"  # type: ignore  # noqa

    def test_second_call_returns_same_communicator(self, pipe_handler_setup: PipeHandler):
        com2 = pipe_handler_setup.get_communicator()
        assert com2 == pipe_handler_setup.external_pipe  # type: ignore


def test_communicator_send_message(pipe_handler_pipe: PipeHandler, communicator: CommunicatorPipe):
    message = Message("rec", "send")
    pipe_handler_pipe._send_frames = MagicMock()  # type: ignore[method-assign]
    communicator.send_message(message)
    pipe_handler_pipe.handle_pipe_message()
    # assert that the message is actually sent
    pipe_handler_pipe._send_frames.assert_called_once_with(frames=message.to_frames())


def test_communicator_send_message_without_sender(pipe_handler_pipe: PipeHandler,
                                                  communicator: CommunicatorPipe):
    message = Message("rec", sender="")
    pipe_handler_pipe._send_frames = MagicMock()  # type: ignore[method-assign]
    communicator.send_message(message)
    pipe_handler_pipe.handle_pipe_message()
    # assert that the message is actually sent
    message.sender = b"handler"  # should have been added by the handler
    pipe_handler_pipe._send_frames.assert_called_once_with(frames=message.to_frames())


def test_communicator_read_message(pipe_handler_pipe: PipeHandler, communicator: CommunicatorPipe):
    response = Message("handler", "rec", conversation_id=cid)
    pipe_handler_pipe.buffer.add_conversation_id(cid)
    pipe_handler_pipe.buffer.add_response_message(response)
    # act
    read = communicator.read_message(cid)
    assert read == response


def test_communicator_ask_message(pipe_handler_pipe: PipeHandler, communicator: CommunicatorPipe):
    message = Message("rec", "handler", conversation_id=cid)
    response = Message("handler", "rec", conversation_id=cid)
    pipe_handler_pipe._send_frames = MagicMock()  # type: ignore[method-assign]
    pipe_handler_pipe.buffer.add_conversation_id(cid)
    pipe_handler_pipe.buffer.add_response_message(response)
    # act
    read = communicator.ask_message(message)
    pipe_handler_pipe.handle_pipe_message()
    # assert
    assert read == response
    pipe_handler_pipe._send_frames.assert_called_once_with(frames=message.to_frames())
    assert cid in pipe_handler_pipe.buffer._cids


def test_communicator_subscribe(pipe_handler_pipe: PipeHandler, communicator: CommunicatorPipe):
    pipe_handler_pipe.subscribe_single = MagicMock()  # type: ignore[method-assign]
    # act
    communicator.subscribe_single(b"topic")
    pipe_handler_pipe.handle_pipe_message()
    # assert
    pipe_handler_pipe.subscribe_single.assert_called_once_with(topic=b"topic")


def test_communicator_unsubscribe(pipe_handler_pipe: PipeHandler, communicator: CommunicatorPipe):
    pipe_handler_pipe.unsubscribe_single = MagicMock()  # type: ignore[method-assign]
    # act
    communicator.unsubscribe_single(b"topic")
    pipe_handler_pipe.handle_pipe_message()
    # assert
    pipe_handler_pipe.unsubscribe_single.assert_called_once_with(topic=b"topic")


def test_communicator_unsubscribe_all(pipe_handler_pipe: PipeHandler,
                                      communicator: CommunicatorPipe):
    pipe_handler_pipe.unsubscribe_all = MagicMock()  # type: ignore[method-assign]
    # act
    communicator.unsubscribe_all()
    pipe_handler_pipe.handle_pipe_message()
    # assert
    pipe_handler_pipe.unsubscribe_all.assert_called_once()


def test_communicator_rename(pipe_handler_pipe: PipeHandler, communicator: CommunicatorPipe):
    pipe_handler_pipe.sign_in = MagicMock()  # type: ignore[method-assign]
    pipe_handler_pipe.sign_out = MagicMock()  # type: ignore[method-assign]
    # act
    communicator.name = "new name"
    pipe_handler_pipe.handle_pipe_message()
    # assert
    pipe_handler_pipe.sign_out.assert_called_once()
    assert pipe_handler_pipe.name == "new name"
    assert communicator.name == "new name"
    pipe_handler_pipe.sign_in.assert_called_once()


def test_add_name_change_method(pipe_handler: PipeHandler):
    method = MagicMock()
    pipe_handler.name_changing_methods.append(method)
    pipe_handler.set_full_name("new full name")
    # assert
    method.assert_called_once_with("new full name")
