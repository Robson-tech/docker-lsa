"""
Este módulo define a classe Host, que simula um host em uma rede que se comunica
via pacotes UDP com outros hosts por meio de um roteador. Ele envia mensagens
espontâneas e responde automaticamente a mensagens recebidas.
"""

import threading
import socket
import json
import random
import time
import argparse
from typing import List, Dict, Any


class Host:
    def __init__(self, host_id: str, router_ip: str, router_port: int, known_hosts: List[str], host_ip: str = '0.0.0.0', listen_port: int = 7001):
        """
        Classe que representa um host na rede.

        O host pode enviar mensagens espontâneas para outros hosts conhecidos, e também
        responder automaticamente a mensagens recebidas, utilizando um roteador como intermediário.

        :param host_id: Identificador único do host
        :param router_ip: Endereço IP do roteador conectado a este host
        :param router_port: Porta do roteador para envio de pacotes
        :param listen_port: Porta local para escutar mensagens UDP
        :param known_hosts: Lista de IDs de outros hosts na rede
        """
        self._host_id = host_id
        self._host_ip = host_ip
        self._router_ip = router_ip
        self._router_port = router_port
        self._listen_port = listen_port
        self._known_hosts = [h for h in known_hosts if h != host_id]

        self._running = False
        self._receiver_thread = None
        self._sequence_number = 0
        self._last_confirmed_seq = -1
        self._sender_thread = None
        self._outgoing_queue: List[Dict[str, Any]] = []
        self._awaiting_confirmation = False
        self._message_event = threading.Event()

        self._lock = threading.Lock()

    def start(self):
        """
        Inicia as threads de envio e recebimento de pacotes.
        """
        self._running = True
        self._receiver_thread = threading.Thread(target=self._receive_messages)
        self._receiver_thread.start()

        self._sender_thread = threading.Thread(target=self._send_messages)
        self._sender_thread.start()

    def stop(self):
        """
        Interrompe as threads de envio e recebimento de pacotes.
        Aguarda finalização das threads com timeout.
        """
        self._running = False
        self._message_event.set()  # Libera a thread de envio
        if self._receiver_thread:
            self._receiver_thread.join(timeout=1)
        if self._sender_thread:
            self._sender_thread.join(timeout=1)

    def _receive_messages(self):
        """
        Thread responsável por escutar mensagens UDP na porta configurada.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self._host_ip, self._listen_port))
        sock.settimeout(1.0)

        while self._running:
            try:
                data, _ = sock.recvfrom(1024)
                message = json.loads(data.decode())
                
                # Verifica se é uma mensagem de confirmação
                if message.get('type') == 'ack':
                    with self._lock:
                        if message['sequence'] == self._last_confirmed_seq + 1:
                            self._last_confirmed_seq = message['sequence']
                            self._awaiting_confirmation = False
                            self._message_event.set()
                            print(f"[Host {self._host_id}] Confirmação recebida para sequência {message['sequence']}")
                    continue

                typeMessage = message['type']
                sourceMessage = message['source']
                destinationMessage = message['destination']
                contentMessage = message['payload']

                print(f"[Host {self._host_id}] Recebeu mensagem de {sourceMessage}: {contentMessage}")

                if typeMessage == 'data' and destinationMessage == self._host_id:
                    # Envia confirmação de recebimento
                    ack_packet = self._create_ack_packet(
                        sequence=message['sequence'],
                        destination=sourceMessage
                    )
                    self._send_packet_to_router(ack_packet)

                    # Prepara resposta
                    response = self._create_data_packet(sourceMessage, 'Legal.')
                    with self._lock:
                        self._outgoing_queue.append(response)

            except socket.timeout:
                continue
            except KeyError as e:
                print(f'[Host {self._host_id}] Erro de formato do pacote. Campo não reconhecido: {e}')
            except Exception as e:
                print(f'[Host {self._host_id}] Erro ao receber mensagem: {e}')

        sock.close()

    def _send_messages(self):
        """
        Thread responsável por gerar mensagens espontâneas e enviar
        mensagens da fila de saída (_outgoing_queue) para o roteador.
        Agora espera confirmação antes de enviar a próxima mensagem.
        """
        while self._running:
            # Mensagem espontânea
            if self._known_hosts and not self._awaiting_confirmation:
                destination = random.choice(self._known_hosts)
                packet = self._create_data_packet(destination, 'Legal?')
                with self._lock:
                    self._outgoing_queue.append(packet)

            # Envio de mensagens na fila
            with self._lock:
                if not self._outgoing_queue or self._awaiting_confirmation:
                    continue
                packet = self._outgoing_queue.pop(0)
                self._last_confirmed_seq = packet['sequence'] - 1  # Espera confirmação para este

            self._send_packet_to_router(packet)
            self._awaiting_confirmation = True
            self._message_event.clear()

            # Espera confirmação ou timeout
            if not self._message_event.wait(timeout=5.0):  # Timeout de 5 segundos
                print(f"[Host {self._host_id}] Timeout - reenviando pacote {packet['sequence']}")
                with self._lock:
                    self._outgoing_queue.insert(0, packet)  # Recoloca no início da fila
                self._awaiting_confirmation = False

    def _send_packet_to_router(self, packet: Dict[str, Any]):
        """
        Envia um pacote para o roteador configurado via UDP.
        Trata pacotes ACK de forma diferenciada para melhor rastreamento.

        Args:
            packet: Dicionário contendo:
                - type: 'data' ou 'ack'
                - sequence: Número de sequência
                - source: Origem do pacote
                - destination: Destino do pacote
                - payload: Conteúdo (para pacotes de dados)
                - timestamp: Timestamp (para pacotes ACK)
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.sendto(json.dumps(packet).encode(), (self._router_ip, self._router_port))
                
                # Log diferenciado para ACKs
                if packet.get('type') == 'ack':
                    print(f"[Host {self._host_id}] ACK enviado para {packet['destination']} "
                        f"(seq: {packet['sequence']}, timestamp: {packet['timestamp']:.2f})")
                else:
                    print(f"[Host {self._host_id}] Dados enviados para {packet['destination']}: "
                        f"{packet['payload']} (seq: {packet['sequence']})")
                    
        except socket.error as e:
            error_msg = f"Erro de socket ao enviar {packet.get('type', 'pacote')}"
            if packet.get('type') == 'ack':
                error_msg += f" (ACK para seq {packet['sequence']})"
            print(f"[Host {self._host_id}] {error_msg}: {e}")
            
        except json.JSONEncodeError as e:
            print(f"[Host {self._host_id}] Erro ao serializar pacote: {e}")
            
        except Exception as e:
            print(f"[Host {self._host_id}] Erro inesperado ao enviar pacote: {e}")
            if packet.get('type') == 'ack':
                print(f"[Host {self._host_id}] Pacote ACK perdido: {packet}")

    def _create_data_packet(self, destination: str, content: str) -> Dict:
        """
        Cria um novo pacote de dados para envio.

        :param destination: ID do host de destino
        :param content: Conteúdo da mensagem
        :return: Dicionário com o pacote formatado
        """
        self._sequence_number += 1
        return {
            'type': 'data',
            'sequence': self._sequence_number,
            'source': self._host_id,
            'destination': destination,
            'ttl': 10,
            'payload': {
                'content': content
            }
        }
    
    def _create_ack_packet(self, sequence: int, destination: str) -> Dict:
        """
        Cria um pacote de confirmação (ACK) para enviar ao remetente.
        
        Args:
            sequence: Número de sequência do pacote sendo confirmado
            destination: ID do host remetente original
            
        Returns:
            Dicionário representando o pacote ACK formatado
        """
        return {
            'type': 'ack',
            'sequence': sequence,
            'source': self._host_id,
            'destination': destination,
            'timestamp': time.time()
        }


def parse_arguments():
    """
    Configura e parseia os argumentos de linha de comando
    """
    parser = argparse.ArgumentParser(description='Inicia um host na rede')
    
    parser.add_argument('--id', required=True, help='ID único do host')
    parser.add_argument('--router_ip', required=True, help='IP do roteador gateway')
    parser.add_argument('--router_port', type=int, required=True, help='Porta do roteador gateway')
    parser.add_argument('--host_ip', default='0.0.0.0', help='IP do host')
    parser.add_argument('--listen_port', type=int, default=5001, help='Porta para escutar mensagens')
    parser.add_argument('--known_hosts', nargs='+', default=[], help='Lista de hosts conhecidos')
    
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_arguments()
    
    host = Host(
        host_id=args.id,
        router_ip=args.router_ip,
        router_port=args.router_port,
        host_ip=args.host_ip,
        listen_port=args.listen_port,
        known_hosts=args.known_hosts
    )
    
    try:
        host.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        host.stop()