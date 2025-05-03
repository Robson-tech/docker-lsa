import socket
import time
import struct
import random
import argparse
import sys
import json

# Formato do pacote de ping:
# {
#   "type": "ping_request" ou "ping_reply",
#   "sequence": número de sequência,
#   "timestamp": timestamp de quando o pacote foi enviado,
#   "data": dados adicionais (opcional)
# }

class Host:
    def __init__(self, host_id, router_ip, router_port=9000):
        self.host_id = host_id
        self.router_ip = router_ip
        self.router_port = router_port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # UDP
        self.socket.settimeout(2.0)  # 2 segundos de timeout
        
        # Registrar-se com o roteador local
        self.register_with_router()
        
    def register_with_router(self):
        """Registra este host com seu roteador de gateway"""
        registration_msg = {
            "type": "host_registration",
            "host_id": self.host_id
        }
        self.socket.sendto(json.dumps(registration_msg).encode(), (self.router_ip, self.router_port))
        try:
            data, addr = self.socket.recvfrom(1024)
            response = json.loads(data.decode())
            if response.get("status") == "registered":
                print(f"Host {self.host_id} registrado com sucesso no roteador {self.router_ip}")
            else:
                print(f"Falha ao registrar com o roteador: {response}")
        except socket.timeout:
            print("Timeout ao aguardar resposta do roteador")
    
    def send_ping(self, destination_host, count=4):
        """Envia 'count' pings para o host de destino"""
        print(f"PING para host {destination_host} de {self.host_id}")
        
        statistics = {
            "transmitted": 0,
            "received": 0,
            "times": []
        }
        
        for seq in range(count):
            # Prepara o pacote de ping
            packet = {
                "type": "ping_request",
                "source_host": self.host_id,
                "destination_host": destination_host,
                "sequence": seq,
                "timestamp": time.time(),
                "data": "X" * 32  # Dados fictícios para simular payload
            }
            
            # Envia o pacote ao roteador
            start_time = time.time()
            self.socket.sendto(json.dumps(packet).encode(), (self.router_ip, self.router_port))
            statistics["transmitted"] += 1
            
            # Aguarda resposta
            try:
                data, addr = self.socket.recvfrom(1024)
                end_time = time.time()
                rtt = (end_time - start_time) * 1000  # em ms
                
                response = json.loads(data.decode())
                if response.get("type") == "ping_reply" and response.get("sequence") == seq:
                    statistics["received"] += 1
                    statistics["times"].append(rtt)
                    print(f"64 bytes de {destination_host}: seq={seq} tempo={rtt:.3f} ms")
                else:
                    print(f"Resposta inesperada: {response}")
            
            except socket.timeout:
                print(f"Requisição expirou para seq={seq}")
            
            time.sleep(1)  # Espera 1 segundo entre os pings
        
        # Exibe estatísticas
        if statistics["received"] > 0:
            avg_time = sum(statistics["times"]) / len(statistics["times"])
            min_time = min(statistics["times"])
            max_time = max(statistics["times"])
            
            print("\n--- Estatísticas de ping para {destination_host} ---")
            print(f"{statistics['transmitted']} pacotes transmitidos, {statistics['received']} recebidos, " +
                  f"{(statistics['transmitted'] - statistics['received']) * 100 / statistics['transmitted']:.1f}% perda de pacotes")
            print(f"rtt min/avg/max = {min_time:.3f}/{avg_time:.3f}/{max_time:.3f} ms")
        else:
            print(f"\n--- Nenhuma resposta de {destination_host} ---")
    
    def listen_for_pings(self):
        """Escuta por pings de outros hosts e responde"""
        print(f"Host {self.host_id} aguardando pings...")
        
        while True:
            try:
                data, addr = self.socket.recvfrom(1024)
                packet = json.loads(data.decode())
                
                if packet.get("type") == "ping_request" and packet.get("destination_host") == self.host_id:
                    # Responde ao ping
                    reply = {
                        "type": "ping_reply",
                        "source_host": self.host_id,
                        "destination_host": packet["source_host"],
                        "sequence": packet["sequence"],
                        "timestamp": time.time(),
                        "reply_to": packet["timestamp"]
                    }
                    self.socket.sendto(json.dumps(reply).encode(), addr)
                    print(f"Respondido ping de {packet['source_host']}, seq={packet['sequence']}")
            
            except socket.timeout:
                continue  # Apenas continua escutando
            except json.JSONDecodeError:
                print(f"Recebido pacote inválido de {addr}")
            except Exception as e:
                print(f"Erro ao processar pacote: {str(e)}")
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Simulador de ping para hosts virtuais')
    parser.add_argument('host_id', help='ID deste host')
    parser.add_argument('router_ip', help='IP do roteador local')
    parser.add_argument('--router-port', type=int, default=9000, help='Porta do roteador local')
    parser.add_argument('--ping', help='ID do host de destino para enviar ping')
    parser.add_argument('--count', type=int, default=4, help='Número de pings a enviar')
    parser.add_argument('--listen', action='store_true', help='Escuta por pings de outros hosts')
    
    args = parser.parse_args()
    
    client = Host(args.host_id, args.router_ip, args.router_port)
    
    if args.ping:
        client.send_ping(args.ping, args.count)
    
    if args.listen or not args.ping:
        client.listen_for_pings()