import os.path
import numpy as np
from collections import defaultdict


class CSFGraph:
    """
    Compressed Storage Format graph class (cannot be modified after graph construction)
    """

    class Edge:
        """
        Class to organize edge data during the construction of the graph. We do not need
        Edge objects in the final graph (edges are encoded using arrays)
        """

        def __init__(self, nA, nB, w):
            self.nodeA = nA
            self.nodeB = nB
            self.weight = w

        def get_edge_type_string(self):
            '''
            For the summary output of the graph, we would like to show how many homogeneous and
            how many heterogeneous edges there are. We expect nodes types to be coded using the
            first characters of the nodes. For instance, g1-g3 would we coded as 'gg' and 'g1-p45'
            would be coded as 'gp'. We assume an undirected graph. We sort the characters alphabetically.
            :return:
            '''
            na = self.nodeA[0]
            nb = self.nodeB[0]
            return "".join(sorted([na, nb]))

        def __hash__(self):
            """
            Do not include weight in the hash function, we are interested in
            the edges. Users are responsible for not including the same edge
            twice with different weights
            """
            return hash((self.nodeA, self.nodeB))

        def __eq__(self, other):
            """
            For equality, we disregard the edge weight
            """
            return (self.nodeA, self.nodeB) == (other.nodeA, other.nodeB)

        def __ne__(self, other):
            return not (self == other)

        def __lt__(self, other):
            """
            We sort on (1) source node and (2) destination node
            """
            if self.nodeA == other.nodeA:
                return self.nodeB < other.nodeB
            return self.nodeA < other.nodeA

    def __init__(self, filepath):
        if filepath is None:
            raise TypeError("Need to pass path of file with edges")
        if not isinstance(filepath, str):
            raise TypeError("filepath argument must be string")
        if not os.path.exists(filepath):
            raise TypeError("Could not find graph file {}".format(filepath))
        nodes = set()
        edges = set()

        self.edgetype2count_dictionary = defaultdict(int)
        self.nodetype2count_dictionary = defaultdict(int)
        with open(filepath) as f:
            for line in f:
                # print(line)
                fields = line.rstrip('\n').split()
                if not len(fields) == 3:
                    print("[ERROR] Skipping malformed line with {} fields ({}).".format(len(fields), line))
                    continue
                nodeA = fields[0]
                nodeB = fields[1]
                try:
                    weight = float(fields[2])
                except Exception as e:
                    print("[ERROR] Could not parse weight field (must be an integer): {}".format(fields[2]))
                    continue
                nodes.add(nodeA)
                nodes.add(nodeB)
                edge = CSFGraph.Edge(nodeA, nodeB, weight)
                inverse_edge = CSFGraph.Edge(nodeB, nodeA, weight)
                edges.add(edge)
                edges.add(inverse_edge)
                self.edgetype2count_dictionary[edge.get_edge_type_string()] += 1
        # When we get here, we can create the graph
        # print("Got {} nodes and {} edges".format(len(nodes), len(edges)))
        # convert the sets to lists
        # sort the edges on their source element
        # this will give us blocks of edges that start from the same source
        node_list = sorted(nodes)
        edge_list = sorted(edges)
        self.node_to_index_map = defaultdict(int)
        self.index_to_node_map = defaultdict(str)
        total_edge_count = len(edge_list)
        total_vertex_count = len(node_list)
        self.edge_to = np.zeros(total_edge_count, dtype=np.int32)
        self.edge_weight = np.zeros(total_edge_count, dtype=np.int32)
        # self.proportion_of_different_neighbors = np.zeros(total_vertex_count, dtype=np.float32)
        self.offset_to_edge_ = np.zeros(total_vertex_count + 1, dtype=np.int32)
        for i in range(len(node_list)):
            node = node_list[i]
            self.node_to_index_map[node] = i
            self.index_to_node_map[i] = node
        # We perform two passes
        # In the first pass, we count how many edges emanate from each source
        index2edge_count = defaultdict(int)
        for edge in edge_list:
            source_index = self.node_to_index_map[edge.nodeA]
            index2edge_count[source_index] += 1
        # second pass -- set the offset_to_edge_ according to the number of edges
        # emanating from each source ids.
        offset = 0
        self.offset_to_edge_[0] = 0
        i = 0
        for n in node_list:
            nodetype = n[0]
            self.nodetype2count_dictionary[nodetype] += 1
            source_index = self.node_to_index_map[n]
            n_edges = index2edge_count[source_index]
            # n_edges can be zero here, that is OK
            i += 1
            offset += n_edges
            self.offset_to_edge_[i] = offset
        # third pass -- add the actual edges
        # use the offset variable to keep track of how many edges we have already
        # entered for a given source index
        current_source_index = -1;
        offset = 0
        j = 0
        for edge in edge_list:
            source_index = self.node_to_index_map[edge.nodeA]
            dest_index = self.node_to_index_map[edge.nodeB]
            if source_index != current_source_index:
                current_source_index = source_index;
                offset = 0;  # start a new block
            else:
                offset += 1  # go to next index (for a new destination of the previous source)
            self.edge_to[j] = dest_index
            self.edge_weight[j] = edge.weight
            j += 1

    def nodes(self):
        return list(self.node_to_index_map.keys())

    def nodes_as_integers(self):
        return list(self.index_to_node_map.keys())

    def node_count(self):
        return len(self.node_to_index_map)

    def edge_count(self):
        return len(self.edge_to)

    def weight(self, source, dest):
        """
        :param source: index (integer) of source node
        :param dest: index (integer) of destination node
        :return: weight of edge from source to dest
        Assume that there is a valid edge between source and dest
        """
        source_idx = self.node_to_index_map[source]
        dest_idx = self.node_to_index_map[dest]
        for i in range(self.offset_to_edge_[source_idx], self.offset_to_edge_[source_idx + 1]):
            if dest_idx == self.edge_to[i]:
                return self.edge_weight[i]
        # We should never get here
        raise TypeError("Could not identify edge between {} and {}".format(source, dest))

    def neighbors(self, source):
        """
        :param source: index (integer) of source node
        :return: list of indices of neighbors
        """
        nbrs = []
        source_idx = self.node_to_index_map[source]
        for i in range(self.offset_to_edge_[source_idx], self.offset_to_edge_[source_idx + 1]):
            nbr = self.index_to_node_map[self.edge_to[i]]
            nbrs.append(nbr)
        return nbrs

    def has_edge(self, src, dest):
        """
        Check if the graph hhas an edge between src and dest
        """
        source_idx = self.node_to_index_map[src]
        dest_idx = self.node_to_index_map[dest]
        for i in range(self.offset_to_edge_[source_idx], self.offset_to_edge_[source_idx + 1]):
            nbr_idx = self.edge_to[i]
            if nbr_idx == dest_idx:
                return True
        return False

    def same_nodetype(self, n1, n2):
        """
        We encode the nodetype using the first character of the node label. For instance, g1 and g2
        have the same nodetype but g2 and p5 do not.
        """
        if n1[0] == n2[0]:
            return True
        else:
            return False

    def edges(self):
        """
        return a list of tuples with all edges in the graph
        each tuple is like ('2', '3')
        """
        edge_list = []
        for source_idx in range(len(self.offset_to_edge_) - 1):
            src = self.index_to_node_map[source_idx]
            for j in range(self.offset_to_edge_[source_idx], self.offset_to_edge_[source_idx + 1]):
                nbr_idx = self.edge_to[j]
                nbr = self.index_to_node_map[nbr_idx]
                tpl = (src, nbr)
                edge_list.append(tpl)
        return edge_list

    def get_node_to_index_map(self):
        """
        This is equivalent to the 'dictionary' of word2vec, where the key is the word (or node label) and the
        value is the corresponding integer code
        :return: dictionary of node to int indices
        """
        return self.node_to_index_map

    def get_index_to_node_map(self):
        """
        This is equivalent to the 'reverse dictionary' of word2vec, where the key is the integer index and the
        value is the corresponding word (node label)
        :return:
        """
        return self.index_to_node_map

    def __str__(self):
        return 'CSFGraph(nodes: %d; edges: %d)' % (self.node_count(),  self.edge_count())

    def print_edge_type_distribution(self):
        """
        This function is intended to be used for debugging or logging.
        It returns a string with the total counts of edges according to type.
        If the graph only has one node type, it just shows the total edge count.
        :return:
        """
        for n, count in self.nodetype2count_dictionary.items():
            print("node type %s - count: %d" % (n,count))
        if len(self.edgetype2count_dictionary) < 2:
            print( "edge count: %d" % self.edge_count() )
        else:
            edgecounts = []
            for category, count in self.edgetype2count_dictionary.items():
                print("%s - count: %d" % (category, count) )

