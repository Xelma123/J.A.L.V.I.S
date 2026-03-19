"""
audio.py — JARVIS Ses Motoru
- Edge-TTS ile Türkçe sesli yanıt
- Google Speech Recognition ile sesli komut algılama
- FFT dalga akışı (HUD için stub)
- Sessizlik izleyici (uyku modu için)
"""

import asyncio
import os
import time
import speech_recognition as sr
import edge_tts
import pygame
from dotenv import load_dotenv

load_dotenv()


class AudioEngine:
    # FIX: hud parametresi eklendi — main.py AudioEngine(hud=self.hud) şeklinde çağırıyor
    def __init__(self, hud=None):
        self.hud = hud  # HUD referansı (FFT dalga gönderimi için)
        self._silence_callback = None
        self._silence_task = None

        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
        except Exception as e:
            # FIX: Bare except yerine açık Exception türü — pygame hatası loglanıyor
            print(f"⚠️ Pygame mixer başlatılamadı: {e}")

        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        
        # ── SES ALGISI İYİLEŞTİRMELERİ ──
        # Konuşurken nefes aldığında/duraksadığında cümleyi hemen kesmemesi için:
        self.recognizer.pause_threshold = 1.8
        # Konuşmanın bittiğinden emin olması için gereken sessizlik:
        self.recognizer.non_speaking_duration = 0.6
        # Arkadaki sabit gürültüleri (fan, yol sesi) filtrelemede oran:
        self.recognizer.dynamic_energy_ratio = 1.5

        self.voice = "tr-TR-AhmetNeural"

        print("🔧 Akustik kalibrasyon yapılıyor (Lütfen 3 saniye sessiz kalın)...")
        with self.microphone as source:
            # Ortam gürültüsünü tanımak için 1s yerine 3s dinlesin:
            self.recognizer.adjust_for_ambient_noise(source, duration=3.0)

    # FIX: Gerçek zamanlı ses genliği hesaplayıcı (FFT stub'ı RMS ile değiştirildi)
    def start_fft_stream(self):
        """Gerçek zamanlı mikrofon dinleyip frekansı HUD'a gönderir."""
        if not self.hud:
            print("🎵 FFT akışı başlatılamadı: HUD mevcut değil.")
            return

        import pyaudio
        import struct
        import threading
        import time

        def _worker():
            p = pyaudio.PyAudio()
            try:
                # Windows'ta WASAPI ve genel uyumluluk için standart ayarlar
                stream = p.open(format=pyaudio.paInt16,
                                channels=1,
                                rate=16000,
                                input=True,
                                frames_per_buffer=1024)
                print("🎵 Gerçek Zamanlı Ses Frekansı (FFT) HUD'a bağlandı.")
                while True:
                    try:
                        data = stream.read(1024, exception_on_overflow=False)
                        # Root Mean Square hesabı (genlik için en temiz yöntem)
                        shorts = struct.unpack(f"{len(data)//2}h", data)
                        rms = sum(x*x for x in shorts) / len(shorts)
                        rms = rms ** 0.5
                        
                        # Ses RMS değeri genelde 0-5000 arasındadır. Bunu HUD için 0-40 arasına sıkıştırıyoruz.
                        level = min(40, int(rms / 40))
                        self.hud.set_audio_level(level)
                    except Exception:
                        pass
                    # Arayüzü çok yormamak için saniyede 20-25 kare
                    time.sleep(0.04)
            except Exception as e:
                print(f"⚠️ FFT Mikrofonu meşgul olabilir: {e}")

        # Bloklamaması için daemon thread'de çalıştır
        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    # FIX: Eksik metot eklendi — main.py satır 112'de çağrılıyor
    def start_silence_watcher(self, callback, timeout_seconds: int = 120):
        """Belirli süre sessizlik olduğunda callback fonksiyonunu çağırır.
        timeout_seconds: Sessizlik eşiği (varsayılan 2 dakika)
        """
        self._silence_callback = callback
        self._silence_timeout = timeout_seconds
        self._last_activity = time.time()
        print(f"🔇 Sessizlik izleyici aktif ({timeout_seconds}s eşik).")

        async def _watcher_loop():
            while True:
                await asyncio.sleep(10)
                if self._silence_callback and (time.time() - self._last_activity > self._silence_timeout):
                    if asyncio.iscoroutinefunction(self._silence_callback):
                        await self._silence_callback()
                    else:
                        self._silence_callback()
                    self._reset_silence_timer()

        self._silence_task = asyncio.create_task(_watcher_loop())

    def _reset_silence_timer(self):
        """Her ses aktivitesinde zamanlayıcıyı sıfırla."""
        self._last_activity = time.time()

    @staticmethod
    def _clean_for_tts(text: str) -> str:
        """Markdown ve okunmaz karakterleri TTS öncesi temizler."""
        import re
        # Code block'ları kaldır
        text = re.sub(r'```[\s\S]*?```', '', text)
        # Inline code
        text = re.sub(r'`([^`]+)`', r'\1', text)
        # Bold ve italic
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        # Başlıklar (##, ###)
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        # Liste madde işaretleri
        text = re.sub(r'^\s*[-*•]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
        # Boş satırları tek satıra indir
        text = re.sub(r'\n{2,}', '\n', text)
        return text.strip()

    async def speak(self, text):
        """Ses verisini temp dosyasında çalar ve ardından dosyayı imha eder."""
        if not text:
            return
        # Markdown temizliği — TTS okunabilirliği için
        text = self._clean_for_tts(text)
        print(f"Jarvis: {text}")

        # Sessizlik zamanlayıcısını sıfırla
        self._reset_silence_timer()

        try:
            communicate = edge_tts.Communicate(text, self.voice)
            # TEMP klasörünü kullanarak sistem kirliliğini önle
            temp_file = os.path.join(
                os.getenv('TEMP', '/tmp'),
                f"jarvis_voice_{int(time.time())}.mp3"
            )

            await communicate.save(temp_file)

            pygame.mixer.music.load(temp_file)
            pygame.mixer.music.play()

            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.1)

            pygame.mixer.music.unload()
            if os.path.exists(temp_file):
                os.remove(temp_file)

        except Exception as e:
            print(f"❌ Ses Motoru Hatası: {e}")

    async def listen(self):
        """Mikrofonu dinler ve metne çevirir."""
        loop = asyncio.get_event_loop()
        try:
            with self.microphone as source:
                print("🎧 Dinleniyor...")
                audio_data = await loop.run_in_executor(
                    None,
                    lambda: self.recognizer.listen(
                        source, timeout=None, phrase_time_limit=12
                    )
                )

            text = await loop.run_in_executor(
                None,
                lambda: self.recognizer.recognize_google(
                    audio_data, language="tr-TR"
                )
            )
            print(f"Siz: {text}")

            # Sessizlik zamanlayıcısını sıfırla — kullanıcı konuştu
            self._reset_silence_timer()

            return text.lower()
        except sr.UnknownValueError:
            # Ses anlaşılamadı — normal durum, sessizce geç
            return None
        except sr.RequestError as e:
            # Google API hatası
            print(f"⚠️ Ses tanıma API hatası: {e}")
            return None
        except Exception as e:
            # FIX: Bare except yerine spesifik hata yakalama
            print(f"⚠️ Dinleme hatası: {e}")
            return None