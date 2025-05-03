import unittest
import time

from host import Host


class TestDirectHostCommunication(unittest.TestCase):
    def setUp(self):
        # H1 envia para H2 na porta 9002
        self.host1 = Host(
            host_id='H1',
            router_ip='127.0.0.1',
            router_port=9002,
            listen_port=9001,
            known_hosts=['H2']
        )

        # H2 envia para H1 na porta 9001
        self.host2 = Host(
            host_id='H2',
            router_ip='127.0.0.1',
            router_port=9001,
            listen_port=9002,
            known_hosts=['H1']
        )

        self.host1.start()
        self.host2.start()

    def test_message_exchange(self):
        # Espera tempo suficiente para troca de mensagens
        time.sleep(10)

    def tearDown(self):
        self.host1.stop()
        self.host2.stop()

if __name__ == '__main__':
    unittest.main()
