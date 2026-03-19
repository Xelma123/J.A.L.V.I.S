import os
import json
import asyncio
import google.generativeai as genai
import re
from urllib.parse import quote_plus
import webbrowser
import pyautogui
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── Prompt Dosya Yolu ─────────────────────────────────────────────────────────
PROMPT_FILE = os.path.join(os.path.dirname(__file__), "SYSTEM_PROMPT.json")

# --- JARVIS SİSTEM ARAÇLARI ---
_SHUTDOWN_PENDING = False

def system_operation(action: str, target: str = None, extra_data: str = None):
    """YouTube, Medya ve Dosya işlemlerini yöneten ana çekirdek fonksiyon."""
    global _SHUTDOWN_PENDING
    try:
        if action == "open_youtube":
            query = quote_plus(extra_data) if extra_data else ""
            url = f"https://www.youtube.com/results?search_query={query}" if query else "https://www.youtube.com"
            webbrowser.open(url)
            return f"Sistem: YouTube üzerinden '{extra_data if extra_data else 'Ana Sayfa'}' talebi yürütüldü."
        elif action == "media_control":
            pyautogui.press(target)
            return "Sistem: Medya katmanı güncellendi."
        elif action == "shutdown_pc":
            _SHUTDOWN_PENDING = True
            return "Bilgisayarı kapatmak istediğinize emin misiniz Patron? Sesli onay bekliyorum."
    except Exception as e:
        return f"Hata: İşlem yürütülemedi. Detay: {str(e)}"
    return "Hata: Bilinmeyen komut."


def _load_system_prompt() -> str:
    """SYSTEM_PROMPT.json dosyasından sistem talimatını yükler."""
    try:
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        prompt = data.get("system_instruction_template", "")
        if prompt:
            print(f"📜 Sistem promptu yüklendi (v{data.get('meta', {}).get('version', '?')})")
            return prompt
    except FileNotFoundError:
        print(f"⚠️ {PROMPT_FILE} bulunamadı, varsayılan prompt kullanılıyor.")
    except Exception as e:
        print(f"⚠️ Prompt yükleme hatası: {e}")

    # Fallback — dosya yoksa veya hatalıysa
    return (
        "Sen J.A.R.V.I.S.'sin. Patron'un kişisel AI asistanısın. "
        "Kısa ve net cevap ver. Maksimum 2-3 cümle. "
        "Kapanış sorusu sorma. Patron veya Efendim hitabı kullan."
    )


class JarvisBrain:
    def __init__(self):
        self.api_keys = [os.getenv(k) for k in os.environ if "GEMINI_API_KEY" in k]
        self.api_keys = [k for k in self.api_keys if k]

        if not self.api_keys:
            raise Exception("🚨 HATA: .env dosyasında API anahtarı bulunamadı!")

        self.current_key_index = 0
        self.models_to_try = ['gemini-2.5-flash', 'gemini-2.5-flash-lite']
        self.current_model_index = 0

        # Prompt artık SYSTEM_PROMPT.json'dan yükleniyor
        self.system_instruction = _load_system_prompt()
        self._setup_current_config()

    def _setup_current_config(self):
        current_key = self.api_keys[self.current_key_index]
        current_model = self.models_to_try[self.current_model_index]
        genai.configure(api_key=current_key)
        self.model = genai.GenerativeModel(
            model_name=current_model,
            tools=[system_operation],
            system_instruction=self.system_instruction
        )
        self.chat = self.model.start_chat(enable_automatic_function_calling=True)
        print(f"📡 J.A.R.V.I.S. Aktif | Anahtar #{self.current_key_index + 1} | Model: {current_model}")

    def _rotate_logic(self):
        if self.current_model_index < len(self.models_to_try) - 1:
            self.current_model_index += 1
        else:
            self.current_model_index = 0
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        self._setup_current_config()

    # ── Komut Yönlendirici ────────────────────────────────────────────────────
    async def handle_request(self, user_input, memory, light_manager,
                              net_scanner=None, net_controller=None):
        global _SHUTDOWN_PENDING
        text = user_input.lower().strip()
        print(f"🔍 J.A.R.V.I.S. Analiz Ediyor: {text}")

        # ── Kapatma Onay Kontrolü ──────────────────────────────────────────────
        if _SHUTDOWN_PENDING:
            if any(w in text for w in ["evet", "tamam", "onay", "kapat", "devam"]):
                _SHUTDOWN_PENDING = False
                os.system("shutdown /s /t 5")
                return "Onay alındı. Bilgisayar 5 saniye içinde kapatılıyor Patron. İyi uykular."
            elif any(w in text for w in ["hayır", "iptal", "vazgeç", "dur", "bekle"]):
                _SHUTDOWN_PENDING = False
                return "Kapatma işlemi iptal edildi Patron."

        # ── Kestirme Komutlar ──────────────────────────────────────────────────
        if text == "jarvis":
            return "Buyurun Patron."

        if "saat kaç" in text:
            return f"Şu an saat {datetime.now().strftime('%H:%M:%S')}, Efendim."

        # ── Işık Kontrolü ──────────────────────────────────────────────────────
        if any(w in text for w in ["ışık", "lamba", "isik", "ampul", "parlak", "renk"]):
            res = await self._process_lights(text, light_manager)
            if res:
                memory.add(user_input, res)
                return res

        # ── YouTube ────────────────────────────────────────────────────────────
        if "youtube" in text:
            search_query = text.split("aç")[0].replace("youtube", "").replace("da", "").strip()
            res = system_operation("open_youtube", extra_data=search_query)
            memory.add(user_input, res)
            return res

        # ── Sistem Teşhisi (Donanım/HUD Komutu) ────────────────────────────────
        if any(w in text for w in ["sistem durum", "sistem rapor", "sistem analiz", "donanım rapor", "bilgisayarın durumu", "bilgisayar ne durumda", "sistem nasıl"]):
            res = self._process_system_status()
            memory.add(user_input, res)
            return res

        # ── Ağ Komutları ───────────────────────────────────────────────────────
        if net_scanner and net_controller:
            net_res = await self._process_network(text, net_scanner, net_controller)
            if net_res:
                memory.add(user_input, net_res)
                return net_res

        # ── Genel Sohbet (Gemini) ──────────────────────────────────────────────
        return await self._gemini_chat(user_input, memory)

    async def _process_network(self, text: str, scanner, controller) -> str | None:
        """Ağ ile ilgili komutları yakala ve yönlendir."""

        # Tarama
        if any(x in text for x in ["ağı tara", "ağda kim var", "cihazları listele",
                                     "ağ taraması", "bağlı cihazlar", "tekrar tara", "yeniden tara"]):
            await scanner.scan()
            return scanner.get_network_report()

        # Internet kesme
        cut_triggers = ["internetini kes", "internet kes", "interneti kes", "bağlantısını kes", "bağlantıyı kes", "engelle", "internetten kes"]
        if any(x in text for x in cut_triggers):
            target = self._extract_device_name(text, cut_triggers)
            if target:
                return await controller.block_device(target)
            return "Hangi cihazın internetini kesmemi istiyorsunuz Patron?"

        # Internet açma
        open_triggers = ["internetini aç", "interneti aç", "bağlantısını aç", "bağlantıyı aç", "engeli kaldır", "tekrar bağla", "internet ver"]
        if any(x in text for x in open_triggers):
            if any(x in text for x in ["hepsini", "tümünü", "hepsinin"]):
                return await controller.unblock_all()
            target = self._extract_device_name(text, open_triggers)
            if target:
                return await controller.unblock_device(target)
            return "Hangi cihazın bağlantısını açayım Patron?"

        # Kesili cihazlar
        if any(x in text for x in ["kesili cihaz", "hangileri kesik", "engelli cihaz"]):
            return controller.get_blocked_list()

        # Ping / durum kontrolü
        if any(x in text for x in ["çevrimiçi mi", "online mı", "bağlı mı", "açık mı"]):
            target = self._extract_device_name(text, [
                "çevrimiçi mi", "online mı", "bağlı mı", "açık mı"
            ])
            if target:
                return await controller.ping_device(target)

        # Wake-on-LAN
        if any(x in text for x in ["uyandır", "aç", "wake"]):
            if any(x in text for x in ["pc", "bilgisayar", "masaüstü"]):
                target = self._extract_device_name(text, ["uyandır", "aç", "wake"])
                if target:
                    return await controller.wake_device(target)

        # Cihaz isimlendir
        # FIX: Operatör önceliği düzeltildi — parantez ile açık hale getirildi
        if "adı olsun" in text or ("ismini" in text and "koy" in text):
            # "bu cihazın adı PS3 olsun" veya "192.168.1.5'in ismini PS3 koy"
            nums = re.findall(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', text)
            name_match = re.search(r'adı (\w+) olsun|ismini (\w+) koy', text)
            if nums and name_match:
                ip = nums[0]
                name = name_match.group(1) or name_match.group(2)
                success = scanner.label_by_ip(ip, name)
                return (f"{ip} adresli cihaz '{name}' olarak kaydedildi Patron."
                        if success else f"{ip} adresi veritabanında bulunamadı Patron.")

        return None  # Ağ komutu değil

    def _process_system_status(self) -> str:
        """Donanım sensörlerinden veri alıp Tony Starkvari sesli rapor verir."""
        try:
            import psutil
            cpu = int(psutil.cpu_percent(interval=0.5))
            ram = int(psutil.virtual_memory().percent)
            
            # Batarya
            bat_str = ""
            battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
            if battery:
                plug_str = "fişe bağlı (şarj oluyor)" if battery.power_plugged else "pilde kullanılıyor"
                bat_str = f" Güç kaynağı {plug_str}, batarya seviyesi yüzde {int(battery.percent)}."
                
            # Isı
            temp_str = ""
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if temps and 'coretemp' in temps:
                    core_temp = temps['coretemp'][0].current
                    temp_str = f" İşlemci ısısı {int(core_temp)} derece stabil seviyede."

            if cpu > 85:
                status = "İşlemci yükü kritik seviyelerde Patron, sistem şu an zorlanıyor."
            elif cpu > 50:
                status = "Sistem üzerinde belirgin bir iş yükü var."
            else:
                status = "Bütün çekirdekler devrede. Sistemler stabil ve tıkırında Patron."

            return f"{status} CPU çekirdek kullanımı yüzde {cpu}, ana bellek kullanımı yüzde {ram}.{bat_str}{temp_str}"
        except Exception as e:
            return "Holografik raporlama modülü donanımları kontrol edemiyor Patron. Arayüze kilitlenmiş olabilir."

    def _extract_device_name(self, text: str, triggers: list[str]) -> str | None:
        """Komut kelimesinden önceki veya sonraki cihaz adını tespit eder."""
        for trigger in sorted(triggers, key=len, reverse=True):
            if trigger in text:
                parts = text.split(trigger, 1)
                before = parts[0].strip()
                after = parts[1].strip() if len(parts) > 1 else ""
                
                # Çoğunlukla cihaz adı komuttan önce gelir ("Tabletin bağlantısını kes")
                device = before if before else after
                
                # Gereksiz tüm Türkçe iyelik takılarını temizle
                suffixes = ["'nın", "'nin", "'nun", "'nün", "'un", "'ün", "'ın", "'in", 
                            " nın", " nin", " nun", " nün", " un", " ün", " ın", " in",
                            "cihazının", "cihazın", "adlı", "isimli", "in", "ın", "un", "ün", "nin", "nın"]
                
                for suffix in suffixes:
                    if device.endswith(suffix):
                        # Özel ek isimle birleşikse onu kes (örn: tabletin -> tablet)
                        device = device[:-len(suffix)].strip()
                        break
                        
                if device:
                    return device
        return None

    async def _process_lights(self, text, light_manager) -> str | None:
        durum = ("ac" if any(x in text for x in ["aç", "yak"])
                 else "kapat" if any(x in text for x in ["kapat", "söndür"])
                 else None)
        renkler = ["kırmızı", "mavi", "yeşil", "sarı", "mor", "beyaz"]
        secilen_renk = next((r for r in renkler if r in text), None)
        parlaklik = None
        if "loş" in text:
            parlaklik = 20
        elif "parlak" in text or "full" in text:
            parlaklik = 100
        else:
            nums = re.findall(r'\d+', text)
            if nums:
                parlaklik = int(nums[0])

        if durum or secilen_renk or parlaklik:
            return await light_manager.ayarla(durum, secilen_renk, parlaklik)
        return None

    async def _gemini_chat(self, user_input: str, memory) -> str:
        search_query = user_input
        if any(x in user_input.lower() for x in ["adım", "ismim", "soyadım", "kimim"]):
            search_query = "Patronun adı, soyadı bilgileri"

        max_attempts = len(self.api_keys) * len(self.models_to_try)
        attempts = 0

        while attempts < max_attempts:
            try:
                past_context = memory.search(search_query)
                full_prompt = (
                    "### ANA VERİ TABANI KAYITLARI ###\n"
                    f"{past_context}\n"
                    "#################################\n\n"
                    f"Patron: {user_input}"
                )

                loop = asyncio.get_event_loop()
                response = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: self.chat.send_message(full_prompt)),
                    timeout=15.0
                )

                if response and response.text:
                    memory.add(user_input, response.text)
                    return response.text
                return "İstediğiniz işlemi gerçekleştirdim."

            except Exception as e:
                if any(x in str(e).lower() for x in ["429", "quota", "limit"]):
                    self._rotate_logic()
                    attempts += 1
                    await asyncio.sleep(1)
                else:
                    return f"İletişim hatası: {str(e)[:50]}"

        return "Sistem kapasitem doldu Patron."