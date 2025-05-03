import threading
import socket
import json
import time
import heapq
from typing import Dict, Tuple, Optional, Any, Set
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
        """
        Inicializa o roteador com parâmetros básicos de configuração.
        
        Args:
            router_id: Identificador único do roteador (string)
            neighbors: Dicionário de vizinhos no formato {neighbor_id: (ip, port)}
            listen_port: Porta UDP para escutar pacotes LSA (padrão: 5000)
        """
        self._router_id = router_id
        self._neighbors = neighbors
        self._listen_port = listen_port
        self._lsdb: Dict[str, Dict[str, Any]] = {}  # Link State Database
        self._running = False
        self._lock = threading.Lock()
        self._routing_table: Dict[str, Dict[str, Any]] = {}
        
        # Inicializa a LSDB com o próprio roteador
        self._update_lsdb(self._router_id, 0, {n: 1 for n in neighbors.keys()})
        
    def start(self) -> None:
        """
        Inicia as threads de recebimento e transmissão de pacotes LSA.
        
        Cria e inicia duas threads:
        1. Para receber pacotes de estado de enlace (LSA)
        2. Para transmitir pacotes de estado de enlace periodicamente
        """
        self._running = True
        
        self.receiver_thread = threading.Thread(
            target=self._receive_lsa_packets,
            daemon=True
        )
        
        self.sender_thread = threading.Thread(
            target=self._send_lsa_packets,
            daemon=True
        )
        
        self.receiver_thread.start()
        self.sender_thread.start()
        print(f"[Router {self._router_id}] Threads de recebimento e envio iniciadas")
    
    def stop(self) -> None:
        """
        Para as threads do roteador de forma segura.
        
        Sinaliza para as threads pararem e aguarda sua finalização.
        """
        self._running = False
        self.receiver_thread.join()
        self.sender_thread.join()
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

    def _receive_lsa_packets(self) -> None:
        """
        Thread para receber pacotes LSA dos vizinhos.
        
        Fica em loop ouvindo na porta UDP configurada e processa os pacotes recebidos.
        Utiliza timeout para verificar periodicamente se deve continuar executando.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(('0.0.0.0', self._listen_port))
            sock.settimeout(1.0)
            
            print(f"[Router {self._router_id}] Ouvindo LSAs na porta {self._listen_port}")
            
            while self._running:
                try:
                    data, addr = sock.recvfrom(1024)
                    lsa = json.loads(data.decode())
                    self._process_received_lsa(lsa)
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"[Router {self._router_id}] Erro ao processar LSA: {e}")
    
    def _send_lsa_packets(self) -> None:
        """
        Thread para enviar pacotes LSA periodicamente.
        
        Envia o estado atual dos enlaces para todos os vizinhos em intervalos regulares.
        """
        broadcast_interval = 5  # segundos
        
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            while self._running:
                with self._lock:
                    lsa_packet = {
                        'router_id': self._router_id,
                        'sequence': time.time_ns(),
                        'links': {n: 1 for n in self._neighbors.keys()}
                    }
                
                for neighbor_id, (ip, port) in self._neighbors.items():
                    try:
                        sock.sendto(json.dumps(lsa_packet).encode(), (ip, port))
                        print(f"[Router {self._router_id}] LSA enviado para {neighbor_id} ({ip}:{port})")
                    except Exception as e:
                        print(f"[Router {self._router_id}] Falha ao enviar LSA para {neighbor_id}: {e}")
                
                time.sleep(broadcast_interval)
    
    def _process_received_lsa(self, lsa: Dict[str, Any]) -> None:
        """
        Processa um pacote LSA recebido e atualiza a LSDB.
        
        Args:
            lsa: Dicionário contendo o pacote LSA recebido
        """
        sender_id = lsa['router_id']
        sequence = lsa['sequence']
        links = lsa['links']
        
        with self._lock:
            if sender_id in self._lsdb and self._lsdb[sender_id]['sequence'] >= sequence:
                return
            
            self._update_lsdb(sender_id, sequence, links)
            print(f"[Router {self._router_id}] LSDB atualizada com LSA de {sender_id}")
            self._run_dijkstra()
            
            for neighbor_id, (ip, port) in self._neighbors.items():
                if neighbor_id == sender_id:
                    continue  # não reenvia para quem enviou

                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                        sock.sendto(json.dumps(lsa).encode(), (ip, port))
                        print(f"[Router {self._router_id}] Replicou LSA de {sender_id} para {neighbor_id}")
                except Exception as e:
                    print(f"[Router {self._router_id}] Erro ao reenviar LSA: {e}")
    
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