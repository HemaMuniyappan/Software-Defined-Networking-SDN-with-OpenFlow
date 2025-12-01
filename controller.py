# controller.py
# Ryu app: learning switch + reactive flow install + basic failover handling
# Compatible with OpenFlow 1.3 and Ryu

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.lib.packet import packet, ethernet, ether_types
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub
from ryu.topology import api as topo_api
from ryu.topology.event import EventSwitchEnter, EventSwitchLeave, EventPortAdd, EventPortDelete
import time
import logging

LOG = logging.getLogger('ryu.app.controller')
LOG.setLevel(logging.INFO)


class SimpleFailoverController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    # idle_timeout (seconds) for installed flows
    FLOW_IDLE_TIMEOUT = 30

    def __init__(self, *args, **kwargs):
        super(SimpleFailoverController, self).__init__(*args, **kwargs)
        # mac_to_port: dpid -> { mac: port_no }
        self.mac_to_port = {}
        # datapaths: dpid -> datapath object
        self.datapaths = {}
        # start a watcher thread for dead datapaths (optional)
        self.monitor_thread = hub.spawn(self._monitor)

    @set_ev_cls(EventSwitchEnter)
    def switch_enter_handler(self, ev):
        dp = ev.switch.dp
        dpid = dp.id
        LOG.info("Switch entered: %s", dpid)
        self.datapaths[dpid] = dp
        self.mac_to_port.setdefault(dpid, {})

    @set_ev_cls(EventSwitchLeave)
    def switch_leave_handler(self, ev):
        dp = ev.switch.dp
        dpid = dp.id
        LOG.info("Switch left: %s", dpid)
        if dpid in self.datapaths:
            del self.datapaths[dpid]
        if dpid in self.mac_to_port:
            del self.mac_to_port[dpid]

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofproto = dp.ofproto
        parser = dp.ofproto_parser
        LOG.info("Switch %s connected (features)", dp.id)

        # install table-miss flow entry (send to controller)
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=dp, priority=0, match=match, instructions=inst)
        dp.send_msg(mod)

    def _monitor(self):
        while True:
            # This loop can be extended to poll stats or do periodic tasks
            hub.sleep(10)

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def state_change_handler(self, ev):
        dp = ev.datapath
        if not dp:
            return
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[dp.id] = dp
        elif ev.state == DEAD_DISPATCHER:
            if dp.id in self.datapaths:
                del self.datapaths[dp.id]

    @set_ev_cls(EventPortDelete)
    def port_delete_handler(self, ev):
        # When ports are removed (link failure), clear related learned entries
        port = ev.port
        dpid = ev.port.dpid
        port_no = ev.port.port_no
        LOG.info("Port deleted on switch %s port %s", dpid, port_no)
        # Remove mac entries that mapped to this port so controller re-learns
        if dpid in self.mac_to_port:
            macs_to_remove = [m for m, p in self.mac_to_port[dpid].items() if p == port_no]
            for m in macs_to_remove:
                LOG.info("Removing learned MAC %s on switch %s due to port delete", m, dpid)
                del self.mac_to_port[dpid][m]

            # Optional: flush all flows on this switch to force re-install via new path
            if dpid in self.datapaths:
                self._flush_flows(self.datapaths[dpid])

    def _flush_flows(self, datapath):
        """Delete all non-table-miss flows (priority > 0)"""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        match = parser.OFPMatch()
        mod = parser.OFPFlowMod(datapath=datapath,
                                command=ofproto.OFPFC_DELETE,
                                out_port=ofproto.OFPP_ANY,
                                out_group=ofproto.OFPG_ANY,
                                priority=1,
                                match=match)
        datapath.send_msg(mod)
        LOG.info("Flushed flows on switch %s", datapath.id)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """Handle incoming packets (reactive learning switch)"""
        msg = ev.msg
        dp = msg.datapath
        dpid = dp.id
        ofproto = dp.ofproto
        parser = dp.ofproto_parser

        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        dst = eth.dst
        src = eth.src

        # ignore LLDP
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        self.mac_to_port.setdefault(dpid, {})

        # learn src MAC
        if src not in self.mac_to_port[dpid]:
            LOG.info("Learned %s on switch %s port %s", src, dpid, in_port)
        self.mac_to_port[dpid][src] = in_port

        # determine output port
        out_port = None
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            # destination unknown -> flood
            out_port = ofproto.OFPP_FLOOD

        # build actions
        actions = [parser.OFPActionOutput(out_port)]

        # If output is a normal port (not flood), install a flow
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            # install flow with idle_timeout; use priority 10
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
            mod = parser.OFPFlowMod(datapath=dp, priority=10, match=match,
                                    instructions=inst, idle_timeout=self.FLOW_IDLE_TIMEOUT)
            dp.send_msg(mod)
            LOG.info("Installed flow on %s: %s -> out %s", dpid, dst, out_port)

        # send packet out (for flood or to the known out_port)
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        out = parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        dp.send_msg(out)
