"""
network/scanner.py — JARVIS Ağ Tarayıcı
- ARP ile yerel ağdaki tüm cihazları tespit eder
- MAC adresine göre cihazları tanır ve isimlendirir
- Cihaz durumunu (online/offline) takip eder
- Yönetici yetkisi gerektirir (scapy için)
"""

import asyncio
import json
import os
import socket
import time
from datetime import datetime
from typing import Optional

try:
    from scapy.all import ARP, Ether, srp, conf
    conf.verb = 0  # Scapy çıktısını sustur
    SCAPY_OK = True
except ImportError:
    SCAPY_OK = False
    print("⚠️  scapy kurulu değil: pip install scapy")

# ── Bilinen Cihaz Veritabanı ──────────────────────────────────────────────────
# MAC prefix → üretici adı (ilk 8 karakter: XX:XX:XX)
MAC_VENDORS = {
    "b8:27:eb": "Raspberry Pi",
    "dc:a6:32": "Raspberry Pi",
    "e4:5f:01": "Raspberry Pi",
    "00:26:bb": "Apple",
    "f4:f2:6d": "Apple",
    "ac:bc:32": "Apple",
    "fc:fb:fb": "Tapo/TP-Link",
    "50:c7:bf": "Tapo/TP-Link",
    "30:de:4b": "Samsung",
    "8c:77:12": "Samsung TV",
    "78:bd:bc": "Samsung",
    "00:15:c1": "Sony PlayStation",
    "00:1f:a7": "Sony PlayStation",
    "00:19:c5": "Sony PlayStation",
    "f8:d0:ac": "Sony PlayStation",
    "70:45:58": "Huawei/Modem",
    "00:e0:fc": "Huawei",
}

# Kullanıcının kendi cihaz etiketleri (.env veya devices.json'dan yüklenir)
DEVICES_FILE = os.path.join(os.path.dirname(__file__), "..", "devices.json")


class NetworkDevice:
    def __init__(self, ip: str, mac: str, name: str = None, vendor: str = None):
        self.ip = ip
        self.mac = mac.lower()
        self.name = name or self._auto_name(vendor)
        self.vendor = vendor or "Bilinmeyen"
        self.first_seen = datetime.now().isoformat()
        self.last_seen = datetime.now().isoformat()
        self.online = True

    def _auto_name(self, vendor: str) -> str:
        if not vendor:
            return "Bilinmeyen Cihaz"
        return vendor

    def touch(self):
        self.last_seen = datetime.now().isoformat()
        self.online = True

    def to_dict(self) -> dict:
        return {
            "ip": self.ip,
            "mac": self.mac,
            "name": self.name,
            "vendor": self.vendor,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "online": self.online,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NetworkDevice":
        dev = cls(d["ip"], d["mac"], d.get("name"), d.get("vendor"))
        dev.first_seen = d.get("first_seen", dev.first_seen)
        dev.last_seen = d.get("last_seen", dev.last_seen)
        dev.online = d.get("online", True)
        return dev

    def __str__(self):
        status = "🟢" if self.online else "🔴"
        return f"{status} {self.name} | {self.ip} | {self.mac}"


class NetworkScanner:
    def __init__(self):
        self.devices: dict[str, NetworkDevice] = {}  # mac → device
        self.last_scan: Optional[datetime] = None
        self._load_known_devices()

    # ── Cihaz Kayıtları ───────────────────────────────────────────────────────
    def _load_known_devices(self):
        """Daha önce kaydedilmiş cihazları yükle."""
        if os.path.exists(DEVICES_FILE):
            try:
                with open(DEVICES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for mac, d in data.items():
                    self.devices[mac] = NetworkDevice.from_dict(d)
                print(f"📂 {len(self.devices)} bilinen cihaz yüklendi.")
            except Exception as e:
                print(f"⚠️ Cihaz veritabanı yüklenemedi: {e}")

    def save_devices(self):
        """Cihazları dosyaya kaydet."""
        try:
            with open(DEVICES_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {mac: dev.to_dict() for mac, dev in self.devices.items()},
                    f, ensure_ascii=False, indent=2
                )
        except Exception as e:
            print(f"⚠️ Kaydetme hatası: {e}")

    def label_device(self, mac: str, name: str) -> bool:
        """Bir cihaza özel isim ver. 'Jarvis, bu cihazın adı PS3 olsun'"""
        mac = mac.lower()
        if mac in self.devices:
            self.devices[mac].name = name
            self.save_devices()
            return True
        return False

    def label_by_ip(self, ip: str, name: str) -> bool:
        for dev in self.devices.values():
            if dev.ip == ip:
                dev.name = name
                self.save_devices()
                return True
        return False

    # ── MAC → Vendor ──────────────────────────────────────────────────────────
    def _get_vendor(self, mac: str) -> str:
        prefix = mac[:8].lower()
        prefix6 = mac[:5].lower()
        return MAC_VENDORS.get(prefix) or MAC_VENDORS.get(prefix6) or "Bilinmeyen"

    # ── ARP Tarama ────────────────────────────────────────────────────────────
    async def scan(self, network: str = None) -> list[NetworkDevice]:
        """
        ARP broadcast ile ağdaki tüm cihazları tarar.
        network: '192.168.1.0/24' formatında. None ise otomatik tespit.
        """
        if not SCAPY_OK:
            return []

        if not network:
            network = self._detect_network()

        print(f"🔍 Ağ taranıyor: {network}")

        loop = asyncio.get_event_loop()
        try:
            results = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: self._arp_scan(network)),
                timeout=15.0
            )
        except asyncio.TimeoutError:
            print("⚠️ Tarama zaman aşımı.")
            return list(self.devices.values())

        # Mevcut cihazları offline yap, bulunanları güncelle
        for dev in self.devices.values():
            dev.online = False

        # ── Config İçindeki Statik IP'leri Oku ──
        known_ips_from_config = {}
        config_path = os.path.join(os.path.dirname(__file__), "..", "config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                c = json.load(f)
                known_ips_from_config = c.get("network", {}).get("known_ips", {})
        except Exception:
            pass

        found = []
        for ip, mac in results:
            vendor = self._get_vendor(mac)
            
            # Eğer kullanıcı config'e bu IP için isim yazmışsa, o ismi al
            static_name = known_ips_from_config.get(ip)
            
            if mac in self.devices:
                self.devices[mac].ip = ip
                # Eğer config'te bir isim varsa, mevcut ismin (kötü/eski olsa bile) üzerine yaz
                if static_name:
                    self.devices[mac].name = static_name
                self.devices[mac].touch()
            else:
                dev = NetworkDevice(ip, mac, name=static_name, vendor=vendor)
                self.devices[mac] = dev

            self.devices[mac].online = True
            found.append(self.devices[mac])

        self.last_scan = datetime.now()
        self.save_devices()
        print(f"✅ Tarama tamamlandı: {len(found)} cihaz bulundu.")
        return found

    def _arp_scan(self, network: str) -> list[tuple]:
        """Scapy ARP tarama (blocking, executor'da çalışır)."""
        arp = ARP(pdst=network)
        ether = Ether(dst="ff:ff:ff:ff:ff:ff")
        packet = ether / arp
        answered, _ = srp(packet, timeout=3, retry=1)
        return [(rcv.psrc, rcv.hwsrc) for _, rcv in answered]

    def _detect_network(self) -> str:
        """Mevcut ağ aralığını otomatik tespit et."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            # /24 subnet varsay
            parts = local_ip.rsplit(".", 1)
            return f"{parts[0]}.0/24"
        except Exception:
            return "192.168.1.0/24"

    # ── Cihaz Arama ───────────────────────────────────────────────────────────
    def find(self, query: str) -> Optional[NetworkDevice]:
        """İsim, IP veya MAC ile cihaz bul."""
        query = query.lower().strip()
        for dev in self.devices.values():
            if (query in dev.name.lower() or
                    query == dev.ip or
                    query == dev.mac):
                return dev
        return None

    def get_online(self) -> list[NetworkDevice]:
        return [d for d in self.devices.values() if d.online]

    # ── Sesli Rapor ───────────────────────────────────────────────────────────
    def get_network_report(self) -> str:
        """JARVIS'in sesli raporlayacağı ağ özeti."""
        online = self.get_online()
        if not online:
            return "Ağda hiç cihaz tespit edemedim Patron. Tarama yetkim var mı?"

        lines = [f"Ağda {len(online)} cihaz aktif Patron:"]
        for dev in online:
            lines.append(f"  • {dev.name} — {dev.ip}")

        scan_time = self.last_scan.strftime("%H:%M:%S") if self.last_scan else "bilinmiyor"
        lines.append(f"Son tarama: {scan_time}")
        return "\n".join(lines)

    async def continuous_monitor(self, interval: int = 30, on_change=None):
        """
        Arka planda sürekli tarama yapar.
        on_change(yeni_cihaz, ayrılan_cihaz) callback'i tetikler.
        """
        prev_online = set()
        while True:
            await self.scan()
            curr_online = {dev.mac for dev in self.get_online()}

            if prev_online:
                joined = curr_online - prev_online
                left = prev_online - curr_online

                if on_change and (joined or left):
                    joined_devs = [self.devices[m] for m in joined if m in self.devices]
                    left_devs = [self.devices[m] for m in left if m in self.devices]
                    await on_change(joined_devs, left_devs)

            prev_online = curr_online
            await asyncio.sleep(interval)