"""
display.py — JARVIS HUD Arayüzü
- Arc-reaktör tarzı dönen çember animasyonu
- Duruma göre renk değişimi (IDLE, LISTENING, THINKING, SPEAKING, SLEEPING)
- Hafıza sayacı göstergesi
- Her zaman en üstte, tıklamaları arkaya geçirir
"""

import sys
from PyQt6.QtWidgets import QMainWindow, QApplication
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QGuiApplication, QFont


class JarvisHUD(QMainWindow):
    def __init__(self):
        super().__init__()
        # Pencereyi her zaman en üstte ve diğer pencerelerin üzerinde tutar
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput  # Tıklamaları arkaya geçirir
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # FIX: Metinlere yer açmak için genişlik 260'dan 420'ye çıkarıldı. Yükseklik hala 260.
        self.resize(420, 260)

        screen = QGuiApplication.primaryScreen().availableGeometry()
        # Pencereyi ekranın sağ üst köşesine (boşluklu) hizala
        self.move(screen.width() - 430, 10)

        self.state = "IDLE"
        self.angle = 0
        self.pulse = 0
        self.pulse_dir = 1
        self._memory_count = 0  # FIX: Hafıza sayacı değişkeni eklendi

        # FIX: 25ms → 50ms (40 FPS yerine 20 FPS, CPU dostu)
        self.timer = QTimer()
        self.timer.timeout.connect(self.animate)
        self.timer.start(50)

        # ── Holografik Sistem Analizi Değişkenleri ──
        self.cpu_usage = 0
        self.ram_usage = 0
        self.net_io = "0 KB/s"
        self._last_net = None

        self.diag_timer = QTimer()
        self.diag_timer.timeout.connect(self._update_diagnostics)
        self.diag_timer.start(1000)  # Her saniye donanımı güncelle

    def _update_diagnostics(self):
        try:
            import psutil
            self.cpu_usage = int(psutil.cpu_percent(interval=0))
            self.ram_usage = int(psutil.virtual_memory().percent)
            
            net = psutil.net_io_counters()
            if self._last_net:
                # İndirme ve yükleme toplamı byte
                diff = (net.bytes_recv - self._last_net.bytes_recv) + (net.bytes_sent - self._last_net.bytes_sent)
                val_mb = diff / (1024 * 1024)
                if val_mb >= 0.1:
                    self.net_io = f"{val_mb:.1f} MB/s"
                else:
                    self.net_io = f"{int(diff / 1024)} KB/s"
            self._last_net = net
        except ImportError:
            self.cpu_usage = 0
            self.ram_usage = 0
            self.net_io = "psutil yok"

    def set_state(self, s):
        """HUD durumunu günceller (IDLE, LISTENING, THINKING, SPEAKING, SLEEPING)."""
        self.state = s

    # FIX: Eksik metot eklendi — main.py satır 115 ve 160'da çağrılıyor
    def set_memory_count(self, count: int):
        """Hafızadaki anı sayısını günceller."""
        self._memory_count = count

    def set_audio_level(self, level: int):
        """HUD'ın merkez genliğini (pulse) mikrofon frekansıyla yeniler."""
        if self.state in ["LISTENING", "SPEAKING"]:
            # Ani oynamaları önlemek için eski değerle yeni değeri yumuşatıyoruz (smoothing/lerping)
            self.pulse = self.pulse * 0.7 + level * 0.3

    def animate(self):
        # Katman önceliğini her karede tazele
        self.raise_()

        # FIX: SLEEPING state eklendi — uyku modunda yavaş dönüş
        speeds = {
            "THINKING": 12,
            "LISTENING": 2,
            "SPEAKING": 6,
            "IDLE": 3,
            "SLEEPING": 0.5,
        }
        self.angle = (self.angle + speeds.get(self.state, 3)) % 360

        # Eğer dinliyor veya konuşuyorsak animasyonu FFT (gerçek ses) devralır.
        # Diğer standart durumlarda nefes alma animasyonu kendi kendine çalışır.
        if self.state not in ["LISTENING", "SPEAKING"]:
            if self.pulse >= 12:
                self.pulse_dir = -1
            elif self.pulse <= 0:
                self.pulse_dir = 1
            self.pulse += self.pulse_dir * 0.6
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() // 2, self.height() // 2

        # FIX: SLEEPING state rengi eklendi (loş mavi)
        colors = {
            "LISTENING": QColor(0, 255, 255),
            "THINKING": QColor(255, 80, 0),
            "SPEAKING": QColor(0, 120, 255),
            "SLEEPING": QColor(60, 60, 120, 100),
        }
        base_color = colors.get(self.state, QColor(0, 190, 255, 130))

        p.translate(cx, cy)
        pen = QPen(base_color, 2)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.rotate(self.angle)
        p.drawEllipse(-100, -100, 200, 200)

        p.rotate(-self.angle * 1.5)
        pen.setStyle(Qt.PenStyle.SolidLine)
        pen.setWidth(4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(-75, -75, 150, 150, 0, 90 * 16)
        p.drawArc(-75, -75, 150, 150, 180 * 16, 90 * 16)

        p.setBrush(QBrush(QColor(
            base_color.red(), base_color.green(), base_color.blue(), 60
        )))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPoint(0, 0), 35 + int(self.pulse), 35 + int(self.pulse))

        # ── Holografik Yan Paneller (Tony Stark Arayüzü) ──
        # Rotasyonlardan çıkıp başlangıç açısına geri dönüyoruz ki yazılar düz kalsın
        p.resetTransform()
        p.translate(cx, cy)
        
        font = QFont("Consolas", 8, QFont.Weight.Bold)
        p.setFont(font)
        
        # Eğer aktifsek daha elektrikli bir mavi/turkuaz, değilsek sade
        text_color = base_color if self.state != "IDLE" else QColor(0, 200, 255, 180)
        p.setPen(text_color)

        # Sol Panel
        p.drawText(QPoint(-200, -30), f"CPU: %{self.cpu_usage:02d}")
        p.drawText(QPoint(-200, -10), f"RAM: %{self.ram_usage:02d}")
        p.drawText(QPoint(-200, 10),  f"NET: {self.net_io}")

        # Sağ Panel
        mode_str = "NÖBETÇİ" if self.state == "SLEEPING" else "AKTİF"
        state_str = self.state[:6] # Sığması için kısalt (LISTEN vs)
        p.drawText(QPoint(120, -30), f"SYS: {state_str}")
        p.drawText(QPoint(120, -10), f"MOD: {mode_str}")
        p.drawText(QPoint(120, 10),  f"MEM: {self._memory_count}")

        # Hafıza sayacını göster (Eski yeri iptal ettik, çünkü panellere alındı)

        # FIX: QPainter.end() çağrılıyor — kaynak sızıntısı önlendi
        p.end()