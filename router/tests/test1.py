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
    """Estrutura padronizada para pacotes de roteamento"""
    type: str  # Tipos: 'lsa' (Link-State Advertisement) ou 'data' (dados)
    router_id: str  # Identificador do roteador origem
    sequence: int = 0  # Número de sequência (para LSAs)
    payload: Any = None  # Conteúdo principal do pacote
    dst: Optional[str] = None  # Destino final (apenas para pacotes de dados)


class Router:
    def __init__(self, router_id: str, neighbors: Dict[str, Tuple[str, int]], listen_port: int = 5000):
        """
        Inicializa um roteador com protocolo OSPF simplificado.
        
        Args:
            router_id: Identificador único do roteador
            neighbors: Dicionário de vizinhos {vizinho_id: (ip, porta)}
            listen_port: Porta UDP para escutar pacotes
        """
        self._router_id = router_id
        self._neighbors = neighbors
        self._listen_port = listen_port
        
        # Estruturas de dados protegidas por lock
        self._lock = threading.Lock()
        self._lsdb: Dict[str, Dict[str, Any]] = {}  # Link State Database
        self._routing_table: Dict[str, Dict[str, Any]] = {}  # Tabela de roteamento
        self._outgoing_queue: List[Tuple[Dict, str, int]] = []  # Fila de pacotes para envio
        
        # Controle de estado
        self._running = False
        self._sequence_number = 0
        self._seen_lsas: Set[Tuple[str, int]] = set()  # Pares (router_id, sequence)
        
        # Inicializa a LSDB com o próprio roteador
        self._generate_initial_lsa()

    # ======================= #
    #  Interface Pública      #
    # ======================= #
    
    def start(self) -> None:
        """Inicia as threads de operação do roteador"""
        self._running = True
        
        # Threads principais
        threads = [
            threading.Thread(target=self._receive_packets, daemon=True),
            threading.Thread(target=self._send_packets, daemon=True),
            threading.Thread(target=self._generate_lsa_packets, daemon=True)
        ]
        
        for t in threads:
            t.start()

        print(f"[Router {self._router_id}] Threads iniciadas")

    def stop(self) -> None:
        """Para todas as threads do roteador"""
        self._running = False
        print(f"[Router {self._router_id}] Threads paradas")
    
    def print_lsdb(self) -> None:
        """Imprime a Link State Database formatada"""
        print(f"\n[Router {self._router_id}] Link State Database:")
        print(f"{'Roteador':<10} | {'Sequência':<10} | {'Enlaces':<30}")
        print("-" * 60)
        with self._lock:
            for router, data in self._lsdb.items():
                links = ', '.join(f"{n}:{c}" for n, c in data['links'].items())
                print(f"{router:<10} | {data['sequence']:<10} | {links:<30}")
    
    def print_routing_table(self) -> None:
        """Imprime a tabela de roteamento formatada"""
        print(f"\n[Router {self._router_id}] Tabela de Roteamento:")
        print(f"{'Destino':<10} | {'Custo':<5} | {'Próximo Salto':<15}")
        print("-" * 40)
        with self._lock:
            for dest, route in self._routing_table.items():
                print(f"{dest:<10} | {route.get('cost', '?'):<5} | {route.get('next_hop', '?'):<15}")

    # ====================== #
    #  Threads Principais    #
    # ====================== #
    
    def _receive_packets(self) -> None:
        """Thread para receber e processar pacotes"""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(('0.0.0.0', self._listen_port))
            sock.settimeout(1.0)

            while self._running:
                try:
                    data, _ = sock.recvfrom(1024)
                    packet = json.loads(data.decode())
                    self._process_packet(packet)
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"[Router {self._router_id}] Erro no recebimento: {e}")

    def _send_packets(self) -> None:
        """Thread para enviar pacotes da fila de saída"""
        while self._running:
            if self._outgoing_queue:
                with self._lock:
                    packet, ip, port = self._outgoing_queue.pop(0)
                
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                        sock.sendto(json.dumps(packet).encode(), (ip, port))
                except Exception as e:
                    print(f"[Router {self._router_id}] Falha no envio: {e}")
            
            time.sleep(0.01)  # Controle de CPU

    def _generate_lsa_packets(self) -> None:
        """Thread para gerar LSAs periódicos"""
        while self._running:
            lsa = self._create_lsa_packet()
            self._update_own_lsa(lsa)
            self._schedule_flooding(lsa)
            time.sleep(30)  # Intervalo OSPF padrão

    # ====================== #
    #  Processamento LSAs    #
    # ====================== #
    
    def _create_lsa_packet(self) -> Dict:
        """Cria um novo pacote LSA com estado atual dos enlaces"""
        self._sequence_number += 1
        return Packet(
            type='lsa',
            router_id=self._router_id,
            sequence=self._sequence_number,
            payload={'links': dict(self._neighbors.keys())}  # Custo 1 para todos
        ).__dict__

    def _generate_initial_lsa(self) -> None:
        """Gera o LSA inicial na inicialização do roteador"""
        initial_lsa = self._create_lsa_packet()
        self._update_lsdb(self._router_id, initial_lsa['sequence'], initial_lsa['payload']['links'])
        self._seen_lsas.add((self._router_id, initial_lsa['sequence']))

    def _update_own_lsa(self, lsa: Dict) -> None:
        """Atualiza a LSDB com próprio LSA"""
        with self._lock:
            self._update_lsdb(self._router_id, lsa['sequence'], lsa['payload']['links'])
            self._seen_lsas.add((self._router_id, lsa['sequence']))

    def _process_packet(self, packet: Dict) -> None:
        """Despacha pacote para handler específico"""
        handlers = {
            'lsa': self._process_lsa,
            'data': self._process_data_packet
        }
        
        if packet.get('type') in handlers:
            handlers[packet['type']](packet)
        else:
            print(f"[Router {self._router_id}] Tipo de pacote inválido: {packet.get('type')}")

    def _process_lsa(self, lsa: Dict) -> None:
        """Processa um LSA recebido e faz flooding se necessário"""
        sender = lsa['router_id']
        seq = lsa['sequence']
        
        with self._lock:
            # Verifica se é um LSA novo
            if (sender, seq) in self._seen_lsas:
                return
                
            current_seq = self._lsdb.get(sender, {'sequence': -1})['sequence']
            if seq <= current_seq:
                return
            
            # Atualiza a LSDB
            self._seen_lsas.add((sender, seq))
            self._update_lsdb(sender, seq, lsa['payload']['links'])
            print(f"[Router {self._router_id}] Atualizado LSA de {sender}")
            
            # Agenda flooding e recalcula rotas
            self._schedule_flooding(lsa, except_neighbor=sender)
            self._run_dijkstra()

    def _schedule_flooding(self, lsa: Dict, except_neighbor: Optional[str] = None) -> None:
        """Adiciona pacote LSA na fila para flooding controlado"""
        with self._lock:
            for neighbor, (ip, port) in self._neighbors.items():
                if neighbor != except_neighbor:
                    self._outgoing_queue.append((lsa, ip, port))

    # ====================== #
    #  Processamento Dados   #
    # ====================== #
    
    def _process_data_packet(self, packet: Dict) -> None:
        """Processa e encaminha pacotes de dados"""
        if packet.get('dst') == self._router_id:
            print(f"[Router {self._router_id}] Pacote recebido: {packet.get('payload')}")
            return
        
        next_hop = self._get_next_hop(packet.get('dst'))
        if next_hop:
            self._forward_packet(packet, *next_hop)

    def _get_next_hop(self, destination: str) -> Optional[Tuple[str, int]]:
        """Obtém próximo salto para um destino"""
        with self._lock:
            route = self._routing_table.get(destination, {})
            if route.get('next_hop') in self._neighbors:
                return self._neighbors[route['next_hop']]
        return None

    def _forward_packet(self, packet: Dict, ip: str, port: int) -> None:
        """Encaminha pacote para o próximo roteador"""
        with self._lock:
            self._outgoing_queue.append((packet, ip, port))
        print(f"[Router {self._router_id}] Encaminhando pacote para {ip}:{port}")

    # ====================== #
    #  Algoritmo Dijkstra    #
    # ====================== #
    
    def _run_dijkstra(self) -> None:
        """Calcula caminhos mais curtos usando Dijkstra"""
        if not self._lsdb:
            return
            
        # Inicialização
        visited = set()
        distances = defaultdict(lambda: float('inf'))
        previous = {}
        nodes = set(self._lsdb.keys()) | {self._router_id}
        
        distances[self._router_id] = 0
        heap = [(0, self._router_id)]
        
        # Processamento
        while heap:
            dist, node = heapq.heappop(heap)
            if node in visited:
                continue
            visited.add(node)
            
            for neighbor, cost in self._get_neighbors(node).items():
                if neighbor not in nodes:
                    continue
                    
                new_dist = dist + cost
                if new_dist < distances[neighbor]:
                    distances[neighbor] = new_dist
                    previous[neighbor] = node
                    heapq.heappush(heap, (new_dist, neighbor))
        
        self._update_routing_table(previous, distances)

    def _get_neighbors(self, node: str) -> Dict[str, int]:
        """Obtém vizinhos de um nó (próprio roteador ou da LSDB)"""
        if node == self._router_id:
            return {n: 1 for n in self._neighbors.keys()}
        return self._lsdb.get(node, {}).get('links', {})

    def _update_routing_table(self, previous: Dict[str, str], distances: Dict[str, float]) -> None:
        """Atualiza tabela de roteamento com resultados do Dijkstra"""
        new_routes = {}
        
        for dest in distances:
            if dest == self._router_id or distances[dest] == float('inf'):
                continue
                
            path = self._reconstruct_path(previous, dest)
            if path and path[0] in self._neighbors:
                new_routes[dest] = {
                    'next_hop': path[0],
                    'interface': f"eth_{path[0]}",
                    'cost': distances[dest]
                }
        
        with self._lock:
            self._routing_table = new_routes
            print(f"[Router {self._router_id}] Tabela de roteamento atualizada")

    def _reconstruct_path(self, previous: Dict[str, str], dest: str) -> List[str]:
        """Reconstrói caminho a partir dos nós anteriores"""
        path = []
        while dest in previous:
            path.append(dest)
            dest = previous[dest]
        path.reverse()
        return path

    # ====================== #
    #  Gerenciamento LSDB    #
    # ====================== #
    
    def _update_lsdb(self, router_id: str, sequence: int, links: Dict[str, int]) -> None:
        """Atualiza a LSDB com informações de um roteador"""
        self._lsdb[router_id] = {
            'sequence': sequence,
            'links': links,
            'timestamp': time.time()
        }


if __name__ == '__main__':
    # Exemplo de uso
    router = Router('R1', {'R2': ('10.0.0.2', 5000), 'R3': ('10.0.0.3', 5000)})
    router.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        router.stop()