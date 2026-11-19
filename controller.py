import os, time
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub
from ryu.lib.packet import packet, ipv4

SERVER_IP, SERVER_PORT = "10.0.0.10", 1
BG_IP = "10.0.0.20"
PORT_OF = {SERVER_IP: 1, "10.0.0.1": 2, "10.0.0.2": 3, "10.0.0.3": 4, BG_IP: 5}
REG_PORT, GAME_PORT = 5001, 5000
HIGH_MBPS, LOW_MBPS = 7.0, 5.0
MODE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mode.txt")


def get_mode():
    try:
        m = open(MODE_FILE).read().strip()
        return m if m in ("baseline", "static", "dynamic") else "dynamic"
    except OSError:
        return "dynamic"


class GameSDN(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.dp = None
        self.players = set()
        self.congested = False
        self.low_count = 0
        self.last = None
        hub.spawn(self.monitor)

    def add_flow(self, dp, prio, match, actions):
        p = dp.ofproto_parser
        inst = [p.OFPInstructionActions(dp.ofproto.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(p.OFPFlowMod(datapath=dp, priority=prio, match=match, instructions=inst))

    def want_fast(self):
        mode = get_mode()
        return mode == "static" or (mode == "dynamic" and self.congested)

    def player_rules(self, ip):
        dp, p = self.dp, self.dp.ofproto_parser
        to_server = ([p.OFPActionSetQueue(1)] if self.want_fast() else []) + \
                    [p.OFPActionOutput(SERVER_PORT)]
        self.add_flow(dp, 30, p.OFPMatch(eth_type=0x0800, ip_proto=17, ipv4_src=ip,
                                         ipv4_dst=SERVER_IP, udp_dst=GAME_PORT), to_server)
        self.add_flow(dp, 30, p.OFPMatch(eth_type=0x0800, ip_proto=17, ipv4_dst=ip,
                                         udp_src=GAME_PORT), [p.OFPActionOutput(PORT_OF[ip])])

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def on_connect(self, ev):
        dp = self.dp = ev.msg.datapath
        ofp, p = dp.ofproto, dp.ofproto_parser
        self.players, self.congested, self.last = set(), False, None
        self.logger.info("EVENT switch_connected dpid=%s mode=%s", dp.id, get_mode())
        self.add_flow(dp, 0, p.OFPMatch(), [])
        self.add_flow(dp, 10, p.OFPMatch(eth_type=0x0806), [p.OFPActionOutput(ofp.OFPP_FLOOD)])
        for ip, port in PORT_OF.items():
            out = [p.OFPActionOutput(port)]
            self.add_flow(dp, 10, p.OFPMatch(eth_type=0x0800, ip_proto=1, ipv4_dst=ip), out)
            self.add_flow(dp, 10, p.OFPMatch(eth_type=0x0800, ip_proto=17, ipv4_dst=ip,
                                             udp_src=REG_PORT), out)
        self.add_flow(dp, 10, p.OFPMatch(eth_type=0x0800, ip_proto=17, ipv4_src=BG_IP,
                                         ipv4_dst=SERVER_IP), [p.OFPActionOutput(SERVER_PORT)])
        self.add_flow(dp, 10, p.OFPMatch(eth_type=0x0800, ip_proto=17, ipv4_dst=BG_IP),
                      [p.OFPActionOutput(PORT_OF[BG_IP])])
        self.add_flow(dp, 20, p.OFPMatch(eth_type=0x0800, ip_proto=17, ipv4_dst=SERVER_IP,
                                         udp_dst=REG_PORT),
                      [p.OFPActionSetQueue(1), p.OFPActionOutput(SERVER_PORT),
                       p.OFPActionOutput(ofp.OFPP_CONTROLLER, 65535)])

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def on_packet_in(self, ev):
        msg = ev.msg
        ip = packet.Packet(msg.data).get_protocol(ipv4.ipv4)
        if ip is None or ip.src not in PORT_OF or ip.src in (SERVER_IP, BG_IP):
            return
        if not msg.data[14 + ip.header_length * 4 + 8:].startswith(b"REG"):
            return
        self.players.add(ip.src)
        self.player_rules(ip.src)
        self.logger.info("EVENT player_registered ip=%s mode=%s fast_lane=%s",
                         ip.src, get_mode(), self.want_fast())

    def monitor(self):
        while True:
            hub.sleep(1)
            if self.dp:
                p = self.dp.ofproto_parser
                self.dp.send_msg(p.OFPPortStatsRequest(self.dp, 0, self.dp.ofproto.OFPP_ANY))

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def on_stats(self, ev):
        for s in ev.msg.body:
            if s.port_no != SERVER_PORT:
                continue
            now = time.time()
            if self.last:
                mbps = (s.tx_bytes - self.last[1]) * 8 / (now - self.last[0]) / 1e6
                self.decide(mbps)
            self.last = (now, s.tx_bytes)

    def decide(self, mbps):
        if get_mode() != "dynamic":
            self.congested, self.low_count = False, 0
            return
        if not self.congested and mbps > HIGH_MBPS:
            self.congested = True
            self.logger.info("EVENT congestion_detected load=%.1f Mbit/s -> fast lane ON", mbps)
            for ip in self.players:
                self.player_rules(ip)
        elif self.congested:
            self.low_count = self.low_count + 1 if mbps < LOW_MBPS else 0
            if self.low_count >= 2:
                self.congested, self.low_count = False, 0
                self.logger.info("EVENT congestion_cleared load=%.1f Mbit/s -> fast lane OFF", mbps)
                for ip in self.players:
                    self.player_rules(ip)
