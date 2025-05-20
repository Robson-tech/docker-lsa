"""
Simulador de roteador com suporte ao protocolo de estado de enlace (Link-State Routing),
baseado no algoritmo de Dijkstra, usando comunicação via sockets UDP e multithreading.

Cada roteador:

- Mantém uma base de dados de estado de enlace (LSDB)
- Calcula rotas com Dijkstra com base nos LSAs recebidos
- Encaminha pacotes entre hosts e outros roteadores
"""

import threading
import socket
import json
import time
import heapq
import argparse
from typing import Dict, Tuple, Optional, Any, Set, List
from collections import defaultdict


class Router:
    def __init__(self, router_id: str, neighbors: Dict[str, Tuple[str, int]] = [], router_ip: str = '0.0.0.0', listen_port: int = 5001):
        """
        Inicializa o roteador com identificador, vizinhos e porta de escuta.

        Args:
            router_id: Nome ou ID único do roteador (ex: 'R1').
            neighbors: Dicionário de vizinhos no formato {id: (ip, porta)}.
            listen_port: Porta UDP para escutar pacotes recebidos.
        """
        self._router_id = router_id
        self._router_ip = router_ip
        self._neighbors = neighbors
        self._listen_port = listen_port
        self._lsdb: Dict[str, Dict[str, Any]] = {}  # Link State Database
        self._running = False
        self._lock = threading.Lock()
        self._routing_table: Dict[str, Dict[str, int]] = {}
        self._sequence_number = 0
        self._seen_lsas: Set[Tuple[str, int]] = set()
        self._outgoing_queue: List[Tuple[Dict, str, int]] = []  # (packet, ip, port)
        self._pending_acks = {}  # {sequence: (packet, dest_ip, dest_port, timestamp, retries)}
        self._ack_lock = threading.Lock()
        self._last_ack_time = time.time()

        # Inicializa estruturas de roteamento
        self._initialize_routing_structures()

    def _initialize_routing_structures(self) -> None:
        """
        Gera o primeiro LSA e configura rotas para vizinhos diretos e gateway padrão.
        """
        with self._lock:
            # Inicializa a LSDB com o próprio roteador
            self._generate_initial_lsa()

            # Configura o primeiro vizinho como gateway padrão
            if self._neighbors:
                first_neighbor = next(iter(self._neighbors.keys()))
                self._routing_table['0.0.0.0'] = {
                    'next_hop': first_neighbor,
                    'cost': 1
                }
                print(f"[Router {self._router_id}] Gateway padrão configurado para {first_neighbor}")
            
            # Inicializa tabela de roteamento com vizinhos diretos
            for neighbor in self._neighbors.keys():
                self._routing_table[neighbor] = {
                    'next_hop': neighbor,
                    'cost': 1  # Custo padrão para vizinhos diretos
                }
            
        print(f"[Router {self._router_id}] Tabela de roteamento inicializada com vizinhos diretos\n{self.get_routing_table_formatted()}")

    def _generate_initial_lsa(self) -> None:
        """
        Cria e registra o LSA inicial do roteador na LSDB.
        """
        initial_lsa = self._create_lsa_packet()
        self._update_lsdb(self._router_id, self._sequence_number, initial_lsa['payload']['links'])
        self._seen_lsas.add((self._router_id, self._sequence_number))

    def _update_lsdb(self, router_id: str, sequence: int, links: Dict[str, int]) -> None:
        """
        Atualiza a LSDB com um novo LSA.

        Args:
            router_id: Identificador do roteador que enviou o LSA.
            sequence: Número de sequência do LSA.
            links: Dicionário de vizinhos e custos.
        """
        self._lsdb[router_id] = {
            'sequence': sequence,
            'links': links,
            'timestamp': time.time()
        }

    def start(self) -> None:
        """
        Inicia todas as threads do roteador (recebimento, envio, geração de LSA).
        """
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
        """
        Para todas as threads do roteador de forma segura.
        """
        self._running = False
        self.receiver_thread.join()
        self.sender_thread.join()
        self.lsa_generator_thread.join()
        print(f"[Router {self._router_id}] Threads paradas")

    def get_lsdb_table_formatted(self) -> str:
        """
        Retorna a LSDB formatada como tabela com bordas.
        """
        with self._lock:
            header = f"┌{'─' * 12}┬{'─' * 22}┬{'─' * 50}┐\n"
            title = f"│ {'Roteador':<10} │ {'Sequência':<20} │ {'Enlaces (vizinho: custo)':<49}│\n"
            divider = f"├{'─' * 12}┼{'─' * 22}┼{'─' * 50}┤\n"
            rows = ""
            for router_id, data in self._lsdb.items():
                links_str = ', '.join(f"{n}:{c}" for n, c in data['links'].items())
                rows += f"│ {router_id:<10} │ {data['sequence']:<20} │ {links_str:<49}│\n"
            footer = f"└{'─' * 12}┴{'─' * 22}┴{'─' * 50}┘"

            table = header + title + divider + rows + footer

        return table

    def get_routing_table_formatted(self) -> str:
        """
        Retorna a tabela de roteamento formatada como tabela com bordas.
        """
        with self._lock:
            col1, col2, col3 = 12, 8, 20  # larguras das colunas

            top_border = f"┌{'─' * col1}┬{'─' * col2}┬{'─' * col3}┐\n"
            header_line = f"│ {'Destino':<{col1 - 2}} │ {'Custo':<{col2 - 2}} │ {'Próximo Salto':<{col3 - 1}}│\n"
            mid_border = f"├{'─' * col1}┼{'─' * col2}┼{'─' * col3}┤\n"
            rows = ""

            for dest, info in self._routing_table.items():
                cost = info.get('cost', '?')
                next_hop = info.get('next_hop', '?')
                rows += f"│ {dest:<{col1 - 2}} │ {cost:<{col2 - 2}} │ {next_hop:<{col3 - 1}}│\n"

            bottom_border = f"└{'─' * col1}┴{'─' * col2}┴{'─' * col3}┘"

            table = top_border + header_line + mid_border + rows + bottom_border

        return table

    def _receive_packets(self) -> None:
        """
        Thread que escuta pacotes UDP recebidos na porta do roteador.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind((self._router_ip, self._listen_port))
            sock.settimeout(1.0)

            print(f"[Router {self._router_id}] Ouvindo pacotes na porta {self._listen_port}")

            while self._running:
                try:
                    data, addr = sock.recvfrom(1024)
                    packet = json.loads(data.decode())
                    self._handle_packet(packet)
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"[Router {self._router_id}] Erro ao receber: {e}")

    def _send_packets(self) -> None:
        """
        Thread que envia pacotes presentes na fila de saída (_outgoing_queue).
        Agora inclui lógica de retransmissão e confirmação.
        """
        while self._running:
            current_time = time.time()
            
            # 1. Verifica retransmissões pendentes
            with self._ack_lock:
                for seq in list(self._pending_acks.keys()):
                    pkt, ip, port, ts, retries = self._pending_acks[seq]
                    
                    if current_time - ts > 2.0:  # Timeout de 2 segundos
                        if retries < 3:  # Máximo de 3 tentativas
                            try:
                                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                                    sock.sendto(json.dumps(pkt).encode(), (ip, port))
                                    self._pending_acks[seq] = (pkt, ip, port, current_time, retries + 1)
                                    print(f"[Router {self._router_id}] Retransmitindo pacote (tentativa {retries + 1})")
                            except Exception as e:
                                print(f"[Router {self._router_id}] Falha na retransmissão: {e}")
                        else:
                            print(f"[Router {self._router_id}] Máximo de retentativas alcançado para seq {seq}")
                            del self._pending_acks[seq]
            
            # 2. Processa novos pacotes da fila
            if self._outgoing_queue:
                with self._lock:
                    packet, dest_ip, dest_port = self._outgoing_queue.pop(0)
                
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                        sock.sendto(json.dumps(packet).encode(), (dest_ip, dest_port))
                        
                        # Se for pacote de dados, armazena para possível retransmissão
                        if packet.get('type') == 'data':
                            with self._ack_lock:
                                self._pending_acks[packet['sequence']] = (
                                    packet, dest_ip, dest_port, current_time, 0
                                )
                        
                        print(f"[Router {self._router_id}] Pacote enviado para {dest_ip}:{dest_port}")
                except Exception as e:
                    print(f"[Router {self._router_id}] Falha no envio: {e}")
            
            time.sleep(0.1)  # Intervalo reduzido para melhor responsividade

    def _handle_packet(self, packet: Dict) -> None:
        """
        Trata pacotes recebidos de acordo com o tipo: LSA, dados ou ACK.
        """
        packet_type = packet.get('type')
        
        if packet_type == 'lsa':
            self._process_lsa(packet)
        elif packet_type == 'data':
            print(f"[Router {self._router_id}] Pacote de dados recebido de {packet['source']}")
            self._process_data_packet(packet)
        elif packet_type == 'ack':
            self._process_ack_packet(packet)
        else:
            print(f"[Router {self._router_id}] Tipo de pacote inválido: {packet_type}")

    def _process_ack_packet(self, packet: Dict) -> None:
        """
        Processa um pacote de confirmação (ACK).
        Remove o pacote confirmado da lista de pendentes.
        """
        seq = packet['sequence']
        with self._ack_lock:
            if seq in self._pending_acks:
                del self._pending_acks[seq]
                print(f"[Router {self._router_id}] Confirmação recebida para pacote {seq}")
                self._last_ack_time = time.time()
            else:
                print(f"[Router {self._router_id}] ACK inesperado para sequência {seq}")

    def _process_data_packet(self, packet: Dict) -> None:
        """
        Processa um pacote de dados e o encaminha com base na tabela de roteamento.
        Inclui envio de confirmação (ACK) para o remetente.
        """
        # Verifica TTL
        if 'ttl' in packet:
            packet['ttl'] -= 1
            if packet['ttl'] <= 0:
                print(f"[Router {self._router_id}] Pacote descartado - TTL esgotado")
                return
        
        # Envia ACK de confirmação
        ack_packet = {
            'type': 'ack',
            'sequence': packet['sequence'],
            'source': self._router_id,
            'destination': packet['source']
        }
        source_ip, source_port = self._neighbors.get(packet['source'], (None, None))
        
        if source_ip and source_port:
            self._outgoing_queue.append((ack_packet, source_ip, source_port))
        else:
            print(f"[Router {self._router_id}] Não foi possível enviar ACK - origem desconhecida")
        
        # Processamento normal do pacote
        destination = packet.get('destination')
        
        if destination == self._router_id:
            print(f"[Router {self._router_id}] Pacote recebido: {packet.get('payload')}")
            return
        
        with self._lock:
            route = self._routing_table.get(destination)
            
        if route and route['next_hop'] in self._neighbors:
            ip, port = self._neighbors[route['next_hop']]
            self._outgoing_queue.append((packet, ip, port))
            print(f"[Router {self._router_id}] Encaminhando pacote para {destination} via {route['next_hop']}")
        else:
            if self._neighbors:
                first_neighbor = next(iter(self._neighbors.keys()))
                ip, port = self._neighbors[first_neighbor]
                self._outgoing_queue.append((packet, ip, port))
                print(f"[Router {self._router_id}] Encaminhando pacote para gateway padrão {first_neighbor}")
            else:
                print(f"[Router {self._router_id}] Sem vizinhos - pacote descartado")

    def _create_lsa_packet(self) -> Dict:
        """
        Cria um novo pacote LSA com sequência incrementada e links atuais.
        """
        self._sequence_number += 1
        return {
            'type': 'lsa',
            'sequence': self._sequence_number,
            'source': self._router_id,
            'destination': None,
            'payload': {
                'links': {n: 1 for n in self._neighbors.keys()}
            }
        }

    def _generate_lsa_packets(self) -> None:
        """
        Thread que gera e envia pacotes LSA periodicamente.
        """
        while self._running:
            lsa = self._create_lsa_packet()
            
            with self._lock:
                self._update_lsdb(self._router_id, lsa['sequence'], lsa['payload']['links'])
                self._seen_lsas.add((self._router_id, lsa['sequence']))
                
                # Agenda envio para todos os vizinhos
                for neighbor_id, (ip, port) in self._neighbors.items():
                    self._outgoing_queue.append((lsa, ip, port))
            
            time.sleep(30)  # Intervalo OSPF padrão

    def _process_lsa(self, lsa: Dict) -> None:
        """
        Processa LSA recebido e atualiza LSDB com flooding controlado.
        """
        sender_id = lsa['source']
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
        
        self.get_lsdb_table_formatted()

        # Agenda flooding para outros vizinhos
        self._schedule_flooding(lsa, except_neighbor=sender_id)
        
        # Recalcula rotas
        self._run_dijkstra()

    def _schedule_flooding(self, lsa: Dict, except_neighbor: Optional[str] = None) -> None:
        """
        Adiciona LSA na fila de envio para todos os vizinhos, exceto o remetente.
        """
        with self._lock:
            for neighbor_id, (ip, port) in self._neighbors.items():
                if neighbor_id != except_neighbor:
                    self._outgoing_queue.append((lsa, ip, port))

    def _run_dijkstra(self) -> None:
        """
        Executa Dijkstra para atualizar rotas com base na LSDB.
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
        Atualiza a tabela de roteamento com os caminhos mais curtos.

        Args:
            previous_nodes: Dicionário com predecessores de cada nó no caminho mais curto.
            distances: Dicionário com as menores distâncias até cada nó.
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
                routing_table[destination] = {
                    'next_hop': next_hop,
                    'cost': distances[destination]
                }
        
        with self._lock:
            self._routing_table.update(routing_table)
        
        self.get_routing_table_formatted()


def parse_neighbors(neighbors_list: List[str]) -> Dict[str, Tuple[str, int]]:
    """Converte a lista de vizinhos no formato string para dicionário"""
    neighbors = {}
    if neighbors_list:
        for neighbor_str in neighbors_list:
            parts = neighbor_str.split(':')
            if len(parts) == 3:
                neighbor_id, ip, port = parts
                neighbors[neighbor_id] = (ip, int(port))
            else:
                print(f"Formato inválido para vizinho: {neighbor_str}. Use 'id:ip:porta'")
    return neighbors


def parse_arguments():
    parser = argparse.ArgumentParser(description='Inicia um roteador na rede')
    parser.add_argument('--id', required=True, help='ID único do roteador')
    parser.add_argument('--neighbors', nargs='+', help='Vizinhos no formato id:ip:porta')
    parser.add_argument('--ip', default='0.0.0.0', help='Endereço IP deste roteador')
    parser.add_argument('--listen_port', type=int, default=5000)
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_arguments()
    neighbors = parse_neighbors(args.neighbors)

    router = Router(
        router_id=args.id,
        neighbors=neighbors,
        router_ip=args.ip,
        listen_port=args.listen_port
    )

    try:
        router.start()
        while True:
            pass
    except KeyboardInterrupt:
        router.stop()