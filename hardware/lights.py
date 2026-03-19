import asyncio
from tapo import ApiClient
import os

class LightManager:
    def __init__(self, email, password, ip):
        self.email = email
        self.password = password
        self.ip = ip
        self.client = ApiClient(self.email, self.password)
        self.device = None

    async def _ensure_connected(self):
        try:
            if self.device is None:
                self.device = await self.client.l530(self.ip)
            return True
        except Exception as e:
            print(f"💡 Tapo Bağlantı Hatası: {e}")
            return False

    async def ayarla(self, durum=None, renk=None, parlaklik=None):
        if not await self._ensure_connected():
            return "Ampule ulaşılamadı Patron."

        try:
            if durum == "ac": await self.device.on()
            elif durum == "kapat": await self.device.off()

            if renk:
                # Tapo L530 için H (0-360), S (0-100) değerleri
                renk_kodlari = {
                    "kırmızı": (0, 100), "mavi": (240, 100),
                    "yeşil": (120, 100), "sarı": (60, 100),
                    "mor": (280, 100), "beyaz": (0, 0)
                }
                h, s = renk_kodlari.get(renk.lower(), (0, 0))
                await self.device.set_color(h, s)

            if parlaklik is not None:
                # Parlaklığı sınırla (1-100)
                parlaklik = max(1, min(100, parlaklik))
                await self.device.set_brightness(parlaklik)
                
            return f"Işıklar istediğiniz gibi ayarlandı Patron. ({renk if renk else ''} {parlaklik if parlaklik else ''})"
        except Exception as e:
            self.device = None # Hata durumunda bağlantıyı sıfırla
            return f"Işık kontrol hatası: {e}"