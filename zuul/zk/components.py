# Copyright 2020 BMW Group
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
import json
import logging
from collections import defaultdict

from kazoo.exceptions import NoNodeError
from kazoo.recipe.cache import TreeCache, TreeEvent

from zuul.zk import ZooKeeperBase, ZooKeeperSimpleBase


COMPONENTS_ROOT = "/zuul/components"


class BaseComponent(ZooKeeperSimpleBase):
    """
    Read/write component object.

    This object holds an offline cache of all the component's attributes. In
    case of an failed update to ZooKeeper the local cache will still hold the
    fresh values. Updating any attribute uploads all attributes to ZooKeeper.

    This enables this object to be used as local key/value store even if the
    ZooKeeper connection got lost.
    """

    # Component states
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"

    log = logging.getLogger("zuul.zk.components.BaseComponent")
    kind = "base"

    def __init__(self, client, hostname):
        # Ensure that the content is available before setting any other
        # attribute, because our __setattr__ implementation is relying on it.
        self.__dict__["content"] = {
            "hostname": hostname,
            "state": self.STOPPED,
            "kind": self.kind,
        }
        # NOTE (felix): If we want to have a "read-only" component, we could
        # provide client=None to the constructor.
        super().__init__(client)

        self.path = None
        self._zstat = None

    def __getattr__(self, name):
        try:
            return self.content[name]
        except KeyError:
            raise AttributeError

    def __setattr__(self, name, value):
        # If the specified attribute is not part of our content dictionary,
        # fall back to the default __settattr__ behaviour.
        if name not in self.content.keys():
            return super().__setattr__(name, value)

        # Set the value in the local content dict
        self.content[name] = value

        if not self.path:
            self.log.error(
                "Path is not set on this component, did you forget to call "
                "register()?"
            )
            return

        # Update the ZooKeeper node
        content = json.dumps(self.content).encode("utf-8")
        try:
            zstat = self.kazoo_client.set(
                self.path, content, version=self._zstat.version
            )
            self._zstat = zstat
        except NoNodeError:
            self.log.error("Could not update %s in ZooKeeper", self)

    def register(self):
        path = "/".join([COMPONENTS_ROOT, self.kind, self.hostname])
        self.log.debug("Registering component in ZooKeeper %s", path)
        self.path, self._zstat = self.kazoo_client.create(
            path,
            json.dumps(self.content).encode("utf-8"),
            makepath=True,
            ephemeral=True,
            sequence=True,
            # Also return the zstat, which is necessary to successfully update
            # the component.
            include_data=True,
        )

    def updateFromDict(self, data):
        self.content.update(data)

    @classmethod
    def fromDict(cls, client, hostname, data):
        component = cls(client, hostname)
        component.updateFromDict(data)
        return component

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.content}>"


class SchedulerComponent(BaseComponent):
    kind = "scheduler"


class ExecutorComponent(BaseComponent):
    kind = "executor"

    def __init__(self, client, hostname):
        super().__init__(client, hostname)
        self.initial_state = {
            "accepting_work": False,
            "zone": None,
            "allow_unzoned": False,
            "process_merge_jobs": False,
        }
        self.content.update(self.initial_state)


class MergerComponent(BaseComponent):
    kind = "merger"


class FingerGatewayComponent(BaseComponent):
    kind = "fingergw"


class WebComponent(BaseComponent):
    kind = "web"


class ComponentRegistry(ZooKeeperBase):

    log = logging.getLogger("zuul.zk.components.ZooKeeperComponentRegistry")

    COMPONENT_CLASSES = {
        "scheduler": SchedulerComponent,
        "executor": ExecutorComponent,
        "merger": MergerComponent,
        "fingergw": FingerGatewayComponent,
        "web": WebComponent,
    }

    def __init__(self, client):
        super().__init__(client)

        self.client = client
        self._component_tree = None
        # kind -> hostname -> component
        self._cached_components = defaultdict(dict)

        # If we are already connected when the class is instantiated, directly
        # call the onConnect callback.
        if self.client.connected:
            self._onConnect()

    def _onConnect(self):
        self._component_tree = TreeCache(self.kazoo_client, COMPONENTS_ROOT)
        self._component_tree.listen_fault(self._cacheFaultListener)
        self._component_tree.listen(self._componentCacheListener)
        self._component_tree.start()

    def _onDisconnect(self):
        if self._component_tree is not None:
            self._component_tree.close()
            # Explicitly unset the TreeCache, otherwise we might leak
            # open connections/ports.
            self._component_tree = None

    def all(self, kind=None):
        if kind is None:
            return [kind.values() for kind in self._cached_components.keys()]

        # Filter the cached components for the given kind
        return self._cached_components.get(kind, {}).values()

    def _cacheFaultListener(self, e):
        self.log.exception(e)

    def _componentCacheListener(self, event):
        path = None
        if hasattr(event.event_data, "path"):
            path = event.event_data.path

        # Ignore events without path
        if not path:
            return

        # Ignore root node
        if path == COMPONENTS_ROOT:
            return

        # Ignore lock nodes
        if "__lock__" in path:
            return

        # Ignore unrelated events
        if event.event_type not in (
            TreeEvent.NODE_ADDED,
            TreeEvent.NODE_UPDATED,
            TreeEvent.NODE_REMOVED,
        ):
            return

        # Split the path into segments to find out the type of event (e.g.
        # a subnode was created or the buildnode itself was touched).
        segments = self._getSegments(path)

        # The segments we are interested in should look something like this:
        # <kind> / <hostname>
        if len(segments) < 2:
            # Ignore events that don't touch a component
            return

        kind = segments[0]
        hostname = segments[1]

        self.log.debug(
            "Got cache update event %s for path %s", event.event_type, path
        )

        if event.event_type in (TreeEvent.NODE_UPDATED, TreeEvent.NODE_ADDED):
            # Ignore events without data
            if not event.event_data.data:
                return

            # Perform an in-place update of the cached component (if any)
            component = self._cached_components.get(kind, {}).get(hostname)
            d = json.loads(event.event_data.data.decode("utf-8"))

            if component:
                if (
                    event.event_data.stat.version
                    <= component._zstat.version
                ):
                    # Don't update to older data
                    return
                component.updateFromDict(d)
                component._zstat = event.event_data.stat
            else:
                # Create a new component from the data structure
                # Get the correct kind of component
                # TODO (felix): KeyError on unknown component type?
                component_cls = self.COMPONENT_CLASSES[kind]
                component = component_cls.fromDict(self.client, hostname, d)
                component.path = path
                component._zstat = event.event_data.stat

            self._cached_components[kind][hostname] = component

        elif event.event_type == TreeEvent.NODE_REMOVED:
            try:
                del self._cached_components[kind][hostname]
            except KeyError:
                # If it's already gone, don't care
                pass

    def _getSegments(self, path):
        if path.startswith(COMPONENTS_ROOT):
            # Normalize the path (remove the root part)
            path = path[len(COMPONENTS_ROOT) + 1:]

        return path.split("/")
