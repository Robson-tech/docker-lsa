import unittest
import threading
import socket
import time
from unittest.mock import patch

from router import Router


class TestRouter(unittest.TestCase):
    def setUp(self):
        """Configura um roteador básico para os testes"""
        self.router = Router(router_id="R1", neighbors={}, listen_port=5001)
        self.sample_packet = {
            'type': 'data',
            'sequence': 1,
            'source': 'H1',
            'destination': 'H2',
            'payload': {'content': 'Test message'}
        }

    def test_initialization(self):
        """Testa a inicialização básica do roteador"""
        self.assertEqual(self.router._router_id, "R1")
        self.assertEqual(self.router._listen_port, 5001)
        self.assertEqual(self.router._sequence_number, 0)
        self.assertTrue(isinstance(self.router._lock, type(threading.Lock())))

    def test_initial_routing_structures(self):
        """Testa se as estruturas de roteamento são inicializadas corretamente"""
        self.router._initialize_routing_structures()
        self.assertIn(self.router._router_id, self.router._lsdb)
        self.assertEqual(self.router._lsdb[self.router._router_id]['sequence'], 0)

    @patch('socket.socket')
    def test_start_stop(self, mock_socket):
        """Testa o início e parada das threads do roteador"""
        self.router.start()
        self.assertTrue(self.router._running)
        self.assertTrue(self.router.receiver_thread.is_alive())
        
        self.router.stop()
        self.assertFalse(self.router._running)
        self.assertFalse(self.router.receiver_thread.is_alive())

    def test_create_lsa_packet(self):
        """Testa a criação de pacotes LSA"""
        packet = self.router._create_lsa_packet()
        self.assertEqual(packet['type'], 'lsa')
        self.assertEqual(packet['sequence'], 1)
        self.assertEqual(packet['source'], 'R1')
        self.assertEqual(self.router._sequence_number, 1)

    def test_update_lsdb(self):
        """Testa a atualização da LSDB"""
        test_links = {'R2': 1, 'R3': 2}
        self.router._update_lsdb('R2', 1, test_links)
        
        self.assertIn('R2', self.router._lsdb)
        self.assertEqual(self.router._lsdb['R2']['links'], test_links)
        self.assertEqual(self.router._lsdb['R2']['sequence'], 1)

    def test_process_lsa_new(self):
        """Testa o processamento de um novo LSA"""
        lsa = {
            'type': 'lsa',
            'sequence': 1,
            'source': 'R2',
            'payload': {'links': {'R1': 1, 'R3': 1}}
        }
        
        with patch.object(self.router, '_run_dijkstra') as mock_dijkstra:
            self.router._process_lsa(lsa)
            
            self.assertIn('R2', self.router._lsdb)
            self.assertEqual(self.router._lsdb['R2']['sequence'], 1)
            mock_dijkstra.assert_called_once()

    def test_process_lsa_old(self):
        """Testa o processamento de um LSA antigo"""
        lsa = {
            'type': 'lsa',
            'sequence': 1,
            'source': 'R2',
            'payload': {'links': {'R1': 1}}
        }
        
        # Primeiro processamento (deve aceitar)
        self.router._process_lsa(lsa)
        
        # Segundo processamento (deve ignorar)
        with patch.object(self.router, '_run_dijkstra') as mock_dijkstra:
            self.router._process_lsa(lsa)
            mock_dijkstra.assert_not_called()

    def test_run_dijkstra(self):
        """Testa o algoritmo de Dijkstra com uma topologia simples"""
        # Configura uma topologia simples: R1 -- R2 -- R3
        self.router._lsdb = {
            'R2': {'sequence': 1, 'links': {'R1': 1, 'R3': 1}, 'timestamp': time.time()},
            'R3': {'sequence': 1, 'links': {'R2': 1}, 'timestamp': time.time()}
        }
        self.router._neighbors = {'R2': ('192.168.1.2', 5002)}
        
        self.router._run_dijkstra()
        
        # Verifica a tabela de roteamento resultante
        self.assertEqual(self.router._routing_table['R2']['next_hop'], 'R2')
        self.assertEqual(self.router._routing_table['R2']['cost'], 1)
        self.assertEqual(self.router._routing_table['R3']['next_hop'], 'R2')
        self.assertEqual(self.router._routing_table['R3']['cost'], 2)

    @patch('socket.socket')
    def test_process_data_packet_known_source(self, mock_socket):
        """Testa o processamento de pacotes de origem conhecida"""
        self.router._neighbors = {'H1': ('192.168.1.10', 6001)}
        self.router._routing_table = {'H2': {'next_hop': 'H1', 'cost': 1}}
        
        with patch.object(self.router, '_outgoing_queue') as mock_queue:
            self.router._process_data_packet(self.sample_packet)
            self.assertEqual(mock_queue.append.call_count, 2)  # ACK + encaminhamento

    def test_process_data_packet_unknown_source(self):
        """Testa o processamento de pacotes de origem desconhecida"""
        packet = self.sample_packet.copy()
        packet['source_ip'] = '192.168.1.10'
        packet['source_port'] = 6001
        
        self.router._process_data_packet(packet)
        
        # Verifica se o novo vizinho foi adicionado
        self.assertIn('H1', self.router._neighbors)
        self.assertEqual(self.router._neighbors['H1'], ('192.168.1.10', 6001))
        self.assertIn('H1', self.router._routing_table)

    def test_format_tables(self):
        """Testa a formatação das tabelas de roteamento e LSDB"""
        self.router._lsdb = {
            'R1': {'sequence': 1, 'links': {'R2': 1}, 'timestamp': time.time()}
        }
        self.router._routing_table = {
            'R2': {'next_hop': 'R2', 'cost': 1}
        }
        
        lsdb_table = self.router.get_lsdb_table_formatted()
        routing_table = self.router.get_routing_table_formatted()
        
        self.assertIn('R1', lsdb_table)
        self.assertIn('R2', routing_table)
        self.assertIn('┌───', lsdb_table)  # Verifica bordas da tabela
        self.assertIn('└───', routing_table)

    def test_parse_neighbors(self):
        """Testa o parsing de vizinhos a partir de argumentos"""
        neighbors_list = ["R2:192.168.1.2:5002", "R3:192.168.1.3:5003"]
        result = Router.parse_neighbors(neighbors_list)
        
        self.assertEqual(result, {
            'R2': ('192.168.1.2', 5002),
            'R3': ('192.168.1.3', 5003)
        })

    @patch('socket.socket')
    def test_send_packets_retry(self, mock_socket):
        """Testa a lógica de retransmissão de pacotes"""
        mock_socket.return_value.sendto.side_effect = [socket.error, None]  # Falha primeiro, depois sucesso
        
        self.router._pending_acks = {
            1: ({'type': 'data'}, '192.168.1.2', 5002, time.time()-3, 0)  # Pacote expirado
        }
        
        self.router._send_packets()
        self.assertEqual(mock_socket.return_value.sendto.call_count, 2)  # Tentativa + retransmissão

    def tearDown(self):
        """Garante que o roteador é parado após cada teste"""
        if hasattr(self.router, '_running') and self.router._running:
            self.router.stop()


if __name__ == '__main__':
    unittest.main()