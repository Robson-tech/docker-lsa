import unittest
from unittest.mock import patch
import time

from router import Router


class TestRouterNeighbors(unittest.TestCase):
    def test_router_a(self):
        neighbors = {
            'B': ('10.0.0.2', 5000),
            'C': ('10.0.0.3', 5000)
        }
        router = Router(router_id='A', neighbors=neighbors)
        expected_links = {'B': 1, 'C': 1}
        self.assertIn('A', router._lsdb)
        self.assertEqual(router._lsdb['A']['links'], expected_links)

    def test_router_b(self):
        neighbors = {
            'A': ('10.0.0.1', 5000),
            'C': ('10.0.0.3', 5000),
            'D': ('10.0.0.4', 5000),
            'E': ('10.0.0.5', 5000)
        }
        router = Router(router_id='B', neighbors=neighbors)
        expected_links = {'A': 1, 'C': 1, 'D': 1, 'E': 1}
        self.assertIn('B', router._lsdb)
        self.assertEqual(router._lsdb['B']['links'], expected_links)

    def test_router_c(self):
        neighbors = {
            'A': ('10.0.0.1', 5000),
            'B': ('10.0.0.2', 5000),
            'D': ('10.0.0.4', 5000)
        }
        router = Router(router_id='C', neighbors=neighbors)
        expected_links = {'A': 1, 'B': 1, 'D': 1}
        self.assertIn('C', router._lsdb)
        self.assertEqual(router._lsdb['C']['links'], expected_links)

    def test_router_d(self):
        neighbors = {
            'B': ('10.0.0.2', 5000),
            'C': ('10.0.0.3', 5000),
            'E': ('10.0.0.5', 5000)
        }
        router = Router(router_id='D', neighbors=neighbors)
        expected_links = {'B': 1, 'C': 1, 'E': 1}
        self.assertIn('D', router._lsdb)
        self.assertEqual(router._lsdb['D']['links'], expected_links)

    def test_router_e(self):
        neighbors = {
            'B': ('10.0.0.2', 5000),
            'D': ('10.0.0.4', 5000)
        }
        router = Router(router_id='E', neighbors=neighbors)
        expected_links = {'B': 1, 'D': 1}
        self.assertIn('E', router._lsdb)
        self.assertEqual(router._lsdb['E']['links'], expected_links)


class TestRouterInitialization(unittest.TestCase):

    def test_initial_lsa_generation(self):
        neighbors = {'R2': ('127.0.0.1', 6001), 'R3': ('127.0.0.1', 6002)}
        router = Router(router_id='R1', neighbors=neighbors)
        self.assertIn('R1', router._lsdb)
        self.assertEqual(router._lsdb['R1']['links'], {'R2': 1, 'R3': 1})
        self.assertEqual(router._lsdb['R1']['sequence'], 1)

    def test_lsdb_contains_only_self_after_init(self):
        router = Router(router_id='R1', neighbors={'R2': ('127.0.0.1', 6001)})
        self.assertListEqual(list(router._lsdb.keys()), ['R1'])

    def test_seen_lsas_includes_initial_lsa(self):
        router = Router(router_id='R1', neighbors={'R2': ('127.0.0.1', 6001)})
        self.assertIn(('R1', 1), router._seen_lsas)

    def test_sequence_number_increment_on_lsa_creation(self):
        router = Router(router_id='R1', neighbors={'R2': ('127.0.0.1', 6001)})
        seq_before = router._sequence_number
        packet = router._create_lsa_packet()
        self.assertEqual(packet['sequence'], seq_before + 1)
        self.assertEqual(router._sequence_number, seq_before + 1)

    def test_lsa_packet_structure(self):
        router = Router(router_id='R1', neighbors={'R2': ('127.0.0.1', 6001)})
        lsa = router._create_lsa_packet()
        self.assertEqual(lsa['type'], 'lsa')
        self.assertEqual(lsa['router_id'], 'R1')
        self.assertIn('sequence', lsa)
        self.assertIn('payload', lsa)
        self.assertEqual(lsa['payload']['links'], {'R2': 1})

    def test_router_with_no_neighbors(self):
        router = Router(router_id='R1', neighbors={})
        lsa = router._create_lsa_packet()
        self.assertEqual(lsa['payload']['links'], {})


class TestRouterCommunication(unittest.TestCase):
    def setUp(self):
        """Define os roteadores e os vizinhos simulados em localhost"""
        self.r1_neighbors = {'R2': ('127.0.0.1', 6001)}
        self.r2_neighbors = {'R1': ('127.0.0.1', 6000)}

        # Inicia o patch globalmente para todas as instâncias de Router
        patcher = patch.object(Router, '_process_lsa')
        self.mock_process = patcher.start()
        self.addCleanup(patcher.stop)

        # Função para validar o conteúdo do pacote
        def imprimir_lsa(packet):
            self.assertIn('type', packet)
            self.assertIn('router_id', packet)
            self.assertIn('sequence', packet)
            self.assertIn('payload', packet)
            self.assertIn('links', packet['payload'])
            self.assertEqual(packet['type'], 'lsa')

        self.mock_process.side_effect = imprimir_lsa

    def test_lsa_communication(self):
        """Verifica se R1 envia LSA que R2 consegue receber"""
        self.r1 = Router(router_id='R1', neighbors=self.r1_neighbors, listen_port=6000)
        self.r2 = Router(router_id='R2', neighbors=self.r2_neighbors, listen_port=6001)

        self.r1.start()
        self.r2.start()
        
        # Espera o envio + recebimento ocorrer (1 ciclo de 5s do LSA)
        time.sleep(6)

        self.r1.stop()
        self.r2.stop()

        self.assertFalse(self.r1._running)
        self.assertFalse(self.r2._running)
        self.assertIsNotNone(self.r1.receiver_thread)
        self.assertIsNotNone(self.r2.receiver_thread)

    def tearDown(self):
        """Garante que as threads são encerradas mesmo se o teste falhar"""
        self.r1._running = False
        self.r2._running = False
        try:
            self.r1.receiver_thread.join(timeout=1)
            self.r1.sender_thread.join(timeout=1)
        except:
            pass
        try:
            self.r2.receiver_thread.join(timeout=1)
            self.r2.sender_thread.join(timeout=1)
        except:
            pass


class TestLSDBUpdate(unittest.TestCase):
    def setUp(self):
        self.router = Router(
            router_id='R1',
            neighbors={'R2': ('127.0.0.1', 5000)},
            listen_port=6000
        )

    @patch.object(Router, '_run_dijkstra')
    def test_process_received_lsa_updates_lsdb(self, mock_dijkstra):
        # Simula um pacote LSA vindo de R2
        lsa_packet = {
            'router_id': 'R2',
            'sequence': 1000,
            'links': {'R1': 1, 'R3': 2}
        }

        # Executa o método que deve atualizar a LSDB
        self.router._process_received_lsa(lsa_packet)

        # Verifica se os dados foram armazenados corretamente
        self.assertIn('R2', self.router._lsdb)
        self.assertEqual(self.router._lsdb['R2']['sequence'], 1000)
        self.assertEqual(self.router._lsdb['R2']['links'], {'R1': 1, 'R3': 2})

        # Verifica se _run_dijkstra foi chamado após a atualização
        mock_dijkstra.assert_called_once()

    @patch.object(Router, '_run_dijkstra')
    def test_outdated_lsa_is_ignored(self, mock_dijkstra):
        # Atualiza LSDB com sequência maior
        self.router._update_lsdb('R2', 2000, {'R1': 1})

        # Tenta processar LSA com sequência menor (deve ser ignorado)
        outdated_lsa = {
            'router_id': 'R2',
            'sequence': 1500,
            'links': {'R1': 1, 'R3': 2}
        }

        self.router._process_received_lsa(outdated_lsa)

        # LSDB não deve mudar
        self.assertEqual(self.router._lsdb['R2']['sequence'], 2000)
        # _run_dijkstra não deve ser chamado
        mock_dijkstra.assert_not_called()


class TestLSAExchangeIntegration(unittest.TestCase):
    @patch.object(Router, '_run_dijkstra')  # mocka dijkstra para não interferir no teste
    def test_lsa_exchange_and_lsdb_update(self, _):
        # Definindo os vizinhos de cada roteador
        r1_neighbors = {'R2': ('127.0.0.1', 7001)}
        r2_neighbors = {
            'R1': ('127.0.0.1', 7000),
            'R3': ('127.0.0.1', 7002)
        }
        r3_neighbors = {'R2': ('127.0.0.1', 7001)}

        # Criando instâncias
        r1 = Router(router_id='R1', neighbors=r1_neighbors, listen_port=7000)
        r2 = Router(router_id='R2', neighbors=r2_neighbors, listen_port=7001)
        r3 = Router(router_id='R3', neighbors=r3_neighbors, listen_port=7002)

        # Iniciando os roteadores
        r1.start()
        r2.start()
        r3.start()

        # Espera tempo suficiente para 2 ciclos de envio (~5s cada)
        time.sleep(12)

        # Parando os roteadores
        r1.stop()
        r2.stop()
        r3.stop()

        # Verificações das LSDBs — todos devem conhecer os 3 roteadores
        for router in [r1, r2, r3]:
            lsdb = router._lsdb
            router.print_lsdb()
            with self.subTest(router=router._router_id):
                self.assertIn('R1', lsdb, f"{router._router_id} não recebeu LSA de R1")
                self.assertIn('R2', lsdb, f"{router._router_id} não recebeu LSA de R2")
                self.assertIn('R3', lsdb, f"{router._router_id} não recebeu LSA de R3")





if __name__ == '__main__':
    unittest.main()
