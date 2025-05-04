import threading
import socket
import json
import time
# import heapq
from typing import Dict, Tuple, Any, Set, List
# from collections import defaultdict


class Router:
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
    
    # Use estes métodos para imprimir o estado das tabelas no terminal, caso necessário
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
    
    # Use estes métodos para imprimir o estado das tabelas no terminal, caso necessário
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
                    self._handle_packet(packet, addr)
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
    
    def _handle_packet(self, packet: Dict, addr: tuple) -> None:
        """Processa pacotes recebidos de acordo com o tipo"""
        packet_type = packet.get('type')
        
        if packet_type == 'lsa':
            self._process_lsa(packet)
        elif packet_type == 'data':
            print(f"[Router {self._router_id}] Pacote de dados recebido de {addr}")
            self._process_data_packet(packet)
        else:
            print(f"[Router {self._router_id}] Tipo de pacote inválido: {packet_type}")
    
    def _process_data_packet(self, packet: Dict) -> None:
        """Processa pacotes de dados com roteamento"""
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
            print(f"[Router {self._router_id}] Rota não encontrada para {destination}")
    
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
    
    def _process_lsa(self, lsa: Dict) -> None:
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