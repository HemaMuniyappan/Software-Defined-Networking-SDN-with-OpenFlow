# topology.py
# Mininet custom topology: 2 hosts, 4 switches, redundant paths
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info

class MultiPathTopo(Topo):
    def build(self):
        # Create switches
        s1 = self.addSwitch('s1')  # left-top
        s2 = self.addSwitch('s2')  # left-bottom
        s3 = self.addSwitch('s3')  # right-top
        s4 = self.addSwitch('s4')  # right-bottom

        # Create hosts
        h1 = self.addHost('h1', ip='10.0.0.1/24')
        h2 = self.addHost('h2', ip='10.0.0.2/24')

        # Connect hosts to s1 and s4 (primary path)
        self.addLink(h1, s1)
        self.addLink(h2, s4)

        # Interconnect switches with redundant paths:
        # primary path: s1 - s2 - s3 - s4
        # alternate path: s1 - s3 - s4 (direct cross link)
        self.addLink(s1, s2)
        self.addLink(s2, s3)
        self.addLink(s3, s4)

        # alternate cross links
        self.addLink(s1, s3)
        self.addLink(s2, s4)

def run():
    topo = MultiPathTopo()
    # Controller is expected to be a remote Ryu controller (default port 6633/6653)
    net = Mininet(topo=topo, controller=RemoteController, switch=OVSSwitch, link=TCLink, autoSetMacs=True)
    net.start()
    info("Running pingall to test connectivity\n")
    net.pingAll()
    CLI(net)
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    run()
