import threading
import socket
import json
import random
import time
from typing import List, Dict, Any


class Host:
    def __init__(self, host_id: str, router_ip: str, router_port: int, listen_port: int, known_hosts: List[str]):
        self._host_id = host_id
        self._router_ip = router_ip
        self._router_port = router_port
        self._listen_port = listen_port
        self._known_hosts = [h for h in known_hosts if h != host_id]

        self._running = False
        self._receiver_thread = None
        self._sender_thread = None
        self._outgoing_queue: List[Dict[str, Any]] = []

        self._lock = threading.Lock()

    def start(self):
        self._running = True
        self._receiver_thread = threading.Thread(target=self._receive_messages)
        self._receiver_thread.start()

        self._sender_thread = threading.Thread(target=self._send_messages)
        self._sender_thread.start()

    def stop(self):
        self._running = False
        if self._receiver_thread:
            self._receiver_thread.join(timeout=1)
        if self._sender_thread:
            self._sender_thread.join(timeout=1)

    def _receive_messages(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', self._listen_port))
        sock.settimeout(1.0)

        while self._running:
            try:
                data, _ = sock.recvfrom(1024)
                message = json.loads(data.decode())
                print(f"[Host {self._host_id}] Recebeu mensagem: {message}")

                if message['type'] == 'data' and message['destination'] == self._host_id:
                    # Prepara resposta, mas apenas enfileira
                    response = {
                        'type': 'data',
                        'source': self._host_id,
                        'destination': message['source'],
                        'payload': 'Legal.'
                    }
                    with self._lock:
                        self._outgoing_queue.append(response)

            except socket.timeout:
                continue
            except Exception as e:
                print(f"[Host {self._host_id}] Erro ao receber mensagem: {e}")

        sock.close()

    def _send_messages(self):
        while self._running:
            time.sleep(random.randint(4, 7))  # intervalo aleatório

            # Mensagem espontânea
            if self._known_hosts:
                destination = random.choice(self._known_hosts)
                packet = {
                    'type': 'data',
                    'source': self._host_id,
                    'destination': destination,
                    'payload': 'Legal?'
                }
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
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.sendto(json.dumps(packet).encode(), (self._router_ip, self._router_port))
                print(f"[Host {self._host_id}] Enviou para {packet['destination']}: {packet['payload']}")
        except Exception as e:
            print(f"[Host {self._host_id}] Erro ao enviar pacote: {e}")
