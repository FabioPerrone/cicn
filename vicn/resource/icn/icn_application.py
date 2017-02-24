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

from vicn.resource.linux.application    import LinuxApplication 
from vicn.core.attribute                import Attribute
from netmodel.model.type                import Integer

ICN_SUITE_CCNX_1_0=0
ICN_SUITE_NDN=1

class ICNApplication(LinuxApplication):
    """
    Resource: ICNApplication
    """

    protocol_suites = Attribute(Integer, 
            description = 'Protocol suites supported by the application',
            default = lambda self: self._def_protocol_suite())

    def _def_protocol_suite(self):
        return -1

