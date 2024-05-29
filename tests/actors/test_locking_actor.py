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

import logging
import time

from unittest.mock import MagicMock

import pytest

from pyleco.core.message import Message
from pyleco.actors.locking_actor import LockingActor
from pyleco.core.leco_protocols import LockingActorProtocol


class FantasyChannel:
    def __init__(self) -> None:
        self._prop = -1

    @property
    def channel_property(self):
        return self._prop

    @channel_property.setter
    def channel_property(self, value):
        self._prop = value

    def channel_method(self, value):
        return 2 * value


class FantasyInstrument:
    def __init__(self, adapter, name="FantasyInstrument", *args, **kwargs):
        self.name = name
        self.adapter = adapter
        super().__init__()
        self._prop = 5
        self._prop2 = 7
        self.channel = FantasyChannel()
        self.channel.trace = FantasyChannel()  # type: ignore

    @property
    def prop(self):
        return self._prop

    @prop.setter
    def prop(self, value):
        self._prop = value

    @property
    def prop2(self):
        return self._prop2

    @prop2.setter
    def prop2(self, value):
        self._prop2 = value

    def silent_method(self, value):
        self._method_value = value

    def returning_method(self, value):
        return value**2

    @property
    def long(self):
        time.sleep(0.5)
        return 7

    def connect(self, *args):
        pass

    def disconnect(self, *args):
        pass


class FakeActor(LockingActor):
    def queue_readout(self):
        logging.getLogger().info(f"queue: {time.perf_counter()}")
        super().queue_readout()

    def heartbeat(self):
        logging.getLogger().info("beating")
        super().heartbeat()


@pytest.fixture()
def actor() -> FakeActor:
    actor = FakeActor(
        "test",
        FantasyInstrument,
        auto_connect={"adapter": MagicMock()},
        port=1234,
        protocol="inproc",
    )
    actor.next_beat = float("inf")
    return actor


resources = (
    None,  # the whole device
    "prop",  # a property
    "returning_method",  # a method
    "channel",  # a channel
    "channel.trace",  # channel of a channel
    "channel.channel_property",  # property of a channel
)


@pytest.fixture
def locked_actor(actor: LockingActor) -> LockingActor:
    actor.current_message = Message("rec", "owner")
    for r in resources:
        actor.lock(r)
    actor.current_message = Message("rec", "requester")
    return actor


class TestProtocolImplemented:
    protocol_methods = [m for m in dir(LockingActorProtocol) if not m.startswith("_")]

    def static_test_methods_are_present(self):
        def testing(component: LockingActorProtocol):
            pass

        testing(FakeActor(name="test", device_class=FantasyInstrument))

    @pytest.fixture
    def component_methods(self, actor: LockingActor):
        response = actor.rpc.process_request(
            '{"id": 1, "method": "rpc.discover", "jsonrpc": "2.0"}'
        )
        result = actor.rpc_generator.get_result_from_response(response)  # type: ignore
        return result.get("methods")

    @pytest.mark.parametrize("method", protocol_methods)
    def test_method_is_available(self, component_methods, method):
        for m in component_methods:
            if m.get("name") == method:
                return
        raise AssertionError(f"Method {method} is not available.")


@pytest.mark.parametrize("resource", (None, "channel.prop2", "prop7"))
def test_check_access_rights_owner_True(locked_actor: LockingActor, resource):
    locked_actor.current_message = Message("rec", "owner")
    assert locked_actor._check_access_rights(resource) is True


@pytest.mark.parametrize("resource", (None, "prop7"))
def test_check_access_rights_requester_partially_locked_True(locked_actor: LockingActor, resource):
    """Test that another requester may access unlocked resources."""
    locked_actor.force_unlock(None)
    locked_actor.current_message = Message("rec", "requester")
    assert locked_actor._check_access_rights(resource) is True


@pytest.mark.parametrize(
    "resource", ("channel", "channel.prop2", "channel.channel_property", "prop")
)
def test_check_access_rights_False(locked_actor: LockingActor, resource):
    # arrange
    locked_actor.force_unlock(None)
    # act
    locked_actor.current_message = Message("rec", "requester")
    assert locked_actor._check_access_rights(resource) is False


@pytest.mark.parametrize(
    "resource",
    resources,
)
def lock_unlocked(actor: LockingActor, resource):
    actor.current_message = Message("rec", "owner")
    assert actor.lock(resource) is True
    assert actor._locks[resource] == b"owner"


@pytest.mark.parametrize(
    "resource",
    resources,
)
def lock_already_locked(locked_actor: LockingActor, resource):
    locked_actor.current_message = Message("rec", "owner")
    assert locked_actor.lock(resource) is True
    assert actor.locks[resource] == b"owner"


@pytest.mark.parametrize(
    "resource",
    resources,
)
def lock_fail_as_already_locked(locked_actor: LockingActor, resource):
    locked_actor.current_message = Message("rec", "requester")
    assert locked_actor.lock(resource) is False
    assert actor.locks[resource] == b"owner"


@pytest.mark.parametrize(
    "resource",
    ("prop2", "channel.channel_method"),
)
def lock_fail_for_child_of_locked_resource(locked_actor: LockingActor, resource):
    """If the parent is locked (e.g. the device), no child may be locked."""
    locked_actor.current_message = Message("rec", "requester")
    assert locked_actor.lock(resource) is False
