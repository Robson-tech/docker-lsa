import unittest

from dijkstra import dijkstra


class TestDijkstra(unittest.TestCase):
    def test_grafo_simples(self):
        graph = {
            'A': {'B': 1, 'C': 4},
            'B': {'C': 2, 'D': 5},
            'C': {'D': 1},
            'D': {}
        }
        result = dijkstra(graph, 'A')
        expected = {'A': 0, 'B': 1, 'C': 3, 'D': 4}
        self.assertEqual(result, expected)

    def test_grafo_com_no_inalcancavel(self):
        graph = {
            'A': {'B': 1},
            'B': {'C': 2},
            'C': {},
            'D': {}  # Nó desconectado
        }
        result = dijkstra(graph, 'A')
        expected = {'A': 0, 'B': 1, 'C': 3, 'D': float('inf')}
        self.assertEqual(result, expected)

    def test_ciclo_no_grafo(self):
        graph = {
            'A': {'B': 2},
            'B': {'C': 2},
            'C': {'A': 1}
        }
        result = dijkstra(graph, 'A')
        expected = {'A': 0, 'B': 2, 'C': 4}
        self.assertEqual(result, expected)

    def test_um_unico_no(self):
        graph = {'A': {}}
        result = dijkstra(graph, 'A')
        expected = {'A': 0}
        self.assertEqual(result, expected)

    def test_grafo_vazio(self):
        graph = {}

        with self.assertRaises(ValueError) as context:
            dijkstra(graph, 'A')
            
        self.assertEqual(str(context.exception), "Nó inicial não existe no grafo.")


if __name__ == '__main__':
    unittest.main()
