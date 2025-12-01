# Software-Defined-Networking-SDN-with-OpenFlow
A simple SDN project using the Ryu controller and Mininet. Implements reactive MAC-learning, installs OpenFlow 1.3 flow rules, and forwards packets dynamically. Tested on a single-switch topology with connectivity checks and Wireshark OpenFlow packet capture.

# Simple SDN Routing using Ryu & Mininet

This project demonstrates a basic Software-Defined Networking (SDN) setup using:

- **Ryu controller (OpenFlow 1.3)**
- **Mininet**
- **Wireshark for OpenFlow packet capture**

The controller implements:
- MAC learning
- Reactive forwarding
- Flow rule installation

This is the exact setup used in the screenshots.

---

## 📌 Project Files

| File | Description |
|------|-------------|
| `simple_routing.py` | Ryu controller implementing simple reactive routing |
| `README.md` | Project documentation |

---

## 🛠 Requirements
- Ubuntu 18.04 / 20.04 / 22.04
- Python 3
- Mininet
- Ryu SDN Controller
- Wireshark (optional)

Install Ryu:
```bash
pip install ryu
