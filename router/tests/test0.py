import threading
import socket
import json
import time
import heapq
from typing import Dict, Tuple, Optional, Any, Set, List
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class Packet:
    type: str  # 'lsa' ou 'data'
    router_id: str
    sequence: int = 0
    payload: Any = None
    dst: Optional[str] = None  # Apenas para pacotes de dados


class Router:
    def __init__(self, router_id: str, neighbors: Dict[str, Tuple[str, int]], listen_port: int = 5000):
        self._router_id = router_id
        self._neighbors = neighbors
        self._listen_port = listen_port
        self._lsdb: Dict[str, Dict[str, Any]] = {}  # Link State Database
        self._running = False
        self._lock = threading.Lock()
        self._routing_table: Dict[str, Dict[str, Any]] = {}
        self._sequence_number = 0
        self._seen_lsas: Set[Tuple[str, int]] = set()
        self._outgoing_queue: List[Tuple[Dict, str, int]] = []  # (packet, ip, port)
        
        # Inicializa a LSDB com o próprio roteador
        self._generate_initial_lsa()
    
    def start(self) -> None:
        """Inicia as threads de processamento"""
        self._running = True
        
        # Threads principais
        self.receiver_thread = threading.Thread(
            target=self._receive_packets,
            daemon=True
        )
        self.sender_thread = threading.Thread(
            target=self._send_packets,
            daemon=True
        )
        self.lsa_generator_thread = threading.Thread(
            target=self._generate_lsa_packets,
            daemon=True
        )

        self.receiver_thread.start()
        self.sender_thread.start()
        self.lsa_generator_thread.start()

        print(f"[Router {self._router_id}] Threads iniciadas")

    def stop(self) -> None:
        """Para todas as threads do roteador"""
        self._running = False
        self.receiver_thread.join()
        self.sender_thread.join()
        self.lsa_generator_thread.join()
        print(f"[Router {self._router_id}] Threads paradas")
    
    def print_lsdb(self) -> None:
        """
        Imprime a Link State Database (LSDB) em formato tabular.
        """
        print(f"\n[Router {self._router_id}] Link State Database (LSDB):")
        print(f"{'Roteador':<10} | {'Sequência':<20} | {'Enlaces (vizinho: custo)':<30}")
        print("-" * 70)
        with self._lock:
            for router_id, data in self._lsdb.items():
                links_str = ', '.join(f"{n}:{c}" for n, c in data['links'].items())
                print(f"{router_id:<10} | {data['sequence']:<20} | {links_str:<30}")
    
    def print_routing_table(self) -> None:
        """
        Imprime a tabela de roteamento (routing table) em formato tabular.
        """
        print(f"\n[Router {self._router_id}] Tabela de Roteamento:")
        print(f"{'Destino':<10} | {'Custo':<5} | {'Próximo Salto':<15}")
        print("-" * 40)
        with self._lock:
            for dest, info in self._routing_table.items():
                cost = info.get('cost', '?')
                next_hop = info.get('next_hop', '?')
                print(f"{dest:<10} | {cost:<5} | {next_hop:<15}")
    
    def _receive_packets(self) -> None:
        """Thread para receber todos os pacotes"""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(('0.0.0.0', self._listen_port))
            sock.settimeout(1.0)

            print(f"[Router {self._router_id}] Ouvindo pacotes na porta {self._listen_port}")

            while self._running:
                try:
                    data, addr = sock.recvfrom(1024)
                    packet = json.loads(data.decode())
                    self._handle_packet(packet, sock)
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"[Router {self._router_id}] Erro ao receber: {e}")
    
    def _send_packets(self) -> None:
        """Thread para enviar pacotes da fila de saída"""
        while self._running:
            if self._outgoing_queue:
                with self._lock:
                    packet, dest_ip, dest_port = self._outgoing_queue.pop(0)
                
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                        sock.sendto(json.dumps(packet).encode(), (dest_ip, dest_port))
                        print(f"[Router {self._router_id}] Pacote enviado para {dest_ip}:{dest_port}")
                except Exception as e:
                    print(f"[Router {self._router_id}] Falha no envio: {e}")
            
            time.sleep(0.01)  # Evita uso excessivo da CPU

    def _generate_initial_lsa(self) -> None:
        """Gera o LSA inicial do roteador"""
        initial_lsa = self._create_lsa_packet()
        self._update_lsdb(self._router_id, self._sequence_number, initial_lsa['payload']['links'])
        self._seen_lsas.add((self._router_id, self._sequence_number))
    
    def _create_lsa_packet(self) -> Dict:
        """Cria um novo pacote LSA"""
        self._sequence_number += 1
        return {
            'type': 'lsa',
            'router_id': self._router_id,
            'sequence': self._sequence_number,
            'payload': {
                'links': {n: 1 for n in self._neighbors.keys()}
            }
        }

    def _generate_lsa_packets(self) -> None:
        """Thread para gerar LSAs periódicos"""
        while self._running:
            lsa = self._create_lsa_packet()
            
            with self._lock:
                self._update_lsdb(self._router_id, lsa['sequence'], lsa['payload']['links'])
                self._seen_lsas.add((self._router_id, lsa['sequence']))
                
                # Agenda envio para todos os vizinhos
                for neighbor_id, (ip, port) in self._neighbors.items():
                    self._outgoing_queue.append((lsa, ip, port))
            
            time.sleep(30)  # Intervalo OSPF padrão
    
    def _handle_packet(self, packet: Dict, sock: socket.socket) -> None:
        """Processa pacotes recebidos de acordo com o tipo"""
        packet_type = packet.get('type')
        
        if packet_type == 'lsa':
            self._process_lsa(packet, sock)
        elif packet_type == 'data':
            self._process_data_packet(packet)
        else:
            print(f"[Router {self._router_id}] Tipo de pacote inválido: {packet_type}")

    def _process_lsa(self, lsa: Dict, sock: socket.socket) -> None:
        """Processa um LSA recebido e faz flooding controlado"""
        sender_id = lsa['router_id']
        sequence = lsa['sequence']
        links = lsa['payload']['links']
        
        with self._lock:
            # Verifica se é um LSA novo
            if (sender_id, sequence) in self._seen_lsas:
                return
                
            current_seq = self._lsdb.get(sender_id, {'sequence': -1})['sequence']
            if sequence <= current_seq:
                return
            
            # Atualiza a LSDB
            self._seen_lsas.add((sender_id, sequence))
            self._update_lsdb(sender_id, sequence, links)
            print(f"[Router {self._router_id}] LSDB atualizada com LSA de {sender_id}")
            
            # Agenda flooding para outros vizinhos
            self._schedule_flooding(lsa, except_neighbor=sender_id)
            
            # Recalcula rotas
            self._run_dijkstra()

    def _schedule_flooding(self, lsa: Dict, except_neighbor: Optional[str] = None) -> None:
        """Adiciona pacotes LSA na fila de saída para flooding"""
        with self._lock:
            for neighbor_id, (ip, port) in self._neighbors.items():
                if neighbor_id != except_neighbor:
                    self._outgoing_queue.append((lsa, ip, port))
    
    def _process_data_packet(self, packet: Dict) -> None:
        """Processa pacotes de dados com roteamento"""
        dst = packet.get('dst')
        
        if dst == self._router_id:
            print(f"[Router {self._router_id}] Pacote recebido: {packet.get('payload')}")
            return
        
        with self._lock:
            route = self._routing_table.get(dst)
            
        if route and route['next_hop'] in self._neighbors:
            ip, port = self._neighbors[route['next_hop']]
            self._outgoing_queue.append((packet, ip, port))
            print(f"[Router {self._router_id}] Encaminhando pacote para {dst} via {route['next_hop']}")
        else:
            print(f"[Router {self._router_id}] Rota não encontrada para {dst}")
    
    def _update_lsdb(self, router_id: str, sequence: int, links: Dict[str, int]) -> None:
        """
        Atualiza o Link State Database com novas informações.
        
        Args:
            router_id: ID do roteador que originou a informação
            sequence: Número de sequência do LSA
            links: Dicionário de enlaces {vizinho: custo}
        """
        self._lsdb[router_id] = {
            'sequence': sequence,
            'links': links,
            'timestamp': time.time()
        }

    def _run_dijkstra(self) -> None:
        """
        Executa o algoritmo de Dijkstra para calcular os caminhos mais curtos.
        
        Baseado na LSDB atual, calcula as rotas mais curtas para todos os destinos
        conhecidos na rede e atualiza a tabela de roteamento.
        """
        if not self._lsdb:
            return
            
        visited = set()
        distances = defaultdict(lambda: float('inf'))
        previous_nodes = {}
        
        all_nodes = set(self._lsdb.keys())
        all_nodes.add(self._router_id)
        
        distances[self._router_id] = 0
        priority_queue = [(0, self._router_id)]
        
        while priority_queue:
            current_distance, current_node = heapq.heappop(priority_queue)
            
            if current_node in visited:
                continue
                
            visited.add(current_node)
            
            neighbors = {}
            if current_node == self._router_id:
                neighbors = {n: 1 for n in self._neighbors.keys()}
            else:
                if current_node in self._lsdb:
                    neighbors = self._lsdb[current_node]['links']
            
            for neighbor, cost in neighbors.items():
                if neighbor not in all_nodes:
                    continue
                    
                distance = current_distance + cost
                if distance < distances[neighbor]:
                    distances[neighbor] = distance
                    previous_nodes[neighbor] = current_node
                    heapq.heappush(priority_queue, (distance, neighbor))
        
        self._update_routing_table(previous_nodes, distances)
    
    def _update_routing_table(self, previous_nodes: Dict[str, str], distances: Dict[str, float]) -> None:
        """
        Atualiza a tabela de roteamento com base nos resultados do Dijkstra.
        
        Args:
            previous_nodes: Dicionário com os nós anteriores no caminho mais curto
            distances: Dicionário com as distâncias mais curtas para cada nó
        """
        routing_table = {}
        
        for destination in distances:
            if destination == self._router_id or distances[destination] == float('inf'):
                continue
                
            path = []
            current_node = destination
            
            while current_node in previous_nodes:
                path.append(current_node)
                current_node = previous_nodes[current_node]
            path.reverse()
            
            if path and path[0] in self._neighbors:
                next_hop = path[0]
                interface = self._get_interface_for_neighbor(next_hop)
                routing_table[destination] = {
                    'next_hop': next_hop,
                    'interface': interface,
                    'cost': distances[destination]
                }
        
        with self._lock:
            self._routing_table = routing_table
            print(f"[Router {self._router_id}] Tabela de roteamento atualizada:")
            for dest, route in routing_table.items():
                print(f"  {dest} -> {route['next_hop']} (Interface: {route['interface']}, Custo: {route['cost']})")
    
    def _get_interface_for_neighbor(self, neighbor_id):
        """Retorna a interface de rede para alcançar um vizinho"""
        # Esta é uma implementação simplificada
        # Em uma implementação real, você mapearia vizinhos para interfaces específicas
        return f"eth_{neighbor_id}"


if __name__ == '__main__':
    pass