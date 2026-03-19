# 🧠 J.A.R.V.I.S. A.I. Asistanı (v2.1)

J.A.R.V.I.S., Python tabanlı, sürekli dinleyen (always-listening), çok katmanlı hafızaya sahip ve gelişmiş yetenekleri olan kişisel bir Yapay Zekâ (Gemini 2.5) asistanıdır. Evinizin IOT aletlerini, bilgisayarınızı ve ağ cihazlarınızı ses komutlarınızla yönetir.

---

## 🎧 Genel Konuşma ve Sistem Kontrolü
Jarvis tamamen uyanık halde sizi dinler. İlgisiz durumlar için uyku moduna geçmesini isteyebilirsiniz.

* **Uyku Modu:** `"Jarvis uyku moduna geç"`, `"Biraz bekle"`, `"Sessiz ol"`
  > *Ne yapar?* Dinleme modunu askıya alır, ekrandaki mavi çember söner. Kendi kendine sistemi dinlemez, kaynak tüketimini sıfıra indirir.
* **Uyandırma:** `"Jarvis"` veya `"Jarvis uyan"`
  > *Ne yapar?* Asistanı hemen tekrar aktif döngüye sokar.
* **Çoklu Komut (Chain):** Jarvis bağlaçları anlar!
  > Örnek: `"Işıkları mavi yap ve ağı tara ardından YouTube'da caz müzik aç"` (Üç işlemi de zekice bölüp sırayla uygular).
* **Saat Bilgisi:** `"Saat kaç?"` (Yapay zekayı yormadan yerel saat ile direkt cevaplar).
* **Bilgisayarı Kapatma:** `"Sistemi kapat"` veya `"Bilgisayarı kapat"`
  > *Ne yapar?* Yanlışlıkla kapanmaması için önce sesli onay ister. Sadece `"Evet"`, `"Kapat"` vb. cevap verirseniz sistemi uykuya alır (Kapatır).

---

## 💡 Akıllı Işık Yönetimi (Tapo Entegrasyonu)
Yerel ağınızdaki Tapo L530 vb. akıllı ampulleri saniyeler içinde yönetin.

* **Açma/Kapatma:** `"Işıkları aç"`, `"Işığı yak"`, `"Ampulü söndür"`, `"Işığı kapat"`
* **Renk Değiştirme:** `"Işıkları kırmızı yap"`, `"Ampulü mavi yap"`, `"Rengi yeşil yap"`
  > *Desteklenen renkler:* Kırmızı, Mavi, Yeşil, Sarı, Mor, Beyaz.
* **Parlaklık Ayarı:** 
  - `"Işıkları loş yap"` (%20)
  - `"Işıklar çok parlak olsun"` (%100)
  - `"Işığı yüzde 50 yap"` (%X değer)

---

## 👁️ Ekran Analizi (Vision - Görsel Zekâ)
Jarvis doğrudan baktığınız ekranı saniyede analiz ederek okuyan özel bir görüş modülüne sahiptir.

* **Ekranda Ne Var?:** `"Şu an ekranda ne var?"`, `"Ekranı analiz et"`
  > *Ne yapar?* Ekranın bir fotoğrafını okur ve size kısaca neler olduğunu/hangi uygulamanın açık olduğunu özetler.
* **Detaylı Soru:** `"Bu sayfadaki hata kodunun sebebi ne?"`, `"Monitörde gördüğün makalenin özetini çıkar"`
  > *Ne yapar?* Sorduğunuz soruya sadece ekrandaki piksellere bakarak okur ve çözüm / yanıt üretir.

---

## 🌐 Ağ ve İnternet Yönetimi (Hacker Modülü)
Ağınıza bağlı tüm cihazlara hükmedin. (Bu işlemler root/admin veya Scapy izni gerektirebilir).

* **Ağ Taraması:** `"Ağı tara"`, `"Ağda kimler var"`, `"Bağlı cihazları listele"`
  > *Ne yapar?* Modeme bağlı tüm cihazların IP'sini ve genel markalarını okur.
* **Cihaz İsimlendirme:** `"192.168.1.5'in adını PS3 koy"`, `"Bu cihazın adı telefonum olsun"`
  > *Ne yapar?* Gelecekte IP ile değil "PS3" diye seslenebilmeniz için cihazı ChromaDB'ye (kalıcı hafıza) kaydeder.
* **İnternet Kesme (ARP Block):** `"PS3'ün internetini kes"`, `"Telefonumun bağlantısını kes"`
  > *Ne yapar?* Doğrudan hedef cihaza salyarak internete çıkışını o an felç eder. (ARP Spoofing yapısı ile çalışır)
* **İnternet Geri Verme:** `"PS3 bağlantısını aç"`, `"Hepsinin engelini kaldır"`
* **Çevrimiçi Kontrol (Ping):** `"Ahmet'in telefonu çevrimiçi mi?"`, `"Bilgisayar açık mı?"`
* **Uyandırma (Wake on LAN):** `"Bilgisayarı uyandır"`, `"PC aç"`
  > *Ne yapar?* Cihaz MAC adresini biliyorsa, bilgisayarı fiziki olarak tetikleyip çalıştırır.

---

## 🎵 Medya & Tarayıcı İşlemleri
* **YouTube Arama:** `"YouTube'da Iron Man fragmanı aç"`, `"YouTube aç"`
  > *Ne yapar?* Varsayılan tarayıcınızda otomatik arama sayfasını oluşturup ekrana getirir.

---

## 🧠 Sonsuz Bellek (ChromaDB) ve Normal Sohbet
Bunların hiçbiri yoksa, JARVIS dünyanın en zeki yapay zekalarından (Gemini) biridir!
* Bütün konuşmalarınız ve verdiğiniz isimler Vector DB içerisinde kalıcı olarak kriptolanıp kaydedilir.
* `"Geçen gün bahsettiğim projenin adı neydi?"` derseniz geçmiş 2 aylık sohbeti bile tarayıp saniyeler içinde cevap verecektir.
* Her türlü kodlama problemi, matematik veya genel kültür sorusu için kullanabilirsiniz.

> **Uyarı:** `.env` dosyanıza kendi API keylerinizi, TP-Link hesabınızı ve ağ IP'nizi tanımlamadan yukarıdaki özelliklerin birçoğu yetkilendirme isteyecektir.
