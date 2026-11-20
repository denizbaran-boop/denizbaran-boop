# Kartlar nasıl çalışıyor

Profildeki her blok `cards/` klasöründeki bir SVG dosyası. Hepsini
`render_cards.py` çiziyor; animasyonlar ve fontlar SVG'nin içinde gömülü.

| Ne değişecek | Nereden |
| --- | --- |
| Yazılar, ürünler, renkler | `data/profile.json` |
| Kartların çizimi ve animasyonları | `scripts/render_cards.py` |
| Kartların sırası ve linkleri | `README.md` |
| Katkı verisi | `data/contributions.json` (elle düzenleme, Action yazıyor) |

## Elle çalıştırmak

```bash
pip install -r requirements.txt
python scripts/render_cards.py            # animasyonlu kartlar
STATIC=1 CARDS_DIR=/tmp/cards python scripts/render_cards.py   # son kare, ekran görüntüsü için
python -m pytest tests -q
```

## Otomatik yenileme

`.github/workflows/refresh.yml` her sabah GitHub'dan gerçek katkı takvimini
okuyor, kartları yeniden çiziyor ve değişiklik varsa commit'liyor. Commit'i
Actions botu atıyor; katkı grafiğine sayılmıyor. Yeni ürün eklemek için
`data/profile.json` içindeki `products` listesine bir satır, `README.md`'ye
bir `<img>` eklemek yeterli (`art` alanı: `notch`, `math` veya `route`).

Fontlar: Space Grotesk ve Manrope, SIL Open Font License (`assets/fonts/`).
