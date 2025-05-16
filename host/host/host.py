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
from typing import List, Dict, Any


class Host:
    def __init__(self, host_id: str, router_ip: str, router_port: int, listen_port: int, known_hosts: List[str]):
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
        self._router_ip = router_ip
        self._router_port = router_port
        self._listen_port = listen_port
        self._known_hosts = [h for h in known_hosts if h != host_id]

        self._running = False
        self._receiver_thread = None
        self._sequence_number = 0
        self._sender_thread = None
        self._outgoing_queue: List[Dict[str, Any]] = []

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
        if self._receiver_thread:
            self._receiver_thread.join(timeout=1)
        if self._sender_thread:
            self._sender_thread.join(timeout=1)

    def _receive_messages(self):
        """
        Thread responsável por escutar mensagens UDP na porta configurada.
        Caso o pacote recebido seja destinado a este host, ele prepara uma resposta automática.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', self._listen_port))
        sock.settimeout(1.0)

        while self._running:
            try:
                data, _ = sock.recvfrom(1024)
                message = json.loads(data.decode())
                typeMessage = message['type']
                sourceMessage = message['source']
                destinationMessage = message['destination']
                contentMessage = message['payload']

                print(f"[Host {self._host_id}] Recebeu mensagem de {sourceMessage}: {contentMessage}")

                if typeMessage == 'data' and destinationMessage == self._host_id:
                    # Prepara resposta, mas apenas enfileira
                    response = self._create_data_packet(destinationMessage, 'Legal.')
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
        """
        while self._running:
            time.sleep(random.randint(4, 7))  # intervalo aleatório

            # Mensagem espontânea
            if self._known_hosts:
                destinationRandom = random.choice(self._known_hosts)
                packet = self._create_data_packet(destinationRandom, 'Legal?')
                with self._lock:
                    self._outgoing_queue.append(packet)

            # Envio de mensagens na fila
            while True:
                with self._lock:
                    if not self._outgoing_queue:
                        break
                    packet = self._outgoing_queue.pop(0)

                self._send_packet_to_router(packet)

    def _send_packet_to_router(self, packet: Dict[str, Any]):
        """
        Envia um pacote para o roteador configurado via UDP.

        :param packet: Dicionário com as informações do pacote a ser enviado
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.sendto(json.dumps(packet).encode(), (self._router_ip, self._router_port))
                print(f"[Host {self._host_id}] Enviou para {packet['destination']}: {packet['payload']}")
        except Exception as e:
            print(f"[Host {self._host_id}] Erro ao enviar pacote: {e}")

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


if __name__ == '__main__':
    pass