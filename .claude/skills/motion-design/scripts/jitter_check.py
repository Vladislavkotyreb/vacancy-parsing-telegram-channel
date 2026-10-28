"""Проверка плавности: вертикальный сдвиг между соседними кадрами (фазовая корреляция, субпиксель).

python3 jitter_check.py frames/ 230 380 --crop 230,900,700,1450
Плавное движение — монотонный ряд без скачков (0.9 1.0 1.1 1.2 …).
Дрожание — «пила» (0.5 0.1 0.6 0.2 …): браузер округляет сдвиг до пикселя → рендерить в 2x.
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
    d = np.diff(s); flips = int(np.sum(np.sign(d[1:]) != np.sign(d[:-1])))
    print(f'смен направления ускорения: {flips} из {len(d) - 1} — больше ~20% = дрожание')

if __name__ == '__main__':
    main()
