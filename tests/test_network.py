import unittest
import threading
import time

from router import Router
from host import Host


class TestNetworkIntegration(unittest.TestCase):
    def setUp(self):
        """Configura uma rede com 3 roteadores e 2 hosts cada"""
        # Configuração dos roteadores
        self.routers = {
            'R1': Router(router_id='R1', router_ip='192.168.1.27', listen_port=5001, neighbors={
                'H1': ('192.168.1.27', 7001),
                'H2': ('192.168.1.27', 7002),
                'R2': ('192.168.1.27', 5002),
                'R3': ('192.168.1.27', 5003)
            }),
            'R2': Router(router_id='R2', router_ip='192.168.1.27', listen_port=5002, neighbors={
                'H3': ('192.168.1.27', 7003),
                'H4': ('192.168.1.27', 7004),
                'R1': ('192.168.1.27', 5001),
                'R3': ('192.168.1.27', 5003)
            }),
            'R3': Router(router_id='R3', router_ip='192.168.1.27', listen_port=5003, neighbors={
                'H5': ('192.168.1.27', 7005),
                'H6': ('192.168.1.27', 7006),
                'R1': ('192.168.1.27', 5001),
                'R2': ('192.168.1.27', 5002)
            })
        }

        # Configuração dos hosts
        self.hosts = {
            'H1': Host(host_id='H1', router_ip='192.168.1.27', router_port=5001, known_hosts=['H2', 'H3', 'H4', 'H5', 'H6'], host_ip='192.168.1.27', listen_port=6001),
            'H2': Host(host_id='H2', router_ip='192.168.1.27', router_port=5001, known_hosts=['H1', 'H3', 'H4', 'H5', 'H6'], host_ip='192.168.1.27', listen_port=6002),
            'H3': Host(host_id='H3', router_ip='192.168.1.27', router_port=5002, known_hosts=['H1', 'H2', 'H4', 'H5', 'H6'], host_ip='192.168.1.27', listen_port=6003),
            'H4': Host(host_id='H4', router_ip='192.168.1.27', router_port=5002, known_hosts=['H1', 'H2', 'H3', 'H5', 'H6'], host_ip='192.168.1.27', listen_port=6004),
            'H5': Host(host_id='H5', router_ip='192.168.1.27', router_port=5003, known_hosts=['H1', 'H2', 'H3', 'H4', 'H6'], host_ip='192.168.1.27', listen_port=6005),
            'H6': Host(host_id='H6', router_ip='192.168.1.27', router_port=5003, known_hosts=['H1', 'H2', 'H3', 'H4', 'H5'], host_ip='192.168.1.27', listen_port=6006)
        }
    
    def test_host_communication(self):
        # Inicia todos os roteadores
        for router in self.routers.values():
            router.start()
        
        time.sleep(30)

        # Inicia todos os hosts
        for host in self.hosts.values():
            host.start()

    def tearDown(self):
        """Para todos os roteadores e hosts após os testes"""
        for router in self.routers.values():
            router.stop()

        for host in self.hosts.values():
            host.stop()


if __name__ == '__main__':
    unittest.main()
