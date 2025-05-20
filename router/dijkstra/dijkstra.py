import heapq
from typing import Dict, List, Tuple, Union


def dijkstra(graph: Dict[str, Dict[str, int]], start: str) -> Dict[str, Union[int, float]]:
    """
    Implementação do algoritmo de Dijkstra para encontrar os caminhos mais curtos em um grafo com pesos não-negativos.
    
    Args:
        graph: Dicionário representando o grafo como lista de adjacência.
               Formato: {'nó_origem': {'nó_destino': peso, ...}, ...}
        start: Nó de origem para o cálculo dos caminhos mais curtos.
    
    Returns:
        Dicionário com as distâncias mínimas do nó inicial para todos os outros nós.
        Retorna infinito (float('inf')) para nós inalcançáveis.
    
    Exemplo:
        >>> graph = {'A': {'B': 1}, 'B': {'C': 2}}
        >>> dijkstra(graph, 'A')
        {'A': 0, 'B': 1, 'C': 3}
    """
    if start not in graph:
        raise ValueError("Nó inicial não existe no grafo.")
    
    # Inicializa todas as distâncias como infinito
    distances: Dict[str, Union[int, float]] = {node: float('inf') for node in graph}
    distances[start] = 0  # Distância do nó inicial para ele mesmo é zero
    
    # Fila de prioridade: pares (distância, nó)
    priority_queue: List[Tuple[Union[int, float], str]] = [(0, start)]
    
    while priority_queue:
        current_distance, current_node = heapq.heappop(priority_queue)
        
        # Se encontramos um caminho melhor anteriormente, ignora este
        if current_distance > distances[current_node]:
            continue
        
        # Explora todos os vizinhos do nó atual
        for neighbor, weight in graph[current_node].items():
            distance = current_distance + weight
            
            # Se encontrou um caminho melhor para o vizinho
            if distance < distances[neighbor]:
                distances[neighbor] = distance
                heapq.heappush(priority_queue, (distance, neighbor))
    
    return distances


if __name__ == '__main__':
    # Grafo de exemplo (lista de adjacência)
    graph = {
        0: {1: 4, 7: 8},
        1: {0: 4, 2: 8, 7: 11},
        2: {1: 8, 3: 7, 8: 2},
        3: {2: 7, 4: 9, 5: 14},
        4: {3: 9, 5: 10},
        5: {3: 14, 4: 10, 6: 2},
        6: {5: 2, 7: 1, 8: 6},
        7: {0: 8, 1: 11, 6: 1, 8: 7},
        8: {2: 2, 6: 6, 7: 7}
    }


    # Executando o algoritmo a partir do nó 'A'
    result = dijkstra(graph, 0)
    print("Distâncias mais curtas a partir de A:")
    
    for k, v in result.items():
        print(f'{k}: {v}')