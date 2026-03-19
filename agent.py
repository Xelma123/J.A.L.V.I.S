"""
agent.py — JARVIS Ajan Motoru (v2 - Telegram kaldırıldı)
- Kendi kendine Python kodu yazıp güvenli sandbox'ta çalıştırma
- Akıllı niyet algılama: "kod yaz" demene gerek yok
- Kritik işlemlerde sesli onay sistemi
- Hafızaya entegre: sonuçları otomatik kaydeder
"""

import asyncio
import os
import sys
import io
import traceback
import re
import textwrap
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

# ── Kod görevi olduğunu gösteren kalıplar ────────────────────────────────────
# FIX: Regex kalıpları ön-derlendi — her çağrıda tekrar derleme overhead'i kaldırıldı
_CODE_INTENT_PATTERNS = [
    re.compile(p) for p in [
        # Doğrudan istek
        r"kod yaz", r"python yaz", r"script yaz", r"program yaz",
        r"hesapla(yıp)? (göster|söyle|ver)", r"çalıştır",
        # Matematiksel / algoritmik görevler
        r"asal say", r"fibonacci", r"faktöriyel", r"sayıları listele",
        r"ortalama(sını)? (hesapla|bul)", r"en (büyük|küçük|yüksek|düşük)",
        r"kaç (tane|adet)", r"toplamı nedir", r"yüzde",
        # Veri işleme
        r"sırala", r"filtrele", r"say ve (göster|listele)",
        r"şifrele", r"encode", r"decode", r"hash",
        # Zaman / tarih
        r"kaç gün kaldı", r"gün farkı", r"tarih hesapla",
    ]
]

_NOT_CODE_PATTERNS = [
    re.compile(p) for p in [
        r"nedir", r"ne demek", r"anlat", r"açıkla", r"tarihçe",
        r"kim", r"nerede", r"ne zaman oldu",
    ]
]


def _is_code_task(text: str) -> bool:
    """Metnin kod görevi olup olmadığını belirler.
    FIX: Eski kod her zaman False dönüyordu — mantıksal çelişki düzeltildi.
    Yeni mantık: Hem kod hem sohbet kalıbı eşleşirse → kod öncelikli.
    """
    text = text.lower()
    code_hit = any(p.search(text) for p in _CODE_INTENT_PATTERNS)
    not_code_hit = any(p.search(text) for p in _NOT_CODE_PATTERNS)

    # Her iki kalıp da eşleşiyorsa (örn: "faktöriyel nedir" vs "faktöriyeli hesapla")
    # → Kod kalıbı varsa koda gönder (akcı niyet öncelikli)
    if code_hit and not_code_hit:
        return code_hit  # Kod niyeti daha güçlü

    # Sadece sohbet kalıbı → Gemini'ye
    if not_code_hit:
        return False

    return code_hit


class JarvisAgent:
    def __init__(self, audio_engine=None, memory=None):
        self.audio = audio_engine
        self.memory = memory  # Sonuçları kaydetmek için

        # Gemini (kod yazmak için — brain'den bağımsız kendi instance'ı)
        api_key = self._find_api_key()
        if api_key:
            genai.configure(api_key=api_key)
            self.code_model = genai.GenerativeModel(
                model_name='gemini-2.5-flash',
                system_instruction=(
                    "Sen bir uzman Python programcısısın. "
                    "Sadece saf, çalışan Python kodu yaz. "
                    "Markdown, açıklama veya yorum ekleme. "
                    "Sadece kod."
                )
            )
        else:
            self.code_model = None
            print("⚠️ Agent: Gemini API anahtarı bulunamadı.")

    def _find_api_key(self) -> str | None:
        for k in os.environ:
            if "GEMINI_API_KEY" in k:
                val = os.getenv(k)
                if val:
                    return val
        return None

    # ── Onay Sistemi ──────────────────────────────────────────────────────────
    async def ask_confirmation(self, action_description: str) -> bool:
        if self.audio:
            await self.audio.speak(
                f"Patron, onayınız gerekiyor. {action_description}. "
                f"Devam edeyim mi?"
            )
            response = await self.audio.listen()
            if response and any(w in response for w in
                                 ["evet", "tamam", "yap", "devam", "olur", "onay"]):
                return True
            await self.audio.speak("Anlaşıldı, iptal edildi Patron.")
            return False
        return True

    # ── Ana Giriş Noktası ─────────────────────────────────────────────────────
    async def process(self, user_input: str) -> str | None:
        """
        brain.py'den çağrılır.
        Kod görevi ise işler ve sonucu döner.
        Değilse None döner → brain Gemini'ye yönlendirir.
        """
        text = user_input.lower().strip()

        # Hafıza komutları
        if any(x in text for x in ["hafıza istatistik", "hafıza durumu", "kaç anım var"]):
            if self.memory:
                return self.memory.get_stats()
            return "Hafıza modülü bağlı değil Patron."

        if "kısa hafızayı temizle" in text:
            if self.memory:
                self.memory.clear_short()
                return "Kısa vadeli hafıza temizlendi Patron."

        # Kod görevi mi?
        if _is_code_task(text):
            return await self.write_and_run_code(user_input)

        return None

    # ── Kod Yazma & Çalıştırma ────────────────────────────────────────────────
    async def write_and_run_code(self, task_description: str,
                                  require_confirm: bool = True) -> str:
        if not self.code_model:
            return "Kod motoru hazır değil Patron."

        # Kodu üret
        await self.audio.speak("Kodu yazıyorum Patron, bir saniye.") if self.audio else None

        prompt = textwrap.dedent(f"""
            GÖREV: {task_description}
            
            Kurallar:
            - Sadece standart Python kütüphaneleri (math, datetime, json, re, random, itertools, collections)
            - print() ile sonucu göster
            - try/except ile hata yönetimi yap
            - 50 satırı geçme
            - Sadece ham Python kodu, markdown veya açıklama yok
            - Dosya okuma/yazma, ağ, sistem komutu kullanma
        """)

        try:
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: self.code_model.generate_content(prompt)),
                timeout=20.0
            )
            code = self._clean_code(response.text)
        except asyncio.TimeoutError:
            return "Kod üretme zaman aşımına uğradı Patron."
        except Exception as e:
            return f"Kod üretme hatası Patron: {str(e)[:60]}"

        # Güvenlik taraması
        block_reason = self._security_check(code)
        if block_reason:
            return f"Güvenlik ihlali tespit ettim Patron: {block_reason}. Görev iptal."

        # Onay
        if require_confirm:
            preview = code.split('\n')[0]  # Sadece ilk satırı seslendir
            confirmed = await self.ask_confirmation(
                f"Kodu yazdım. İlk satır: {preview}"
            )
            if not confirmed:
                return "Kod çalıştırma iptal edildi Patron."

        # Çalıştır
        result = await self._run_in_sandbox(code)

        # Hafızaya kaydet (önem puanı 7 — işlemsel ama değerli)
        if self.memory:
            self.memory.add(
                f"[KOD GÖREVİ] {task_description[:80]}",
                result[:200],
                force_score=7
            )

        return result

    def _clean_code(self, raw: str) -> str:
        code = re.sub(r"```python\s*\n?", "", raw)
        code = re.sub(r"```\s*", "", code)
        return code.strip()

    def _security_check(self, code: str) -> str | None:
        """Tehlikeli kalıpları tara. Bulursa açıklama döner, bulmazsa None."""
        checks = [
            (r"os\s*\.\s*system",     "os.system"),
            (r"subprocess",           "subprocess"),
            (r"shutil\s*\.\s*rmtree", "shutil.rmtree"),
            (r"os\s*\.\s*remove",     "os.remove"),
            (r"open\s*\(.+['\"]w",    "dosyaya yazma"),
            (r"__import__",           "__import__"),
            (r"\bsocket\b",           "socket"),
            (r"\brequests\b",         "requests"),
            (r"\burllib\b",           "urllib"),
            (r"\beval\b",             "eval"),
            (r"\bexec\b",             "exec"),
            (r"ctypes",               "ctypes"),
        ]
        for pattern, name in checks:
            if re.search(pattern, code):
                return name
        return None

    async def _run_in_sandbox(self, code: str) -> str:
        loop = asyncio.get_event_loop()

        def execute():
            buf = io.StringIO()
            # UYARI: sys.stdout global override thread-safe değil
            # ancak executor tek thread'de çalıştığı sürece kabul edilebilir
            old_stdout, old_stderr = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = buf

            # FIX: getattr ve type kaldırıldı — sandbox bypass riski:
            # getattr(__import__('os'), 'system') gibi saldırılar mümkündü
            safe_builtins = {
                "print": print, "len": len, "range": range,
                "str": str, "int": int, "float": float, "bool": bool,
                "list": list, "dict": dict, "set": set, "tuple": tuple,
                "sum": sum, "min": min, "max": max, "abs": abs,
                "round": round, "sorted": sorted, "reversed": reversed,
                "enumerate": enumerate, "zip": zip, "map": map, "filter": filter,
                "isinstance": isinstance,
                "chr": chr, "ord": ord, "hex": hex, "bin": bin,
                "Exception": Exception, "ValueError": ValueError,
                "TypeError": TypeError, "ZeroDivisionError": ZeroDivisionError,
                "IndexError": IndexError, "KeyError": KeyError,
                "True": True, "False": False, "None": None,
            }
            safe_globals = {
                "__builtins__": safe_builtins,
                "math":        __import__("math"),
                "datetime":    __import__("datetime"),
                "json":        __import__("json"),
                "re":          __import__("re"),
                "random":      __import__("random"),
                "itertools":   __import__("itertools"),
                "collections": __import__("collections"),
                "string":      __import__("string"),
            }

            try:
                exec(code, safe_globals)
                output = buf.getvalue().strip()
            except Exception:
                output = f"Hata: {traceback.format_exc(limit=2)}"
            finally:
                sys.stdout, sys.stderr = old_stdout, old_stderr

            return output or "Kod çalıştı ancak çıktı üretmedi."

        try:
            output = await asyncio.wait_for(
                loop.run_in_executor(None, execute),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            return "Kod 10 saniye limitini aştı Patron, durduruldu."

        if len(output) > 400:
            output = output[:400] + "... [çıktı kırpıldı]"

        return f"İşlem tamamlandı Patron. Sonuç: {output}"