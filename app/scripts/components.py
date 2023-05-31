import collections
import logging
import sys
import matplotlib.pyplot as plt
import networkx as nx
from logging.handlers import RotatingFileHandler
from timeit import default_timer as timer
import traceback

# create and configure logger
filename = "logs2/components_size_aug14.log"
logging.basicConfig(level=logging.INFO,
                    handlers=[RotatingFileHandler(filename, maxBytes=1000000000, backupCount=100, mode='a'),
                              logging.StreamHandler(sys.stdout)],
                    format="[%(asctime)s] %(message)s",
                    datefmt='%Y-%m-%dT%H:%M:%S', )
logger = logging.getLogger()


# Main
if __name__ == '__main__':
    try:
        # Graph Analysis
        start = timer()

        digraph = nx.read_gpickle('output/multidigraph_without_loops_july.gpickle')
        logger.info("Graph Reading COMPLETED...")

        # component size histogram
        plt.figure(figsize=(12, 8))
        fig, ax = plt.subplots(2)
        fig.tight_layout()
        fig.suptitle('Components Size Distribution of Polkadot Transactions Graph')

        scc_component_size = sorted(nx.strongly_connected_components(digraph), key=len, reverse=True)
        scc_sizes = [len(comp) for comp in scc_component_size]
        val2, cnt2 = zip(*collections.Counter(scc_sizes).items())
        # pl = plt.bar(val2, cnt2, width=0.30, color='b', label='SCC')
        pl = ax[0].bar(val2, cnt2, width=0.70, color='b', label='SCC')
        ax[0].legend(loc="upper right")
        for bar in pl:
            ax[0].annotate(bar.get_height(),
                           xy=(bar.get_x() + 0.07, bar.get_height() + 8),
                           fontsize=6)

        wcc_component_size = sorted(nx.weakly_connected_components(digraph), key=len, reverse=True)
        wcc_sizes = [len(comp) for comp in wcc_component_size]
        val1, cnt1 = zip(*collections.Counter(wcc_sizes).items())
        pl = ax[1].bar(val1, cnt1, width=0.70, color='g', label='WCC')
        for bar in pl:
            ax[1].annotate(bar.get_height(),
                           xy=(bar.get_x() + 0.07, bar.get_height() + 8),
                           fontsize=6)

        ax[0].set_xticks([v + 0.4 for v in val1])
        ax[0].set_xticklabels(val1)
        ax[1].set_xticks([v + 0.4 for v in val1])
        ax[1].set_xticklabels(val1)

        ax[0].set_xscale('log')
        ax[0].set_yscale('log')
        ax[1].set_xscale('log')
        ax[1].set_yscale('log')

        plt.xlabel('Component Size (log)')
        plt.ylabel('Fraction of Nodes (log)')
        plt.legend(loc="upper right")
        fig.tight_layout()
        plt.savefig('output2/component/hist-component-dist.png', bbox_inches='tight')

        logger.info("=======================================END======================================")
        logger.info("Graph Analysis Total Execution Time (seconds): {}".format(timer() - start))

    except Exception as err:
        logger.error(traceback.format_exc())
