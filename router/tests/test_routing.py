import unittest
import time

from router import Router

class TestDijkstraRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Cria uma rede em topologia parcialmente conectada
        cls.router_a = Router(
            'A',
            neighbors={
                'B': ('127.0.0.1', 6001),
                'C': ('127.0.0.1', 6002)
            },
            listen_port=6000
        )
        cls.router_b = Router(
            'B',
            neighbors={
                'A': ('127.0.0.1', 6000),
                'D': ('127.0.0.1', 6003)
            },
            listen_port=6001
        )
        cls.router_c = Router(
            'C',
            neighbors={
                'A': ('127.0.0.1', 6000),
                'D': ('127.0.0.1', 6003)
            },
            listen_port=6002
        )
        cls.router_d = Router(
            'D',
            neighbors={
                'B': ('127.0.0.1', 6001),
                'C': ('127.0.0.1', 6002)
            },
            listen_port=6003
        )

        # Inicia todos os roteadores
        for router in [cls.router_a, cls.router_b, cls.router_c, cls.router_d]:
            router.start()

        # Aguarda troca de LSAs e cálculo das rotas
        time.sleep(5)

    @classmethod
    def tearDownClass(cls):
        for router in [cls.router_a, cls.router_b, cls.router_c, cls.router_d]:
            router.stop()

    def test_router_a_routing_table(self):
        expected = {
            'B': {'next_hop': 'B', 'cost': 1},
            'C': {'next_hop': 'C', 'cost': 1},
            'D': {'next_hop': 'B', 'cost': 2}  # ou via C
        }
        self._compare_routing_table(self.router_a, expected)

    def test_router_b_routing_table(self):
        expected = {
            'A': {'next_hop': 'A', 'cost': 1},
            'D': {'next_hop': 'D', 'cost': 1},
            'C': {'next_hop': 'A', 'cost': 2}  # via A
        }
        self._compare_routing_table(self.router_b, expected)

    def test_router_c_routing_table(self):
        expected = {
            'A': {'next_hop': 'A', 'cost': 1},
            'D': {'next_hop': 'D', 'cost': 1},
            'B': {'next_hop': 'A', 'cost': 2}  # via A
        }
        self._compare_routing_table(self.router_c, expected)

    def test_router_d_routing_table(self):
        expected = {
            'B': {'next_hop': 'B', 'cost': 1},
            'C': {'next_hop': 'C', 'cost': 1},
            'A': {'next_hop': 'B', 'cost': 2}  # ou via C
        }
        self._compare_routing_table(self.router_d, expected)

    def _compare_routing_table(self, router, expected_table):
        actual_table = {}
        with router._lock:
            for dest, route in router._routing_table.items():
                actual_table[dest] = {'next_hop': route['next_hop'], 'cost': route['cost']}
        self.assertEqual(actual_table, expected_table)

if __name__ == '__main__':
    unittest.main()
