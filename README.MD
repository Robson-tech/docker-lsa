# 🛰️ Simulador de Rede com Roteadores e Protocolo de Estado de Enlace

Este projeto simula uma rede de roteadores e hosts que trocam mensagens usando o protocolo de roteamento baseado em **estado de enlace (Link-State Routing)**. A simulação é feita em Python com comunicação via sockets UDP, e cada nó da rede é implementado como um processo separado.

---

## 📖 Descrição

O objetivo deste projeto é implementar uma rede distribuída de roteadores que compartilham informações de conectividade (LSAs - Link State Advertisements), constroem uma **Link State Database (LSDB)** e calculam rotas com base no algoritmo de Dijkstra. A rede também permite que hosts enviem pacotes de dados usando os caminhos calculados.

Este simulador foi projetado para ser leve, modular e extensível, e pode futuramente ser executado em contêineres Docker para simular ambientes distribuídos reais.

---

## ⚙️ Como Funciona

- Cada **roteador** envia periodicamente um LSA contendo seus vizinhos e os custos dos enlaces.
- Os LSAs são retransmitidos por todos os roteadores, garantindo que a **LSDB** fique sincronizada entre eles.
- Após cada atualização relevante, os roteadores recalculam a tabela de roteamento usando o **algoritmo de Dijkstra**.
- Cada **host** pode enviar pacotes de dados para outros nós da rede, que são encaminhados por múltiplos roteadores com base nas rotas computadas.
- A comunicação é feita por meio de **sockets UDP** para simular redes não confiáveis e assíncronas.
- As mensagens são serializadas em **JSON**.

---

## 🌐 Topologia da Rede

A topologia abaixo representa os roteadores (R1–R5) conectados por enlaces com custos diferentes, e dois hosts (H1 e H2) conectados aos roteadores R1 e R5, respectivamente.

![Topologia da Rede](docs/topologia.png)

> *Legenda:*
> - Os nós **R1 a R5** são roteadores com enlaces bidirecionais e custos definidos.
> - Os nós **H1 e H2** são hosts conectados a **R1** e **R5**, respectivamente.
> - Cada enlace possui um **custo**, utilizado para calcular o caminho mais curto.

---

## 📡 Justificativa do Protocolo Escolhido

Este projeto optou por implementar um protocolo de **estado de enlace (Link-State Routing)** em vez de protocolos de **vetor de distância** como RIP, pelos seguintes motivos:

- ✅ **Precisão Global:** Cada roteador mantém uma visão completa da topologia da rede.
- ✅ **Convergência Rápida:** Com base no algoritmo de Dijkstra, as rotas são recalculadas eficientemente após cada mudança.
- ✅ **Evita Loops:** O conhecimento da topologia completa reduz drasticamente o risco de roteamento em loop.
- ✅ **Escalabilidade:** Mais adequado para redes maiores, pois a propagação de LSAs é controlada por números de sequência.

Este modelo é inspirado em protocolos reais como o **OSPF (Open Shortest Path First)**, utilizado em redes de médio e grande porte.

---
