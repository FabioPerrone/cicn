#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (c) 2017 Cisco and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import logging
import shlex
import time

# Suppress logging from pylxd dependency on ws4py 
# (this needs to be included before pylxd)
from ws4py import configure_logger
configure_logger(level=logging.ERROR)
import pylxd

from netmodel.model.type            import String, Integer, Bool, Self
from vicn.core.address_mgr          import AddressManager
from vicn.core.attribute            import Attribute, Reference, Multiplicity
from vicn.core.commands             import ReturnValue
from vicn.core.exception            import ResourceNotFound
from vicn.core.requirement          import Requirement
from vicn.core.resource_mgr         import wait_resource_task
from vicn.core.task                 import task, inline_task, BashTask
from vicn.resource.linux.net_device import NetDevice
from vicn.resource.node             import Node
from vicn.resource.vpp.scripts      import APPARMOR_VPP_PROFILE

log = logging.getLogger(__name__)

# Default name of VICN management/monitoring interface
DEFAULT_LXC_NETDEVICE = 'eth0'

# Default remote server (pull mode only)
DEFAULT_SOURCE_URL      = 'https://cloud-images.ubuntu.com/releases/'

# Default protocol used to download images (lxd or simplestreams)
DEFAULT_SOURCE_PROTOCOL = 'simplestreams'

# Commands used to interact with LXD (in addition to pylxd bindings)
CMD_GET_PID='lxc info {container.name} | grep Pid | cut -d " " -f 2'

# Type: ContainerName
ContainerName = String(max_size = 64, ascii = True, 
        forbidden = ('/', ',', ':'))

class LxcContainer(Node):
    """
    Resource: LxcContainer

    Todo:
      - Remove VPP dependency
      - The bridge is not strictly needed, but we currently have no automated
      way to determine whether we need it or not
      - The management interface should be added by VICN, not part of the
      resource, and its name should be determined automatically.
    """

    architecture = Attribute(String, description = 'Architecture',
            default = 'x86_64')
    container_name = Attribute(ContainerName, 
            description = 'Name of the container',
            default = Reference(Self, 'name'))
    ephemeral = Attribute(Bool, description = 'Ephemeral container flag',
            default = False)
    node = Attribute(Node, 
            description = 'Node on which the container is running',
            mandatory = True,
            requirements = [
                # We need the hypervisor setup to be able to check for the
                # container; more generally, all dependencies
                Requirement('lxd_hypervisor'), # not null
                # The bridge is not strictly needed, but we currently have
                # no automated way to determine whether we need it or not
                Requirement('bridge'),
                # A DNS server is required to provide internet connectivity to
                # the containers
                Requirement('dns_server'),
            ])
    profiles = Attribute(String, multiplicity = Multiplicity.OneToMany, 
            default = ['default'])
    image = Attribute(String, description = 'image', default = None)
    is_image = Attribute(Bool, defaut = False)
    pid = Attribute(Integer, description = 'PID of the container')

    #-------------------------------------------------------------------------- 
    # Constructor / Accessors
    #-------------------------------------------------------------------------- 

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._container = None

    #-------------------------------------------------------------------------- 
    # Resource lifecycle
    #-------------------------------------------------------------------------- 

    @inline_task
    def __initialize__(self):
        """
        We need to intanciate VPPHost before container creation.
        """
        self.node_with_kernel = Reference(self, 'node')

        # We automatically add the management/monitoring interface
        self._host_interface = NetDevice(node = self, 
                owner = self,
                monitored = False,
                device_name = DEFAULT_LXC_NETDEVICE)
        self._state.manager.commit_resource(self._host_interface)

        for iface in self.interfaces:
            if iface.get_type() == "dpdkdevice":
                self.node.vpp_host.dpdk_devices.append(iface.pci_address)

        if 'vpp' in self.profiles:
            dummy = self.node.vpp_host.uio_devices

    @task
    def __get__(self):
        client = self.node.lxd_hypervisor.client
        try:
            self._container = client.containers.get(self.name)
        except pylxd.exceptions.NotFound:
            raise ResourceNotFound

    def __create__(self):
        """
        Make sure vpp_host is instanciated before starting the container.
        """
        wait_vpp_host = wait_resource_task(self.node.vpp_host)
        create = self._create_container()
        start = self.__method_start__()
        return wait_vpp_host > (create > start)

    @task
    def _create_container(self):
        container = self._get_container_description()
        log.debug('Container description: {}'.format(container))
        client = self.node.lxd_hypervisor.client
        self._container = client.containers.create(container, wait=True)
        self._container.start(wait = True)

    def _get_container_description(self):
        # Base configuration
        container = {
            'name'          : self.container_name, 
            'architecture'  : self.architecture,
            'ephemeral'     : self.ephemeral,  
            'profiles'      : ['default'],
            'config'        : {},
            'devices'       : {},
        }

        # DEVICES

        devices = {}
        # FIXME Container profile support is provided by setting changes into
        # configuration (currently only vpp profile is supported)
        for profile in self.profiles:
            if profile == 'vpp':
                # Set the new apparmor profile. This will be created in VPP
                # application 
                # Mount hugetlbfs in the container.
                container['config']['raw.lxc'] = APPARMOR_VPP_PROFILE
                container['config']['security.privileged'] = 'true'

                for device in self.node.vpp_host.uio_devices:
                    container['devices'][device] = {
                        'path' : '/dev/{}'.format(device), 
                        'type' : 'unix-char' }

        # NETWORK (not for images) 

        if not self.is_image:
            container['config']['user.network_mode'] = 'link-local'
            device = {
                'type'      : 'nic',
                'name'      : self.host_interface.device_name,
                'nictype'   : 'bridged',
                'parent'    : self.node.bridge.device_name,
            }
            device['hwaddr'] = AddressManager().get_mac(self)
            prefix = 'veth-{}'.format(self.container_name)
            device['host_name'] = AddressManager().get('device_name', self, 
                    prefix = prefix, scope = prefix)

            container['devices'][device['name']] = device
            

        # SOURCE

        image_names = [alias['name'] for alias in self.node.lxd_hypervisor.aliases]
        image_exists = self.image is not None and self.image in image_names

        if image_exists:
            container['source'] = {
                'type'      : 'image',
                'mode'      : 'local',
                'alias'     : self.image,
            }
        else:
            container['source'] = {
                'type'      : 'image',
                'mode'      : 'pull',
                'server'    : DEFAULT_SOURCE_URL,
                'protocol'  : DEFAULT_SOURCE_PROTOCOL,
                'alias'     : self.dist,
            }

        log.info('Creating container: {}'.format(container))
        return container

    @task
    def __delete__(self):
        log.info("Delete container {}".format(self.container_name))
        self.node.lxd_hypervisor.client.containers.remove(self.name)

    #--------------------------------------------------------------------------
    # Attributes
    #--------------------------------------------------------------------------

    def _get_pid(self):
        """
        Attribute: pid (getter)
        """
        return BashTask(self.node, CMD_GET_PID, {'container': self}, 
                parse = lambda rv: {'pid': rv.stdout.strip()})

    #--------------------------------------------------------------------------
    # Methods
    #--------------------------------------------------------------------------

    @task
    def __method_start__(self):
        """
        Method: Start the container
        """
        self._container.start(wait = True)

    @task
    def __method_stop__(self):
        """
        Method: Stop the container
        """
        self._container.stop(wait = True)

    @task
    def __method_to_image__(self):
        """
        Returns:
            Image metadata as returned by LXD REST API.
        """
        publish_description = {
            "public": True,
            "properties": {
                "os": "Ubuntu",
                "architecture": "x86_64",
                "description": "Image generated from container {}".format(
                        self.container_name),
            },
            "source": {
                "type": "container",  # One of "container" or "snapshot"
                "name": 'image-{}'.format(self.container_name),
            }
        }
        return self.node.lxd_hypervisor.publish_image(publish_description)

    #--------------------------------------------------------------------------
    # Node API
    #--------------------------------------------------------------------------

    def execute(self, command, output = False, as_root = False):
        """
        Executes a command on the node

        Params:
            output (bool) : Flag determining whether the method should return
                the output value.
            as_root (bool) : Flag telling whether the command should be
                executed as root.

        Returns:
            ReturnValue containing exit code, and eventually stdout and stderr.

        Raises
            Exception in case of error

        The node exposes an interface allowing command execution through LXD.
        We don't currently use an eventually available  SSH connection.
        """

        ret = self._container.execute(shlex.split(command))

        # NOTE: pylxd documents the return value as a tuple, while it is in
        # fact a ContainerExecuteResult object
        if not hasattr(ret, "exit_code"):
            log.error("LXD return value does not have an exit code. "
                    "Try installing pylxd>=2.2.2 with pip3")
            import sys; sys.exit(1)

        args = (ret.exit_code,)
        if output:
            args += (ret.stdout, ret.stderr)
        return ReturnValue(*args)
