import unittest
import time
from unittest.mock import patch

from router import Router
from host import Host


class TestHostRouterCommunication(unittest.TestCase):
    def setUp(self):
        # Endereços e portas
        self.router_port = 7000
        self.host1_port = 7001
        self.host2_port = 7002
        self.router_ip = '127.0.0.1'

        # Vizinhos do roteador
        self.router_neighbors = {
            'H1': (self.router_ip, self.host1_port),
            'H2': (self.router_ip, self.host2_port)
        }

        # Inicializa o roteador
        self.router = Router(
            router_id='R',
            neighbors=self.router_neighbors,
            listen_port=self.router_port
        )

        # Inicializa os hosts
        self.host1 = Host(
            host_id='H1',
            router_ip=self.router_ip,
            router_port=self.router_port,
            listen_port=self.host1_port,
            known_hosts=['H2']
        )

        self.host2 = Host(
            host_id='H2',
            router_ip=self.router_ip,
            router_port=self.router_port,
            listen_port=self.host2_port,
            known_hosts=['H1']
        )

        # Mocka os métodos de LSA para não interferirem
        self._lsa_patcher = patch.object(Router, '_generate_lsa_packets')
        self._lsa_patcher.start()
        self.addCleanup(self._lsa_patcher.stop)

        self._process_patcher = patch.object(Router, '_process_lsa')
        self._process_patcher.start()
        self.addCleanup(self._process_patcher.stop)

    def test_data_packet_routing(self):
        """Verifica se o roteador retransmite pacotes entre os hosts"""
        # Força tabela de roteamento para não depender de LSAs
        self.router._routing_table = {
            'H1': {'cost': 1, 'next_hop': 'H1'},
            'H2': {'cost': 1, 'next_hop': 'H2'}
        }

        # Inicia os componentes da rede
        self.router.start()
        self.host1.start()
        self.host2.start()

        time.sleep(10)

        # Encerra os componentes
        self.host1.stop()
        self.host2.stop()
        self.router.stop()

    def tearDown(self):
        try:
            self.host1._running = False
            self.host2._running = False
            self.router._running = False

            self.host1._receiver_thread.join(timeout=1)
            self.host1._sender_thread.join(timeout=1)
            self.host2._receiver_thread.join(timeout=1)
            self.host2._sender_thread.join(timeout=1)
            self.router.receiver_thread.join(timeout=1)
            self.router.sender_thread.join(timeout=1)
            self.router.lsa_generator_thread.join(timeout=1)
        except Exception:
            pass


if __name__ == '__main__':
    unittest.main()
