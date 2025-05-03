import threading
import socket
import json
import random
import time

class Host:
    def __init__(self, host_id: str, router_ip: str, router_port: int, listen_port: int, known_hosts: list):
        self.host_id = host_id
        self.router_ip = router_ip
        self.router_port = router_port
        self.listen_port = listen_port
        self.known_hosts = [h for h in known_hosts if h != host_id]
        self.running = False
        self.receiver_thread = None
        self.sender_thread = None

    def start(self):
        self.running = True
        self.receiver_thread = threading.Thread(target=self._receive_messages)
        self.receiver_thread.start()

        self.sender_thread = threading.Thread(target=self._send_messages)
        self.sender_thread.start()

    def stop(self):
        self.running = False
        if self.receiver_thread:
            self.receiver_thread.join(timeout=1)
        if self.sender_thread:
            self.sender_thread.join(timeout=1)

    def _receive_messages(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', self.listen_port))
        sock.settimeout(1.0)

        while self.running:
            try:
                data, _ = sock.recvfrom(4096)
                message = json.loads(data.decode())
                print(f"[{self.host_id}] Recebeu mensagem: {message}")

                if message['type'] == 'data' and message['destination'] == self.host_id:
                    response = {
                        'type': 'data',
                        'source': self.host_id,
                        'destination': message['source'],
                        'payload': 'Legal.'
                    }
                    self._send_packet_to_router(response)

            except socket.timeout:
                continue
            except Exception as e:
                print(f"[{self.host_id}] Erro ao receber mensagem: {e}")

        sock.close()

    def _send_messages(self):
        while self.running:
            time.sleep(random.randint(4, 7))  # intervalo entre mensagens

            if not self.known_hosts:
                continue

            destination = random.choice(self.known_hosts)
            packet = {
                'type': 'data',
                'source': self.host_id,
                'destination': destination,
                'payload': 'Legal?'
            }

            self._send_packet_to_router(packet)

    def _send_packet_to_router(self, packet):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.sendto(json.dumps(packet).encode(), (self.router_ip, self.router_port))
                print(f"[{self.host_id}] Enviou pacote para {packet['destination']}: {packet['payload']}")
        except Exception as e:
            print(f"[{self.host_id}] Erro ao enviar pacote: {e}")
