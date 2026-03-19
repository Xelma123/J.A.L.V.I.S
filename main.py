"""
main.py — JARVIS Ana Çekirdek (v2)
- qasync ile stabil PyQt6 + asyncio entegrasyonu
- Sessizlik zaman aşımı → uyku modu
- Agent motoru (kod çalıştırma)
- Ekran analizi (mss + Gemini Vision)
- Ağ yönetimi (scanner + controller)
"""

import asyncio
import sys
import os
import base64
from dotenv import load_dotenv

import qasync
from PyQt6.QtWidgets import QApplication
import mss
from PIL import Image
import io

from brain import JarvisBrain
from hardware.lights import LightManager
from hardware.audio import AudioEngine
from ui.display import JarvisHUD
from memory import JarvisMemory
from agent import JarvisAgent
from network.scanner import NetworkScanner
from network.controller import NetworkController

load_dotenv()

# ── Ekran Analiz Yardımcısı ───────────────────────────────────────────────────
def capture_screen_base64() -> str:
    """Ekranın tam görüntüsünü base64 JPEG olarak döner."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # Birincil ekran
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        # Boyutu küçült (Gemini için optimize)
        img.thumbnail((1280, 720), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return base64.b64encode(buf.getvalue()).decode("utf-8")


class JarvisCore:
    def __init__(self):
        # HUD önce oluşturulur (AudioEngine'e referans için)
        self.hud = JarvisHUD()

        self.audio   = AudioEngine(hud=self.hud)
        self.memory  = JarvisMemory()
        self.brain   = JarvisBrain()
        self.agent   = JarvisAgent(audio_engine=self.audio, memory=self.memory)
        self.lights  = LightManager(
            os.getenv("EMAIL"),
            os.getenv("PASSWORD"),
            os.getenv("DEVICE_IP")
        )

        # Ağ modülü — artık aktif
        self.net_scanner = NetworkScanner()
        self.net_controller = NetworkController(self.net_scanner)

        self.is_active = False

    async def _on_silence(self):
        """2 dakika sessizlik → uyku modu"""
        if self.is_active:
            self.is_active = False
            self.hud.set_state("SLEEPING")
            await self.audio.speak(
                "Patron'un varlığı algılanamıyor. "
                "Enerji tasarrufu için bekleme moduna geçiyorum."
            )

    async def _analyze_screen(self, question: str) -> str:
        """Ekranı yakala, Gemini Vision ile analiz et."""
        try:
            img_b64 = capture_screen_base64()
            import google.generativeai as genai

            model = genai.GenerativeModel(
                'gemini-2.5-flash',
                system_instruction=(
                    "Sen J.A.R.V.I.S.'sin. Ekran görüntüsünü analiz ediyorsun.\n"
                    "KURALLAR:\n"
                    "- KISA CEVAP VER. Maksimum 2-3 cümle.\n"
                    "- Ekrandaki HER ŞEYİ tek tek açıklama. Sadece sorulan şeye odaklan.\n"
                    "- Görev çubuğu, saat, simgeler gibi genel Windows öğelerini açıklama.\n"
                    "- Markdown, emoji, liste, madde işareti kullanma — yanıt sesli okunacak.\n"
                    "- 'Başka sorunuz var mı?' gibi kapanış sorusu sorma.\n"
                    "- Doğal ve kısa konuş."
                )
            )
            response = model.generate_content([
                {
                    "parts": [
                        {"text": question},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": img_b64
                            }
                        }
                    ]
                }
            ])
            return response.text
        except Exception as e:
            return f"Ekran analizi başarısız Patron: {str(e)[:80]}"

    def _is_screen_query(self, text: str) -> bool:
        keywords = ["ekrana bak", "ekranı analiz", "ekranda ne var",
                    "bu pdf", "bu sayfa", "şu an açık", "monitörde"]
        return any(k in text for k in keywords)

    async def _split_commands(self, text: str) -> list[str]:
        """Cümleyi statik bağlaçlar yerine, anlama (LLM) dayalı olarak bağımsız komutlara ayırır."""
        # Fast-path: Eğer cümlede ayırıcı potansiyeli taşıyan bir kelime yoksa API'yi hiç yorma
        keywords = ["ve", "ardından", "sonra", "buna ek olarak", "önce", "ayrıca"]
        if not any(k in text for k in keywords):
            return [text]

        # Eğer potansiyel bir çoklu komut varsa, zekice bölmesi için Gemini'ye yolla
        try:
            import google.generativeai as genai
            import json
            
            model = genai.GenerativeModel(
                'gemini-2.5-flash-lite', # Çok hızlı ve ucuz model
                generation_config={"response_mime_type": "application/json"}
            )
            
            prompt = f"""
            Aşağıdaki kullanıcı cümlesi birden fazla bağımsız aksiyon/komut içeriyorsa, bunları bir JSON dizisi (list of strings) olarak böl.
            Eğer cümle tek bir bütünse veya "ve" kelimesi nesneleri bağlıyorsa (örn: "Ayşe ve Ali'yi ara", "elma ve armut"), tek parça olarak bırak.
            Örnek 1: "Işığı mavi yap ve televizyonu kapat" -> ["Işığı mavi yap", "televizyonu kapat"]
            Örnek 2: "Ahmet ve Mehmet'i ara" -> ["Ahmet ve Mehmet'i ara"]
            Örnek 3: "Ağı tara ardından müzik aç sonra uyu" -> ["Ağı tara", "müzik aç", "uyu"]
            Cümle: "{text}"
            """
            
            # Asenkron olarak modeli çağır
            response = await model.generate_content_async(prompt)
            commands = json.loads(response.text)
            
            # Geçerli bir liste döndürdüğünden emin ol
            if isinstance(commands, list) and len(commands) > 0:
                # Sadece 3 karakterden büyük komutları al (boşlukları sil)
                valid = [c.strip() for c in commands if len(c.strip()) > 3]
                return valid if valid else [text]
            return [text]
            
        except Exception as e:
            print(f"⚠️ Komut ayrıştırma hatası (Fallback kullanılıyor): {e}")
            return [text]

    async def run(self):
        self.hud.show()

        # FFT akışı başlat
        self.audio.start_fft_stream()

        # Sessizlik izleyici başlat
        self.audio.start_silence_watcher(self._on_silence)

        # Hafıza sayısını HUD'a ver
        self.hud.set_memory_count(self.memory.count())

        await self.audio.speak(
            "Sistemler yüzde yüz kapasiteyle aktif. "
            "J.A.R.V.I.S. hizmetinizde Patron."
        )

        while True:
            try:
                self.hud.set_state("LISTENING")
                user_text = await self.audio.listen()

                if not user_text:
                    continue

                # Uyandırma kontrolü
                if "jarvis" in user_text or self.is_active:
                    self.is_active = True

                    # Uyku komutu
                    if any(x in user_text for x in ["sessiz ol", "uyku modu", "bekle"]):
                        self.is_active = False
                        self.hud.set_state("SLEEPING")
                        await self.audio.speak("Uyku moduna geçiyorum. İhtiyaç duyduğunuzda çağırın Patron.")
                        continue

                    # Çoklu Komutlara Böl ("Işığı mavi yap ve YouTube'dan müzik aç")
                    commands = await self._split_commands(user_text)

                    for i, cmd in enumerate(commands):
                        if len(commands) > 1:
                            print(f"\n⚡ Çoklu Komut İşleniyor [{i+1}/{len(commands)}]: {cmd}")
                            
                        self.hud.set_state("THINKING")
                        response_text = ""

                        # 1. Önce Agent kontrolü (kod, hafıza vb.)
                        agent_result = await self.agent.process(cmd)
                        if agent_result:
                            response_text = agent_result

                        # 2. Ekran analizi
                        elif self._is_screen_query(cmd):
                            if len(commands) == 1:
                                await self.audio.speak("Ekranı tarıyorum Patron, bir saniye.")
                            response_text = await self._analyze_screen(cmd)

                        # 3. Normal Brain (Gemini + ışık + ağ + sohbet)
                        else:
                            response_text = await self.brain.handle_request(
                                cmd, self.memory, self.lights,
                                net_scanner=self.net_scanner,
                                net_controller=self.net_controller
                            )

                        # Hafıza sayısını güncelle
                        self.hud.set_memory_count(self.memory.count())

                        self.hud.set_state("SPEAKING")
                        await self.audio.speak(response_text)

                self.hud.set_state("IDLE")

            except Exception as e:
                # Hata dayanıklılığı — tek bir hata sistemi durdurmasın
                print(f"⚠️ Döngü hatası (devam ediliyor): {e}")
                self.hud.set_state("IDLE")
                await asyncio.sleep(0.5)


# ── Başlatıcı (qasync) ────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    jarvis = JarvisCore()

    async def _boot():
        await jarvis.run()

    with loop:
        loop.create_task(_boot())
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            print("\n[!] Jarvis Kapatılıyor. İyi günler Patron.")
            sys.exit(0)


if __name__ == "__main__":
    main()