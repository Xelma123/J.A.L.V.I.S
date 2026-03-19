"""
memory.py — JARVIS Bağlamsal Hafıza Motoru
- Önem puanı sistemi: kişisel bilgi, tercih, tekrar eden konular yüksek puan alır
- Erişim sayacı: sık aranan anılar öncelikli döner
- Hafıza seviyeleri: CORE (kalıcı) / LONG (uzun vadeli) / SHORT (kısa vadeli)
- Eskiyen düşük önemli anılar otomatik budanır
"""

import chromadb
import os
import uuid
import re
from datetime import datetime, timedelta
from typing import Optional

# ── Önem Puanı Konfigürasyonu ─────────────────────────────────────────────────

# Bu kelimeler/kalıplar yüksek önem puanı verir
HIGH_IMPORTANCE_PATTERNS = [
    # Kişisel kimlik
    r"\badım\b", r"\bismim\b", r"\bsoyadım\b", r"\bdoğum\b", r"\byaşım\b",
    r"\bnerede otur", r"\bşehir\b", r"\bev\b",
    # Tercihler & alışkanlıklar
    r"\bseverim\b", r"\bsevmem\b", r"\bseviyorum\b", r"\bnefret\b",
    r"\bterci\b", r"\balışkanlık\b", r"\bher zaman\b", r"\bgenellikle\b",
    # Önemli kararlar & görevler
    r"\bunutma\b", r"\bhatırlat\b", r"\bönemli\b", r"\bkritik\b",
    r"\bparola\b", r"\bşifre\b", r"\bip adresi\b", r"\bcihaz\b",
    # İş & proje
    r"\bproje\b", r"\bdeadline\b", r"\btoplantı\b", r"\bplan\b",
]

MEDIUM_IMPORTANCE_PATTERNS = [
    r"\bneden\b", r"\bnasıl\b", r"\bne zaman\b", r"\bkaç\b",
    r"\bjarvis\b", r"\bpatron\b",
]

# Hafıza koleksiyon isimleri (seviyeye göre ayrı bucket'lar)
COLLECTIONS = {
    "core":  "jarvis_core",   # Kalıcı, silinmez (önem >= 8)
    "long":  "jarvis_long",   # Uzun vadeli (önem 5-7)
    "short": "jarvis_short",  # Kısa vadeli (önem 1-4), budanabilir
}

MAX_SHORT_MEMORIES = 200  # Bu limitin üstüne çıkınca en eskiler silinir


class JarvisMemory:
    def __init__(self):
        self.persist_path = os.path.join(os.getcwd(), "jarvis_memory")
        os.makedirs(self.persist_path, exist_ok=True)

        self.client = chromadb.PersistentClient(path=self.persist_path)

        # Üç ayrı koleksiyon
        self.cols = {
            level: self.client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"}  # cosine: anlam benzerliği için daha iyi
            )
            for level, name in COLLECTIONS.items()
        }

        print(f"🧠 Hafıza yüklendi | "
              f"Core: {self.cols['core'].count()} | "
              f"Long: {self.cols['long'].count()} | "
              f"Short: {self.cols['short'].count()}")

    # ── Önem Puanı Hesaplama ──────────────────────────────────────────────────
    def _score(self, user_input: str, jarvis_output: str) -> int:
        """
        0-10 arası önem puanı hesaplar.
        10 = kritik kalıcı bilgi, 1 = sıradan sohbet
        """
        combined = (user_input + " " + jarvis_output).lower()
        score = 2  # Baz puan

        # Yüksek önem kalıpları (+2 her eşleşme, max +6)
        high_hits = sum(1 for p in HIGH_IMPORTANCE_PATTERNS if re.search(p, combined))
        score += min(high_hits * 2, 6)

        # Orta önem kalıpları (+1 her eşleşme, max +2)
        mid_hits = sum(1 for p in MEDIUM_IMPORTANCE_PATTERNS if re.search(p, combined))
        score += min(mid_hits, 2)

        # Uzunluk bonusu: detaylı konuşmalar daha değerli
        if len(user_input) > 80:
            score += 1

        # Jarvis çıktısı detaylıysa daha değerli
        if len(jarvis_output) > 150:
            score += 1

        return min(score, 10)

    def _get_collection(self, score: int):
        """Puana göre doğru koleksiyonu döner."""
        if score >= 8:
            return self.cols["core"], "core"
        elif score >= 5:
            return self.cols["long"], "long"
        else:
            return self.cols["short"], "short"

    # ── Hafızaya Ekleme ───────────────────────────────────────────────────────
    def add(self, user_input: str, jarvis_output: str,
            force_score: Optional[int] = None):
        """
        Konuşmayı hafızaya ekler.
        force_score: Manuel önem puanı (None = otomatik hesapla)
        """
        if not user_input or not jarvis_output:
            return

        score = force_score if force_score is not None else self._score(user_input, jarvis_output)
        collection, level = self._get_collection(score)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        content = (
            f"[{timestamp}] "
            f"Patron: {user_input} | "
            f"Jarvis: {jarvis_output}"
        )
        mem_id = str(uuid.uuid4())

        collection.add(
            documents=[content],
            metadatas=[{
                "type": "conversation",
                "date": timestamp,
                "score": score,
                "level": level,
                "access_count": 0,
                "user_input_preview": user_input[:60],
            }],
            ids=[mem_id]
        )

        icon = "🔴" if level == "core" else "🟡" if level == "long" else "⚪"
        print(f"{icon} Hafıza [{level.upper()} | puan:{score}]: {user_input[:40]}...")

        # Short hafızayı budama
        if level == "short":
            self._prune_short()

    def remember(self, key: str, value: str):
        """
        Özel bir bilgiyi doğrudan CORE hafızaya yazar.
        Örnek: memory.remember("Patronun adı", "Murat Can İşbilen")
        """
        self.add(f"[KALICI BİLGİ] {key}", value, force_score=10)

    # ── Hafızada Arama ────────────────────────────────────────────────────────
    def search(self, query_text: str, n_results: int = 5) -> str:
        """
        Tüm seviyelerde arama yapar, önem ve erişim sıklığına göre sıralar.
        En alakalı ve en önemli anıları döner.
        """
        if not query_text:
            return ""

        all_results = []

        for level, collection in self.cols.items():
            if collection.count() == 0:
                continue
            try:
                # Her seviyeden en fazla n_results kadar çek
                limit = min(n_results, collection.count())
                res = collection.query(
                    query_texts=[query_text],
                    n_results=limit,
                    include=["documents", "metadatas", "distances"]
                )
                if not res["documents"] or not res["documents"][0]:
                    continue

                # FIX: index() yerine enumerate + zip — aynı içerikli belgeler için
                # yanlış ID eşlemesi yapılıyordu
                ids_list = res.get("ids", [[]])[0]
                for idx, (doc, meta, dist) in enumerate(zip(
                    res["documents"][0],
                    res["metadatas"][0],
                    res["distances"][0]
                )):
                    score = meta.get("score", 1)
                    access = meta.get("access_count", 0)

                    # Birleşik sıralama puanı:
                    # düşük mesafe (yüksek benzerlik) + yüksek önem + erişim bonusu
                    similarity = max(0, 1 - dist)
                    rank = (similarity * 0.5) + (score / 10 * 0.4) + (min(access, 10) / 10 * 0.1)

                    all_results.append({
                        "doc": doc,
                        "meta": meta,
                        "rank": rank,
                        "level": level,
                        "id": ids_list[idx] if idx < len(ids_list) else None,
                    })

            except Exception as e:
                err_msg = str(e)
                print(f"⚠️ {level} hafıza arama hatası: {err_msg}")
                # HNSW Corrupted Segment Recovery (Oto-Tamir Modülü)
                if "Nothing found on disk" in err_msg or "segment reader" in err_msg:
                    print(f"🛠️ {level} koleksiyonunda fiziksel bozulma saptandı! Sıfırdan onarılıyor...")
                    try:
                        col_name = COLLECTIONS[level]
                        self.client.delete_collection(col_name)
                        self.cols[level] = self.client.create_collection(
                            name=col_name,
                            metadata={"hnsw:space": "cosine"}
                        )
                        print(f"✅ {level} hafızası başarıyla resetlendi/onarıldı.")
                    except Exception as reset_e:
                        print(f"❌ Oto-Tamir başarısız oldu: {reset_e}")

        if not all_results:
            return ""

        # Sırala ve en iyi n_results tanesini al
        all_results.sort(key=lambda x: x["rank"], reverse=True)
        top = all_results[:n_results]

        # Erişim sayacını artır (en çok erişilen anılar daha değerli hale gelir)
        self._increment_access(top)

        context = "\n---\n".join(r["doc"] for r in top)
        return context

    def _increment_access(self, results: list):
        """Dönen anıların erişim sayacını artırır."""
        for r in results:
            if not r.get("id"):
                continue
            level = r["level"]
            col = self.cols[level]
            meta = r["meta"].copy()
            meta["access_count"] = meta.get("access_count", 0) + 1
            try:
                col.update(ids=[r["id"]], metadatas=[meta])
            except Exception:
                pass

    # ── Budama ────────────────────────────────────────────────────────────────
    def _prune_short(self):
        """Short hafıza limitini aştıysa en eski ve en az erişilen anıları sil.
        FIX: Batch threshold eklendi — her ekleme yerine 20 fazlalık birikince çalışır.
        """
        col = self.cols["short"]
        count = col.count()
        # Her ekleme sonrası değil, 20 fazlalık birikince budama yap
        if count <= MAX_SHORT_MEMORIES + 20:
            return

        try:
            # Tüm short anıları çek
            all_items = col.get(include=["metadatas"])
            if not all_items["ids"]:
                return

            # Puan: düşük erişim + eski tarih = önce silinir
            scored = []
            for id_, meta in zip(all_items["ids"], all_items["metadatas"]):
                access = meta.get("access_count", 0)
                try:
                    date = datetime.strptime(meta.get("date", "2000-01-01 00:00:00"),
                                             "%Y-%m-%d %H:%M:%S")
                    age_days = (datetime.now() - date).days
                except Exception:
                    age_days = 999
                prune_score = age_days - (access * 2)  # Çok erişilenleri koru
                scored.append((id_, prune_score))

            # En yüksek prune_score = önce silinecek
            scored.sort(key=lambda x: x[1], reverse=True)
            to_delete = [s[0] for s in scored[:count - MAX_SHORT_MEMORIES + 20]]
            col.delete(ids=to_delete)
            print(f"🧹 Short hafızadan {len(to_delete)} eski anı budandı.")
        except Exception as e:
            print(f"⚠️ Budama hatası: {e}")

    # ── Yönetim ───────────────────────────────────────────────────────────────
    def get_stats(self) -> str:
        """Hafıza istatistiklerini döner."""
        core_n = self.cols["core"].count()
        long_n = self.cols["long"].count()
        short_n = self.cols["short"].count()
        total = core_n + long_n + short_n
        return (
            f"Hafıza durumu Patron: Toplam {total} anı | "
            f"🔴 Core: {core_n} | 🟡 Uzun: {long_n} | ⚪ Kısa: {short_n}"
        )

    def count(self) -> int:
        return sum(c.count() for c in self.cols.values())

    def clear_short(self):
        """Yalnızca kısa vadeli hafızayı temizle."""
        self.client.delete_collection(COLLECTIONS["short"])
        self.cols["short"] = self.client.get_or_create_collection(
            name=COLLECTIONS["short"],
            metadata={"hnsw:space": "cosine"}
        )
        print("🧹 Kısa vadeli hafıza temizlendi Patron.")

    def clear_all(self):
        """Tüm hafızayı sil (geri alınamaz)."""
        for name in COLLECTIONS.values():
            try:
                self.client.delete_collection(name)
            except Exception:
                pass
        self.__init__()
        print("🧹 Tüm hafıza sıfırlandı Patron.")