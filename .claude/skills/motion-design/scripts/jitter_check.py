"""Проверка плавности: вертикальный сдвиг между соседними кадрами (фазовая корреляция, субпиксель).

python3 jitter_check.py frames/ 230 380 --crop 230,900,700,1450   # номера = порядковые номера файлов в папке
Сравнивает сдвиг каждого кадра с локальной параболой (окно 7 кадров).
Отклонение ≤0.3 px — глазом не видно; >0.5 px — заметное дрожание
(браузер округляет сдвиг до пикселя → рендерить в 2x, при необходимости 3x).
"""
import sys, glob, numpy as np
from PIL import Image

def shift(a, b):
    A = np.fft.fft2(a - a.mean()); B = np.fft.fft2(b - b.mean())
    R = A * np.conj(B); R /= np.abs(R) + 1e-9; r = np.fft.ifft2(R).real
    y, x = np.unravel_index(r.argmax(), r.shape); ny = r.shape[0]
    y0, y1, y2 = r[(y - 1) % ny, x], r[y, x], r[(y + 1) % ny, x]
    d = (y0 - y2) / (2 * (y0 - 2 * y1 + y2) + 1e-9)
    return (y if y < ny / 2 else y - ny) + d

def main():
    folder, a, b = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    crop = tuple(int(v) for v in sys.argv[sys.argv.index('--crop') + 1].split(',')) if '--crop' in sys.argv else None
    files = sorted(glob.glob(folder.rstrip('/') + '/*.png'))
    def load(i):
        im = Image.open(files[i]).convert('L')
        if im.width != 1080: im = im.resize((1080, im.height * 1080 // im.width), Image.LANCZOS)
        return np.asarray(im.crop(crop) if crop else im, dtype=float)
    s = [shift(load(i), load(i + 1)) for i in range(a, b)]
    print(' '.join(f'{v:.2f}' for v in s))
    # Сравниваем с локальной параболой по 7 кадрам: она повторяет разгон и торможение,
    # а скользящее среднее срезало бы пики скорости и давало ложное «дрожит».
    s = np.array(s); k = 3
    dev = np.zeros_like(s)
    for i in range(len(s)):
        lo, hi = max(0, i - k), min(len(s), i + k + 1)
        x = np.arange(lo, hi)
        fit = np.polyval(np.polyfit(x, s[lo:hi], 2 if hi - lo > 3 else 1), i)
        dev[i] = abs(s[i] - fit)
    # На быстром движении (десятки px/кадр) погрешность замера растёт: дрожание —
    # это отклонение больше 0.5 px И больше 3% скорости в этом кадре.
    shaky = (dev > 0.5) & (dev > 0.03 * np.abs(s))
    verdict = 'ДРОЖИТ' if shaky.any() else ('плавно' if dev.max() <= 0.3 else 'плавно (погрешность на быстром движении)')
    print(f'отклонение от плавного: среднее {dev.mean():.2f} px, максимум {dev.max():.2f} px — {verdict}')

if __name__ == '__main__':
    main()
