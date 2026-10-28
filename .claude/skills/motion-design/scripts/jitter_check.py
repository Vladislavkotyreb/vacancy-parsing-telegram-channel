"""Проверка плавности: вертикальный сдвиг между соседними кадрами (фазовая корреляция, субпиксель).

python3 jitter_check.py frames/ 230 380 --crop 230,900,700,1450   # номера = порядковые номера файлов в папке
Сравнивает сдвиг каждого кадра со сглаженным рядом (окно 7 кадров).
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
    s = np.array(s); k = 7
    smooth = np.convolve(np.pad(s, k // 2, mode='edge'), np.ones(k) / k, mode='valid')
    dev = np.abs(s - smooth)
    verdict = 'плавно' if dev.max() <= 0.3 else ('почти плавно' if dev.max() <= 0.5 else 'ДРОЖИТ')
    print(f'отклонение от плавного: среднее {dev.mean():.2f} px, максимум {dev.max():.2f} px — {verdict}')

if __name__ == '__main__':
    main()
