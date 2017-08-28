##### VPP SETUP #####

CMD_VPP_STOP_SERVICE = 'systemctl stop vpp.service'
CMD_VPP_DISABLE = 'systemctl disable vpp.service'

# 'sleep 1' ensures that VPP has enough time to start
CMD_VPP_START = '''
flock /tmp/vppctl.lock -c "systemctl start vpp"
'''
CMD_VPP_STOP = '''
flock /tmp/vppctl.lock -c "systemctl stop vpp"
'''
#killall -9 vpp_main || true
CMD_VPP_ENABLE_PLUGIN = 'vppctl_wrapper {plugin} control start'

##### VPP INTERFACES #####

CMD_VPP_CREATE_IFACE = '''
# Create vpp interface from {vpp_interface.parent.device_name} with mac {vpp_interface.parent.mac_address}
vppctl_wrapper create host-interface name {vpp_interface.parent.device_name} hw-addr {vpp_interface.parent.mac_address}
vppctl_wrapper set interface state {vpp_interface.device_name} up
'''

# It is important to pass the mac address so that it does not get randomly
# generated by VPP, preventing any reboot of VPP and recreation of commands
CMD_VPP_CREATE_MEMIFACE = '''
# Create vpp interface from shared_memory
vppctl_wrapper create memif key {key} socket {vpp_interface.parent.path_unix_socket}{vpp_interface.parent.socket_name} hw-addr {vpp_interface.parent.mac_address} {master_slave}
'''
CMD_VPP_SET_IP = 'vppctl_wrapper set int ip address {device_name} {ip_address}/{prefix_len}'
CMD_VPP_SET_UP = 'vppctl_wrapper set int state {netdevice.device_name} {state}'

##### VPP IP ROUTING #####

CMD_VPP_ADD_ARP = 'vppctl_wrapper set ip arp static {route.interface.vppinterface.device_name} {route.ip_address} {route.mac_address}'
CMD_VPP_DEL_ARP = 'vppctl_wrapper set ip arp del static {route.interface.vppinterface.device_name} {route.ip_address} {route.mac_address}'
CMD_VPP_ADD_ROUTE = 'vppctl_wrapper ip route add {route.ip_address}/{route.ip_address.prefix_len} via {route.interface.vppinterface.device_name}'
CMD_VPP_DEL_ROUTE = 'vppctl_wrapper ip route del {route.ip_address}/{route.ip_address.prefix_len} via {route.interface.vppinterface.device_name}'
CMD_VPP_ADD_ROUTE_GW = 'vppctl_wrapper ip route add {route.ip_address}/{route.ip_address.prefix_len} via {route.gateway} {route.interface.vppinterface.device_name}'
CMD_VPP_DEL_ROUTE_GW = 'vppctl_wrapper ip route del {route.ip_address}/{route.ip_address.prefix_len} via {route.gateway} {route.interface.vppinterface.device_name}'
